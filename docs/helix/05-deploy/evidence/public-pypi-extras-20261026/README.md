# Arras 0.6.3 public-PyPI extras evidence

The exact `arras[truss,umf]==0.6.3` install from `https://pypi.org/simple` passed on the hosted Linux x86_64 and macOS arm64 runners in [workflow run 40370325928](https://github.com/DocumentDrivenDX/arras/actions/runs/40370325928). The release source is commit `81d560310f46f1d2c105e6635d70b0eeb97d4684`, tag `v0.6.3` (tag object `04af6523b7cba0388bb4848215078f9f30cc8575`), and publisher driver commit `dab5884ec45b5e82b9908ad540e8cb67960f6bba`. The Arras wheel SHA-256 is `ef8dec70d8e0089e776166303bc622b573825f2a4e071791a316b58e22a40d0d`.

The hosted Linux x86_64 / CPython 3.11.17 job installed 19 selected distributions from `files.pythonhosted.org`; all report entries were non-direct URL installs, no installed direct-URL references were found, `pip check` passed, and Arras import/doctor, Truss import, Weft import/support, and UMF document admission passed. Truss `0.0.50`, UMF `0.10.0`, and Weft `0.4.51` matched their qualified GitHub release asset digests for Linux x86_64. Raw Linux receipts are under [linux-x86_64](linux-x86_64/). The source artifact was `12675076918` with ZIP SHA-256 `7cbd539d2f6ff929e0550c569b9135f520eff2c31f5d75ca107dff3a9a8120bc`.

The hosted macOS arm64 / CPython 3.11.9 job `121757573895` also passed those checks, including the platform-specific Weft `0.4.51` digest. Its raw report, qualification, publication receipt and postflight are under [macos-arm64](macos-arm64/). The artifact was `12679008357` with ZIP SHA-256 `dbb42ea10f8f23482b5cc993eb8e7f58aded05bbb757ddb831120c91de9f4d69`.

A separate local macOS arm64 install record remains under [local-macos-arm64](local-macos-arm64/local-extras-verification.json) as supplemental evidence. It is not used to replace the hosted macOS result. [verification.json](verification.json) records both hosted artifact digests, member and report hashes, exact installed dependency pins, and the preserved local record.

This evidence qualifies only the exact 0.6.3 extras install on the named Linux x86_64 and macOS arm64 CI runners. It does not qualify Windows, database-backed behavior, or a native/provider campaign.
