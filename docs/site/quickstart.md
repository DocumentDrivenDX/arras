# Quickstart

Use Python 3.11, the version tested in CI. The release workflow checks the installed wheel with `scripts/smoke_installed.py`.

To explore a sample graph in your browser, start with the [Graph Browser walkthrough](graph-browser.md).

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install "arras[devhost]"
arras --version
arras doctor                 # prints a JSON report with "ok": true
arras devhost --port 8765    # open http://127.0.0.1:8765
```

`arras devhost` serves the console over fake data on loopback only. To serve a UMF module of your own, pass
`--module MODULE.umf.json --seed SEED.json`; the repository's
[examples](https://github.com/DocumentDrivenDX/arras/tree/main/examples) show the format.

With the Truss adapter and the official UMF reader:

```bash
pip install "arras[truss,umf]"
```

See the [README](https://github.com/DocumentDrivenDX/arras#readme) for mounting Arras in a host application.
