from __future__ import annotations

import hashlib
import base64
import csv
import importlib.metadata as metadata
import inspect
import json
import platform
import sys
import zipfile
from pathlib import Path

ROOT = Path('/Users/erik/Projects/arras')
UMF_ROOT = Path('/Users/erik/.codex/worktrees/1243/umf')
WHEEL = Path('/private/tmp/umf-u123-published-download/umf_core-0.10.0-py3-none-any.whl')
EXPECTED_WHEEL_SHA256 = '49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9'
OUT = Path('/private/tmp/arras-a1-probe/receipt.json')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


# Establish artifact identity before importing the package under examination.
if sha256(WHEEL) != EXPECTED_WHEEL_SHA256:
    raise SystemExit('wheel checksum did not match expected release digest')
installed = metadata.distribution('umf-core')
direct_url = json.loads(installed.read_text('direct_url.json') or '{}')
if installed.version != '0.10.0' or direct_url.get('url') != WHEEL.as_uri():
    raise SystemExit('active isolated environment does not point at the verified umf-core wheel')
with zipfile.ZipFile(WHEEL) as archive:
    record_rows = csv.reader(archive.read('umf_core-0.10.0.dist-info/RECORD').decode().splitlines())
    installed_record_checks = []
    for relative_path, digest, _size in record_rows:
        if not digest:
            continue
        algorithm, expected = digest.split('=', 1)
        installed_bytes = installed.locate_file(relative_path).read_bytes()
        actual = base64.urlsafe_b64encode(hashlib.new(algorithm, installed_bytes).digest()).decode().rstrip('=')
        installed_record_checks.append({'path': relative_path, 'matches': actual == expected})
if any(not item['matches'] for item in installed_record_checks):
    raise SystemExit('installed umf-core files differ from the checksum-verified wheel RECORD')

import umf
from umf import Diagnostic, Extension, Registry, read_document, validate_document, write_document


def diagnostic(d):
    return {'code': d.code, 'path': d.path, 'message': d.message, 'severity': d.severity}


def validate_case(name: str, data: dict, registry=None, round_trip=False):
    try:
        document = read_document(json.dumps(data), format='json')
    except Exception as error:
        return {
            'name': name,
            'read_error': type(error).__name__,
            'read_error_message': str(error),
        }
    result = validate_document(document, registry)
    answer = {
        'name': name,
        'document_type': type(document).__name__,
        'valid': result.valid,
        'complete': result.complete,
        'diagnostics': [diagnostic(d) for d in result.diagnostics],
        'action_count_first_module': len(document.to_dict().get('modules', [{}])[0].get('actions', [])) if document.to_dict().get('modules') else 0,
    }
    if round_trip:
        out = write_document(document, format='json')
        reread = read_document(out, format='json')
        answer['round_trip_preserves_document'] = reread.to_dict() == document.to_dict()
        answer['actions_preserved'] = reread.to_dict().get('modules', [{}])[0].get('actions', []) == data.get('modules', [{}])[0].get('actions', []) if data.get('modules') else True
    return answer


def validate_raw_case(name: str, data: dict, registry=None):
    result = validate_document(data, registry)
    return {
        'name': name,
        'validation_input': 'raw-json-value',
        'valid': result.valid,
        'complete': result.complete,
        'diagnostics': [diagnostic(d) for d in result.diagnostics],
    }


def read_document_outcome(data: dict):
    try:
        read_document(json.dumps(data), format='json')
        return {'admitted': True, 'error_type': None, 'errors': []}
    except Exception as error:
        details = []
        if hasattr(error, 'errors'):
            details = [
                {'loc': list(item.get('loc', ())), 'type': item.get('type'), 'message': item.get('msg')}
                for item in error.errors(include_url=False, include_input=False)
            ]
        return {'admitted': False, 'error_type': type(error).__name__, 'errors': details}


def registry_for_corpus_case(case: dict):
    spec = case.get('registry')
    registry = Registry()
    if spec is None:
        return registry

    # This is copied from the official UMF Python conformance harness exactly;
    # it is a generic registered callback, not an inferred DDD/action handler.
    def callback(payload, context):
        return [Diagnostic(
            'BASELINE_CALLBACK',
            context['path'],
            f"{context['document']['id']}:{context['scope']}:{payload['kind']}",
            'warning',
        )]

    registry.register(Extension(
        spec['id'], spec['version'], (spec['scope'],), True, callback,
    ))
    return registry


core = {'umf': '0.10.0', 'id': 'admission-probe-core', 'vocabularies': {}, 'extensions': {}, 'modules': []}
ddd = {
    'umf': '0.10.0', 'id': 'admission-probe-ddd',
    'vocabularies': {'umf.ddd': {'version': '0.1.0'}}, 'extensions': {},
    'modules': [{'id': 'catalog', 'namespace': 'catalog', 'extensions': {'umf.ddd': {'kind': 'bounded-context', 'terms': []}}, 'elements': []}],
}
view = {
    'umf': '0.10.0', 'id': 'admission-probe-view',
    'vocabularies': {'arras.view': {'version': '0.1.0'}}, 'extensions': {},
    'modules': [{'id': 'catalog', 'namespace': 'catalog', 'extensions': {'arras.view': {'title': 'Catalog'}}, 'elements': []}],
}
unknown_ext = {
    'umf': '0.10.0', 'id': 'admission-probe-custom',
    'vocabularies': {'acme.catalog': {'version': '1.2.3'}}, 'extensions': {},
    'modules': [{'id': 'catalog', 'namespace': 'catalog', 'extensions': {'acme.catalog': {'title': 'Catalog'}}, 'elements': []}],
}
unknown_vocab_version = json.loads(json.dumps(ddd)); unknown_vocab_version['id'] = 'admission-probe-ddd-unknown-version'; unknown_vocab_version['vocabularies']['umf.ddd']['version'] = '0.2.0'
unknown_core_version = json.loads(json.dumps(core)); unknown_core_version['id'] = 'admission-probe-core-unknown-version'; unknown_core_version['umf'] = '0.11.0'

registered = Registry()
registered.register(Extension(
    id='acme.catalog', version='1.2.3', scopes=('module',),
    schema={'type': 'object', 'required': ['title'], 'properties': {'title': {'type': 'string'}}, 'additionalProperties': False},
    semantics=lambda value, context: [],
))
registered_invalid = json.loads(json.dumps(unknown_ext)); registered_invalid['id'] = 'admission-probe-custom-invalid'; registered_invalid['modules'][0]['extensions']['acme.catalog'] = {'title': 3}
registered_missing_semantics = Registry()
registered_missing_semantics.register(Extension(
    id='acme.catalog', version='1.2.3', scopes=('module',),
    schema={'type': 'object', 'required': ['title'], 'properties': {'title': {'type': 'string'}}},
))

cases = [
    validate_case('core-only', core, round_trip=True),
    validate_case('ddd-unregistered-0.1.0', ddd, round_trip=True),
    validate_case('arras.view-unregistered-0.1.0', view, round_trip=True),
    validate_case('unknown-vocabulary-version', unknown_vocab_version, round_trip=True),
    validate_case('unknown-core-version', unknown_core_version, round_trip=True),
    validate_case('custom-extension-unregistered', unknown_ext, round_trip=True),
    validate_case('custom-extension-registered-with-semantics', unknown_ext, registered, round_trip=True),
    validate_case('custom-extension-registered-without-semantics', unknown_ext, registered_missing_semantics, round_trip=True),
    validate_case('custom-extension-registered-schema-invalid', registered_invalid, registered, round_trip=True),
]

fixture_path = ROOT / 'src/arras/conformance/module.umf.json'
fixture = json.loads(fixture_path.read_text())
cases.append(validate_case('arras-legacy-current-action-fixture', fixture, round_trip=True))

conformance_path = UMF_ROOT / 'fixtures/metamodel/current-conformance.json'
conformance = json.loads(conformance_path.read_text())
conformance_by_id = {case['id']: case for case in conformance['cases']}

def corpus_case(case_id: str):
    source_case = conformance_by_id[case_id]
    data = source_case['document']
    actual = validate_raw_case(
        f'umf-current-conformance:{case_id}', data, registry_for_corpus_case(source_case),
    )
    actual['read_document'] = validate_case(
        f'umf-current-conformance:{case_id}:read-document', data, round_trip=True,
    )
    actual['source_case_id'] = case_id
    actual['independent_expected'] = {
        'valid': source_case['valid'],
        'complete': source_case['complete'],
        'diagnostics': source_case['diagnostics'],
    }
    actual['matches_independent_expected'] = (
        actual.get('valid') == source_case['valid']
        and actual.get('complete') == source_case['complete']
        and actual.get('diagnostics') == source_case['diagnostics']
    )
    return actual

keys_case = conformance_by_id['keys/primary-and-alternate']
identity_doc = json.loads(json.dumps(keys_case['document']))
core_identity_doc = json.loads(json.dumps(identity_doc))
core_identity_doc.get('vocabularies', {}).pop('future', None)
core_identity_doc.get('extensions', {}).pop('future', None)
core_identity = validate_case('derived-core-only-record-key-field', core_identity_doc, round_trip=True)
core_identity['source_case_id'] = keys_case['id']
core_identity['source_conformance_file'] = str(conformance_path)
core_identity['source_conformance_file_sha256'] = sha256(conformance_path)
core_identity['source_document_sha256'] = hashlib.sha256(json.dumps(identity_doc, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
core_identity['source_independent_expected'] = {
    'valid': keys_case['valid'],
    'complete': keys_case['complete'],
    'diagnostics': keys_case['diagnostics'],
}
core_identity['derivation'] = [
    'deep-copy keys/primary-and-alternate document',
    'remove only top-level vocabularies.future declaration',
    'remove only top-level extensions.future payload',
]
core_identity['identity_structure'] = {
    'module_count': len(core_identity_doc['modules']),
    'record_ids': [e['id'] for m in core_identity_doc['modules'] for e in m.get('elements', []) if e.get('kind') == 'record'],
    'field_ids': [e['id'] for m in core_identity_doc['modules'] for e in m.get('elements', []) if e.get('kind') == 'field'],
    'keys': [
        {'id': key['id'], 'primary': key.get('primary', False), 'field_refs': key['fields']}
        for m in core_identity_doc['modules']
        for element in m.get('elements', []) if element.get('kind') == 'record'
        for key in element.get('keys', [])
    ],
}

actions_path = UMF_ROOT / 'docs/helix/03-test/fixtures/bulk-update/model.json'
official_actions = json.loads(actions_path.read_text())
official_actions_probe = validate_case('official-umf.actions-fixture', official_actions, round_trip=True)
official_actions_probe['fixture_path'] = str(actions_path)
official_actions_probe['fixture_sha256'] = sha256(actions_path)
official_actions_probe['action_count'] = len(official_actions['modules'][0]['extensions']['umf.actions']['actions'])
official_actions_probe['canonical_actions_preserved'] = official_actions_probe['round_trip_preserves_document']

targeted_corpus_cases = [
    corpus_case('keys/primary-and-alternate'),
    corpus_case('schema-properties/valid'),
    corpus_case('schema-properties/inverted-length'),
]

corpus_results = []
for source_case in conformance['cases']:
    actual = validate_raw_case(
        f'umf-current-conformance:{source_case["id"]}',
        source_case['document'], registry_for_corpus_case(source_case),
    )
    matches = (
        actual.get('valid') == source_case['valid']
        and actual.get('complete') == source_case['complete']
        and actual.get('diagnostics') == source_case['diagnostics']
    )
    corpus_results.append({
        'id': source_case['id'],
        'expected_valid': source_case['valid'],
        'expected_complete': source_case['complete'],
        'expected_diagnostics': source_case['diagnostics'],
        'actual_valid': actual.get('valid'),
        'actual_complete': actual.get('complete'),
        'actual_diagnostics': actual.get('diagnostics', []),
        'read_document': read_document_outcome(source_case['document']),
        'matches_independent_expected': matches,
    })

requirements = {}
for name in ('jsonschema', 'pydantic', 'ruamel.yaml', 'attrs', 'referencing', 'rpds-py', 'typing_extensions', 'annotated-types', 'pydantic_core', 'jsonschema-specifications', 'typing-inspection'):
    try:
        requirements[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        pass

receipt = {
    'probe': 'arras-umf-admission-installed-wheel-probe/1',
    'wheel': {
        'path': str(WHEEL), 'sha256': sha256(WHEEL), 'expected_sha256': EXPECTED_WHEEL_SHA256,
        'size_bytes': WHEEL.stat().st_size, 'release': 'umf-v0.5.4',
        'github_asset_id': 664083471,
    },
    'installation': {
        'venv': sys.prefix, 'python': sys.version.split()[0], 'implementation': platform.python_implementation(),
        'base_prefix': sys.base_prefix, 'isolated_venv': sys.prefix != sys.base_prefix,
        'venv_reused_read_only_this_probe': True,
        'installed_wheel_record_verified_before_umf_import': True,
        'distribution': installed.metadata['Name'], 'version': installed.version,
        'direct_url': direct_url, 'import_file': umf.__file__,
        'requirements_installed': requirements,
        'all_distributions': sorted(f'{d.metadata["Name"]}=={d.version}' for d in metadata.distributions()),
        'wheel_record_file_count': len(installed_record_checks),
        'wheel_record_mismatch_paths': [item['path'] for item in installed_record_checks if not item['matches']],
    },
    'public_api': {
        '__all__': list(umf.__all__),
        'specialized_projection_or_action_plan_exports': [name for name in umf.__all__ if any(token in name.casefold() for token in ('projection', 'actionplan', 'action_plan', 'planner'))],
        'read_document': str(inspect.signature(read_document)),
        'validate_document': str(inspect.signature(validate_document)),
        'write_document': str(inspect.signature(write_document)),
        'Registry': str(inspect.signature(Registry)),
        'Registry.register': str(inspect.signature(Registry.register)),
        'Registry.get': str(inspect.signature(Registry.get)),
        'Extension': str(inspect.signature(Extension)),
        'Validation_fields': list(inspect.signature(type(validate_document(core))).parameters),
        'Diagnostic': str(inspect.signature(Diagnostic)),
    },
    'fixtures': {
        'arras_current_action_fixture_path': str(fixture_path),
        'arras_current_action_fixture_sha256': hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        'arras_current_action_count': len(fixture['modules'][0].get('actions', [])),
        'current_conformance_path': str(conformance_path),
        'current_conformance_sha256': sha256(conformance_path),
        'current_conformance_profile': conformance['profile'],
        'current_conformance_case_count': len(conformance['cases']),
        'official_actions_fixture_path': str(actions_path),
        'official_actions_fixture_sha256': sha256(actions_path),
        'official_actions_fixture_action_count': official_actions_probe['action_count'],
    },
    'cases': cases + targeted_corpus_cases + [core_identity, official_actions_probe],
    'current_conformance_corpus_comparison': {
        'case_count': len(corpus_results),
        'match_count': sum(1 for case in corpus_results if case['matches_independent_expected']),
        'mismatch_count': sum(1 for case in corpus_results if not case['matches_independent_expected']),
        'mismatches': [case for case in corpus_results if not case['matches_independent_expected']],
    },
    'current_conformance_read_document_admission': {
        'admitted_count': sum(1 for case in corpus_results if case['read_document']['admitted']),
        'rejected_count': sum(1 for case in corpus_results if not case['read_document']['admitted']),
        'rejected_case_ids': [case['id'] for case in corpus_results if not case['read_document']['admitted']],
        'error_types': sorted({case['read_document']['error_type'] for case in corpus_results if not case['read_document']['admitted']}),
    },
    'supported_a2_recommendation': {
        'use_official_core': 'Use read_document and validate_document for core 0.10.0 parsing and core structure/metadata constraints; retain the independent 139-case conformance gate.',
        'extension_boundary': 'Supply only explicitly authoritative exact-version Registry entries for consumer vocabularies; the installed wheel does not register umf.ddd, arras.view, or umf.actions.',
        'execution_gate': 'Require both valid and complete before execution; valid alone includes retained unknown declarations and is not evidence their meaning was interpreted.',
        'actions_boundary': 'The official umf.actions fixture round-trips as valid/incomplete with UNKNOWN_EXTENSION; Arras legacy module.actions round-trips as valid/incomplete with UNKNOWN_CORE_FIELD. This probe establishes preservation only, not action parsing, authorization, planning, or execution.',
        'facet_boundary': 'The tested core conformance vectors validate field facet definitions and their declared default/example literals. This is metadata validation evidence, not a claim of runtime instance enforcement.',
        'not_established': ['DDD or arras.view semantic support by the released core wheel', 'UMF action plan/execution APIs', 'native adapter behavior'],
    },
}
if receipt['wheel']['sha256'] != EXPECTED_WHEEL_SHA256:
    raise SystemExit('wheel checksum did not match expected release digest')
OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(json.dumps({
    'receipt': str(OUT),
    'wheel_sha256': receipt['wheel']['sha256'],
    'case_count': len(receipt['cases']),
    'current_conformance_matches': receipt['current_conformance_corpus_comparison']['match_count'],
}, indent=2))
