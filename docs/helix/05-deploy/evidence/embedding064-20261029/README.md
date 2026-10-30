# Arras 0.6.4 embedding qualification

The exact CI wheel `29139ac729e00639a8b07366ed8c64d69936bceb525d9b85bb562946f115a9b2` passed full CI, fresh macOS native qualification (64 cases, eight declared limits), and all twelve fresh managed Lakebase cases. The managed environment independently verified every installed Arras and Truss wheel member and their PEP 610 archive hashes before and after execution. A fresh read-only process verified owned cleanup and endpoint restoration without restoration mutations.

The disposable project used PostgreSQL 18.6, Truss 0.0.50 and Weft 0.4.51. Four independent ordinary OAuth actors included the human writer; a separate installer held project-only administrative privileges. API-created roles initially failed strict admission because Lakebase granted replication privilege. Recreating only the approved test roles through the documented login-only SQL provisioner satisfied the unchanged gate. No prior managed receipt qualified these bytes.

The safe JSON records bind source, wheel, harness and fixture hashes, original outcomes and scope limits. Private identity configuration, credentials and raw fault archives are excluded. Registry availability remains a later release gate.

All four temporary workspace/account service principals, their four remote
secrets and keychain entries, and the disposable project were deleted. A fresh
confirmation found every identity/keychain entry absent and project deletion
complete. One account lookup initially lagged deletion; the full recheck passed.
The earlier failed restart fixture attempt used a different wheel and is
retained only as repair history. The immutable MP-06 requirements-review digest
identifies the existing public 0.0.50 source review; the separately pinned fresh
requirements-input digest records this campaign's verified derivative. Neither
is a reused managed execution result.
