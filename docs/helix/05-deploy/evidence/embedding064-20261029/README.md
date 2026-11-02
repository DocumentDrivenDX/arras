# Arras 0.6.4 embedding qualification

The exact CI wheel `29139ac729e00639a8b07366ed8c64d69936bceb525d9b85bb562946f115a9b2` passed full CI, fresh macOS native qualification (64 cases, eight declared limits), and all twelve fresh managed Lakebase cases. The managed environment independently verified every installed Arras and Truss wheel member and their PEP 610 archive hashes before and after execution. A fresh read-only process verified owned cleanup and endpoint restoration without restoration mutations.

The disposable project used PostgreSQL 18.6, Truss 0.0.50 and Weft 0.4.51. Four independent ordinary OAuth actors included the human writer; a separate installer held project-only administrative privileges. API-created roles initially failed strict admission because Lakebase granted replication privilege. Recreating only the approved test roles through the documented login-only SQL provisioner satisfied the unchanged gate. No prior managed receipt qualified these bytes.

The safe JSON records bind source, wheel, harness and fixture hashes, original outcomes and scope limits. Private identity configuration, credentials and raw fault archives are excluded. The tagged release and anonymous public-download gate passed. Registry status is recorded below.

All four temporary workspace/account service principals, their four remote
secrets and keychain entries, and the disposable project were deleted. A fresh
confirmation found every identity/keychain entry absent and project deletion
complete. One account lookup initially lagged deletion; the full recheck passed.
The earlier failed restart fixture attempt used a different wheel and is
retained only as repair history. The immutable MP-06 requirements-review digest
identifies the existing public 0.0.50 source review; the separately pinned fresh
requirements-input digest records this campaign's verified derivative. Neither
is a reused managed execution result.

Final-source CI `40977136028` reproduced the selected wheel. Immutable tag
`v0.6.4` selects source `11be778eae8050fd5b2e8b446479e8bea081778a`; all ten gates in
[Release 40978080176](https://github.com/DocumentDrivenDX/arras/actions/runs/40978080176)
passed. The anonymous bundle verifier checked all sixteen assets, wheel-carried
npm parity and fresh installed doctor, UMF, extension host and themed browser
consumers. The release-gates, asset-inventory and original public receipts retain
these observations separately from local qualification.

Registry run `40980958496` passed PyPI exact-byte/base-install verification and
fresh isolated public-PyPI extras installs on Linux x86_64 and macOS arm64.
Both extras receipts record zero direct-URL distributions, pinned native archive
correspondence, `pip check`, installed doctor and official UMF admission. npm
accepted its OIDC upload, but its public metadata preceded the tarball: the URL
returned HTTP 404 and postflight correctly failed before a fresh install. The
original refusal is retained. Attempt two checked the now-matching existing bytes,
skipped upload and passed the fresh npm install.

[Registry run 40980958496](https://github.com/DocumentDrivenDX/arras/actions/runs/40980958496)
completed successfully on attempt two. The [publication record](registry-publication.safe.json)
binds both registry outcomes, receipt hashes, source, immutable tag and publisher
driver. Packages are available as [`arras==0.6.4`](https://pypi.org/project/arras/0.6.4/)
and [`@documentdrivendx/arras-ui@0.6.4`](https://www.npmjs.com/package/@documentdrivendx/arras-ui/v/0.6.4).
