import contextlib
import dataclasses
import importlib.metadata
import io
import json
import subprocess
import sys
from pathlib import Path

import arras
from arras import Invalid, graphfile
from arras.devhost import DevHost, main
from arras.distribution import DistributionConfig
from arras.sandbox import Sandbox, catalog_document
from arras.ui.assets import build_theme_manifest, load_manifest


def refuses(work, exception):
    try:
        work()
    except exception:
        return
    raise AssertionError('required refusal was not observed')


root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
assert importlib.metadata.version('arras') == '0.7.3'
assert 'site-packages' in str(Path(arras.__file__).resolve())
checks = {}

help_output = io.StringIO()
with contextlib.redirect_stdout(help_output):
    try:
        main(['--help'], operator_groups=('public_release_ops',))
    except SystemExit as error:
        assert error.code == 0
assert 'public_release_ops' in help_output.getvalue()
checks['effective_operator_help'] = True

css = root / 'public.css'
css.write_text('.arras-root { --surface: #123456; --arras-public-theme-proof: public-073; }\n')
manifests = {}
for appearance in ('light', 'dark', None):
    label = appearance or 'dual'
    manifest = build_theme_manifest(root / label, stylesheet=css, appearance=appearance)
    entry = load_manifest(manifest, kind='theme').entry
    assert entry.get('appearance') == appearance
    assert ('appearance' in entry) == (appearance is not None)
    manifests[label] = str(manifest)
invalid_output = root / 'invalid'
refuses(lambda: build_theme_manifest(invalid_output, stylesheet=css, appearance='sepia'), ValueError)
assert not invalid_output.exists()
configured = DistributionConfig(theme_manifest=manifests['light'])
host = DevHost(Sandbox(distribution=configured), port=8123, distribution=configured)
assert host.theme_manifest == Path(manifests['light'])
bad = build_theme_manifest(root / 'tampered', stylesheet=css, appearance='light')
(bad.parent / css.name).write_text('/* changed after manifest was authored */')
refuses(lambda: DevHost(Sandbox(), port=8124, distribution=DistributionConfig(theme_manifest=str(bad))), ValueError)
checks['theme_appearance_light_dark_and_omitted'] = True
checks['invalid_appearance_has_no_output_effect'] = True
checks['distribution_theme_reaches_stock_devhost'] = True
checks['tampered_theme_refused'] = True

document = json.loads(catalog_document())
document['vocabularies'].pop('arras.view', None)
document['vocabularies']['legacy.view'] = {'version': '0.1.0'}
module = document['modules'][0]
for carrier in (module, *module.get('elements', []), *module.get('relationships', [])):
    extensions = carrier.setdefault('extensions', {})
    if 'arras.view' in extensions:
        extensions['legacy.view'] = extensions.pop('arras.view')
module['extensions'].setdefault('legacy.view', {})['title'] = 'Legacy entrée'
raw = json.dumps(document, ensure_ascii=False, separators=(',', ':'))
refuses(lambda: Sandbox().load(raw), Invalid)
policy = DistributionConfig(view_vocabulary_aliases=('legacy.view',), graph_format_aliases=('legacy.graph',))
box = Sandbox(distribution=policy).load(raw)
session = box.arras.session(box.people['alice'])
selected = next(item for item in session.modules() if item.name == module['id'])
assert session.document(selected.name).text.encode('utf-8') == raw.encode('utf-8')
assert session.view_of(selected).module.title == 'Legacy entrée'
refuses(lambda: Sandbox().load(raw), Invalid)
refuses(lambda: setattr(policy, 'view_vocabulary_aliases', ()), dataclasses.FrozenInstanceError)
ambiguous = json.loads(raw)
ambiguous['vocabularies']['arras.view'] = {'version': '0.1.0'}
refuses(lambda: Sandbox(distribution=policy).load(json.dumps(ambiguous)), Invalid)
checks['explicit_view_alias_read_and_utf8_custody'] = True
checks['default_policy_stays_closed_after_alias_reader'] = True
checks['alias_policy_immutable_and_ambiguity_refused'] = True

graph_raw = '{"format":"legacy.graph","version":1,"module":"catalog","records":[{"code":"é"}]}'
refuses(lambda: graphfile.loads(graph_raw), ValueError)
graph = graphfile.loads(graph_raw, graph_format_aliases=policy.graph_format_aliases)
assert list(graph.records) == [{'code': 'é'}]
assert json.loads(graphfile.dumps(graph))['format'] == 'arras.graph'
refuses(lambda: graphfile.loads(graph_raw), ValueError)
checks['explicit_graph_alias_and_canonical_write'] = True

shim = root / 'release_shim'
shim.mkdir(exist_ok=True)
(shim / '__init__.py').write_text('from arras.alias import alias_package\n\ndef __getattr__(name):\n    if name == "host_value": return "host"\n    raise AttributeError(name)\n\nalias_package(__name__)\n')
(shim / 'operate.py').write_text('origin = "local-operate"\n')
(shim / 'mcp.py').write_text('origin = "local-mcp"\n')
for import_first in (False, True):
    code = 'import sys, importlib; sys.path.insert(0, ' + repr(str(root)) + '); import release_shim\n'
    if import_first:
        code += 'importlib.import_module("release_shim.operate"); importlib.import_module("release_shim.mcp")\n'
    code += 'assert release_shim.operate.origin == "local-operate"; assert release_shim.mcp.origin == "local-mcp"; assert release_shim.host_value == "host"\n'
    subprocess.run([sys.executable, '-I', '-c', code], check=True, cwd=root)
checks['real_local_shims_win_both_import_orders'] = True

receipt = {'schema': 'arras.public-feature-consumer/1', 'status': 'passed', 'version': '0.7.3', 'python': sys.version, 'arras_origin': str(Path(arras.__file__).resolve()), 'installed_versions': {name: importlib.metadata.version(name) for name in ('arras', 'umf-core', 'truss-toolkit', 'weft-sql')}, 'checks': checks, 'theme_manifests': manifests}
(root / 'feature-consumer.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, sort_keys=True))
