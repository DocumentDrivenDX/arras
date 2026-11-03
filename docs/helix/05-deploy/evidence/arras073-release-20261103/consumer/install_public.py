import os, subprocess
from pathlib import Path
root = Path(__file__).resolve().parent
identity = root / "release-identity.json"
assert identity.is_file(), "actual immutable release identity must be bound before public install"
env = {k:v for k,v in os.environ.items() if not k.upper().startswith(("PIP_", "UV_", "PYTHON", "ARRAS_", "NPM_CONFIG_")) and k != "VIRTUAL_ENV"}
env["PIP_CONFIG_FILE"] = os.devnull
subprocess.run([str(root / "venv/bin/python"), "-I", "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--no-cache-dir", "--index-url", "https://pypi.org/simple", "--report", str(root / "pip-report.json"), "arras[devhost,truss,umf]==0.7.3"], cwd=root, env=env, check=True)
subprocess.run([str(root / "venv/bin/python"), "-I", "-m", "pip", "check"], cwd=root, env=env, check=True)
subprocess.run(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", "--registry", "https://registry.npmjs.org", "--cache", str(root / "empty-public-npm-cache"), "--userconfig", str(root / "empty-user.npmrc"), "--globalconfig", str(root / "empty-global.npmrc")], cwd=root, env=env, check=True)
