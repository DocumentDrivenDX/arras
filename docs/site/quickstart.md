# Quickstart

These steps run in CI against every built wheel (`scripts/smoke_installed.py`).

```bash
python -m venv .venv && . .venv/bin/activate
pip install "arras[devhost]"
arras --version              # arras @VERSION@
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
