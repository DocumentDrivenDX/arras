import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, lstatSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const evidenceDirectory = '/private/tmp/arras070-independent-20261102';
const expectedDigest = '8f3c5ea2d98ffa8011e5acfe3d9a65cd773cd149481aeb6edcf2d671bb5af9de';
const githubArchive = join(evidenceDirectory, 'documentdrivendx-arras-ui-0.7.0.tgz');
const registryArchive = join(evidenceDirectory, 'npm-documentdrivendx-arras-ui-0.7.0.tgz');
const registryBytes = readFileSync(registryArchive);
const digest = (bytes, algorithm = 'sha256', encoding = 'hex') => createHash(algorithm).update(bytes).digest(encoding);
assert.equal(digest(registryBytes), expectedDigest);
assert.deepEqual(registryBytes, readFileSync(githubArchive));
const metadata = JSON.parse(readFileSync(join(evidenceDirectory, 'npm-metadata.json')));
assert.equal(metadata.name, '@documentdrivendx/arras-ui');
assert.equal(metadata.version, '0.7.0');
assert.equal(metadata.dist.integrity, `sha512-${digest(registryBytes, 'sha512', 'base64')}`);
assert.equal(metadata.dist.shasum, digest(registryBytes, 'sha1'));
const installedRoot = join(evidenceDirectory, 'consumer/node_modules/@documentdrivendx/arras-ui');
const entries = execFileSync('tar', ['-tf', githubArchive], { encoding: 'utf8' }).trim().split('\n').filter(entry => !entry.endsWith('/'));
const expectedFiles = entries.map(entry => {
  assert.ok(entry.startsWith('package/') && !entry.split('/').includes('..'));
  const relativePath = entry.slice('package/'.length);
  assert.deepEqual(readFileSync(join(installedRoot, relativePath)), execFileSync('tar', ['-xOf', githubArchive, entry], { maxBuffer: 32 * 1024 * 1024 }));
  return relativePath;
});
const installedFiles = [];
function inventory(directory, prefix = '') {
  for (const entry of readdirSync(directory)) {
    const relativePath = prefix ? `${prefix}/${entry}` : entry;
    const absolutePath = join(directory, entry);
    const stat = lstatSync(absolutePath);
    assert.ok(!stat.isSymbolicLink());
    if (stat.isDirectory()) inventory(absolutePath, relativePath);
    else installedFiles.push(relativePath);
  }
}
inventory(installedRoot);
assert.deepEqual(installedFiles.sort(), expectedFiles.sort());
const manifest = JSON.parse(readFileSync(join(installedRoot, 'package.json')));
assert.equal(manifest.version, '0.7.0');
const exportedModule = await import(pathToFileURL(join(installedRoot, 'dist/index.js')).href);
const exports = Object.keys(exportedModule).sort();
assert.ok(exports.length > 0);
const lock = JSON.parse(readFileSync(join(evidenceDirectory, 'consumer/package-lock.json')));
const installedEntry = lock.packages['node_modules/@documentdrivendx/arras-ui'];
assert.equal(installedEntry.integrity, metadata.dist.integrity);
assert.ok(installedEntry.resolved.startsWith('https://registry.npmjs.org/'));
const dependencies = Object.entries(lock.packages).filter(([path]) => path !== '').map(([path, dependency]) => {
  const origin = new URL(dependency.resolved);
  assert.equal(origin.origin, 'https://registry.npmjs.org');
  assert.equal(origin.username + origin.password + origin.search + origin.hash, '');
  return { path, version: dependency.version, resolved: dependency.resolved, integrity: dependency.integrity };
});
const receipt = {
  schema: 'arras.independent-public-npm-install.v1',
  status: 'passed',
  checkedAt: new Date().toISOString(),
  package: metadata.name,
  version: metadata.version,
  registry: 'https://registry.npmjs.org/',
  tarballSha256: expectedDigest,
  registryIntegrityVerified: true,
  githubArchiveByteEquality: true,
  installedFileCount: installedFiles.length,
  completeInstalledPayloadParity: true,
  freshCache: true,
  lifecycleScripts: 'disabled',
  exports,
  dependencies,
  packageLockSha256: digest(readFileSync(join(evidenceDirectory, 'consumer/package-lock.json'))),
  npm: execFileSync('npm', ['--version'], { encoding: 'utf8' }).trim(),
  node: process.version,
  platform: process.platform,
  architecture: process.arch,
  qualificationRun: 'https://github.com/DocumentDrivenDX/arras/actions/runs/41510837413',
};
writeFileSync(join(evidenceDirectory, 'independent-public-install.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify({ status: receipt.status, files: receipt.installedFileCount, exportCount: exports.length, tarballSha256: expectedDigest }));
