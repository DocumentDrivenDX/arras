import hashlib
import json
import sys
import tarfile
import urllib.parse
from pathlib import Path

root = Path(__file__).resolve().parent
archive = Path(sys.argv[1])
package = root / 'node_modules/@documentdrivendx/arras-ui'
with tarfile.open(archive, 'r:gz') as stream:
    expected = {}
    for member in stream.getmembers():
        if not member.isfile():
            assert member.isdir(), 'unexpected npm archive member'
            continue
        assert member.name.startswith('package/')
        name = member.name.removeprefix('package/')
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert name not in expected
        expected[name] = stream.extractfile(member).read()
assert not any(path.is_symlink() for path in package.rglob('*'))
actual = {str(path.relative_to(package)): path for path in package.rglob('*') if path.is_file()}
assert set(actual) == set(expected)
for name, data in expected.items():
    assert not actual[name].is_symlink()
    assert actual[name].read_bytes() == data, name
lock = json.loads((root / 'package-lock.json').read_text())
origins = []
for name, item in lock['packages'].items():
    if name == '':
        continue
    parsed = urllib.parse.urlsplit(item['resolved'])
    assert parsed.scheme == 'https' and parsed.netloc == 'registry.npmjs.org'
    origins.append({'package': name, 'version': item['version'], 'url': item['resolved'], 'integrity': item['integrity']})
manifest = json.loads((package / 'package.json').read_text())
assert manifest['name'] == '@documentdrivendx/arras-ui' and manifest['version'] == '0.7.3'
receipt = {'schema': 'arras.independent-public-npm-install/1', 'status': 'passed', 'version': '0.7.3', 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'all_installed_package_files_equal_archive': True, 'file_count': len(expected), 'public_registry_dependency_origins': origins}
(root / 'npm-install-verification.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': 'passed', 'files': len(expected), 'public_dependencies': len(origins)}, sort_keys=True))
