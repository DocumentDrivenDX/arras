# Arras 0.7.1 unpublished tag evidence

Tag `v0.7.1` remains at source
`0f7817eb15ee73d1d62eb75c7fe87caa3aa1aa65`, annotated object
`60021573c9b62c362c3ddb5686ab30647c597d7e`. No GitHub Release, PyPI or npm
artifact was published for this version.

[Release 41561152998](https://github.com/DocumentDrivenDX/arras/actions/runs/41561152998)
passed 203 hosted Linux/PostgreSQL 18.6 native tests and 3,840 default Python
tests. The source run skipped two installed-wheel tests and deselected the 203
native cases. Ruff, format, strict Pyright and the official UMF vector gate
passed. The build then stopped at its exact-wheel hash guard.

The locally qualified Mac wheel was `1ef8396a487cf737b81918df6f792d57474dadaa397ae9c7729a847defa5100f`.
The captured Linux wheel was `c999729cd1ae96df5e5fd40b608faeefeb89d58f4f8f3eb4ac55e7120586ce09`.
[Producer comparison 41563181620](https://github.com/DocumentDrivenDX/arras/actions/runs/41563181620)
reproduced the same Linux bytes with Node 24.22.1/npm 11.19.1 and Node
26.12.1/npm 11.20.0. Both wheels contain 188 members; only the carried npm gzip
archive and its `RECORD` entry differ. The entire decompressed npm tar archive
is byte-identical, including all 323 members, order and metadata. The safe
[correspondence receipt](producer-correspondence.json) binds the exact hashes.

[Same-input reproduction 41567382608](https://github.com/DocumentDrivenDX/arras/actions/runs/41567382608)
recompresses the retained tar with level 9 and npm's portable gzip header. The
observed Mac Node zlib 1.2.12 recreates the original Mac archive exactly; the
official Linux Node 24/26 bundled 1.3.2.1-motley builds recreate the Linux
archive exactly. The [root-cause summary](archive-root-cause.json), complete
[wheel ZIP map](wheel-member-map.json), [npm tar map](npm-member-map.json), and
three gzip reproduction receipts retain both encoding outputs and toolchains.
ZIP timestamps, permissions, flags and extra fields match; the remaining ZIP
differences are npm/RECORD sizes and CRCs plus following member offsets. No
unexpected source, JavaScript, CSS, export or asset content was normalized away.

[Captured-artifact verification 41563653335](https://github.com/DocumentDrivenDX/arras/actions/runs/41563653335)
passed source-wheel/sdist-rebuild equality and fresh installed consumers for the
actual Linux wheel. Independent Mac verification also rebuilt that Linux sdist
to the same wheel, passed fresh source/rebuilt-wheel consumers, and passed
139 ordered UMF and 139 fresh-empty Registry comparisons plus all 16 controls.
These results do not close the release: the doctor verifier then could not
install the tagged extension-host example, which still required
`arras==0.7.0`, alongside the exact 0.7.1 candidate. Its downstream consumer gate
has the same incompatible exact dependency.

The successor corrects the source/example version pins and selects its digest
only after actual Linux artifact qualification. The original tag and failed
run remain unchanged. No public-install, managed alias, or new Mac-native
qualification is claimed for this unpublished attempt.
