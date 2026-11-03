import base64
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = '0.7.3'
SOURCE = json.loads((Path(__file__).parent / 'release-identity.json').read_text())['source_sha']
TAG_OBJECT = json.loads((Path(__file__).parent / 'release-identity.json').read_text())['tag_object_sha']
WHEEL_SHA = '2d48d87f872ec9145a9f6d2f2b7adcae9ebe3154f9b47f7aa8aa2b411200c0dd'
API = 'https://api.github.com/repos/DocumentDrivenDX/arras'

def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Arras-public-release-verifier/0.7.3'})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()

def sha(data):
    return hashlib.sha256(data).hexdigest()

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
tag = json.loads(get(API + '/git/ref/tags/v' + VERSION))
assert tag['object']['sha'] == TAG_OBJECT
annotated = json.loads(get(API + '/git/tags/' + TAG_OBJECT))
assert annotated['object']['type'] == 'commit' and annotated['object']['sha'] == SOURCE
release = json.loads(get(API + '/releases/tags/v' + VERSION))
assert release['tag_name'] == 'v' + VERSION and not release['draft'] and not release['prerelease']
assets = release['assets']
assert len({asset['name'] for asset in assets}) == len(assets)
payloads = {}
urls = {}
for asset in assets:
    name = asset['name']
    assert Path(name).name == name and name not in ('', '.', '..')
    data = get(asset['browser_download_url'])
    assert len(data) == asset['size']
    if asset.get('digest'):
        assert asset['digest'] == 'sha256:' + sha(data)
    (root / name).write_bytes(data)
    payloads[name] = data
    urls[name] = asset['browser_download_url']
lines = payloads['SHA256SUMS'].decode().splitlines()
pins = {}
for line in lines:
    match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
    assert match, line
    digest, name = match.groups()
    assert name not in pins
    pins[name] = digest
assert set(pins) == set(payloads) - {'SHA256SUMS'}
for name, digest in pins.items():
    assert sha(payloads[name]) == digest, name
wheel = 'arras-' + VERSION + '-py3-none-any.whl'
sdist = 'arras-' + VERSION + '.tar.gz'
npm = 'documentdrivendx-arras-ui-' + VERSION + '.tgz'
assert pins[wheel] == WHEEL_SHA
assert pins[sdist] == '2d9b434dcba20d026bad58ff108361ca9db40152167ed2448cc22202968e4ba1'
assert pins[npm] == '10150ef0e4ad5bad8242ff8186ec6199d79839088729325c8afd0e7f22932695'
assert sha(payloads['SHA256SUMS']) == '05bbd62c47b44cf984c35b68e6b3e5be934a93709f0c5c690d92413937501cad'
assert pins['release-evidence.json'] == '6d789df734d7d9e2976a3ee210cf5f45a6137031d19c1435d819de8dea71bde3'
evidence = json.loads(payloads['release-evidence.json'])
assert evidence['schema_version'] == 3 and evidence['status'] == 'passed' and evidence['version'] == VERSION
for kind, name in [('wheel', wheel), ('sdist', sdist), ('npm', npm)]:
    assert evidence['release_artifacts'][kind] == {'filename': name, 'sha256': pins[name]}
components = set(payloads) - {wheel, sdist, npm, 'release-evidence.json', 'SHA256SUMS'}
assert evidence['published_components'] == {name: pins[name] for name in components}
with zipfile.ZipFile(io.BytesIO(payloads[wheel])) as archive:
    carried = archive.read('arras/ui/npm/' + npm)
    assert carried == payloads[npm]

pypi_url = 'https://pypi.org/pypi/arras/' + VERSION + '/json'
pypi = json.loads(get(pypi_url))
assert pypi['info']['version'] == VERSION
public_pypi = {}
assert {item['filename'] for item in pypi['urls']} == {wheel, sdist}
for item in pypi['urls']:
    name = item['filename']
    assert item['digests']['sha256'] == pins[name]
    actual = get(item['url'])
    assert actual == payloads[name]
    (root / ('pypi-' + name)).write_bytes(actual)
    public_pypi[name] = {'url': item['url'], 'sha256': sha(actual), 'github_bytes_equal': True}

npm_url = 'https://registry.npmjs.org/@documentdrivendx%2farras-ui/' + VERSION
metadata = json.loads(get(npm_url))
assert metadata['name'] == '@documentdrivendx/arras-ui' and metadata['version'] == VERSION
tarball = get(metadata['dist']['tarball'])
assert tarball == payloads[npm]
assert metadata['dist']['integrity'] == 'sha512-' + base64.b64encode(hashlib.sha512(tarball).digest()).decode()
assert metadata['dist']['shasum'] == hashlib.sha1(tarball).hexdigest()
(root / ('npm-' + npm)).write_bytes(tarball)
receipt = {
    'schema': 'arras.independent-public-bytes/1', 'status': 'passed', 'version': VERSION,
    'source_sha': SOURCE, 'tag_object_sha': TAG_OBJECT, 'release_url': release['html_url'],
    'all_github_assets_downloaded_anonymously': True, 'qualified_wheel_sdist_npm_digests_equal': True, 'complete_public_evidence_component_inventory_verified': True, 'checksum_payload_count': len(pins),
    'github_assets': {name: {'url': urls[name], 'sha256': sha(data)} for name, data in payloads.items()},
    'pypi': public_pypi,
    'npm': {'url': metadata['dist']['tarball'], 'sha256': sha(tarball), 'integrity': metadata['dist']['integrity'], 'github_and_wheel_bytes_equal': True},
}
(root / 'independent-public-bytes.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': 'passed', 'github_assets': len(payloads), 'wheel_sha256': pins[wheel], 'sdist_sha256': pins[sdist], 'npm_sha256': pins[npm]}, sort_keys=True))
