import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent
theme = root / 'features/light/theme-manifest.json'
assert theme.is_file()
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
url = f'http://127.0.0.1:{port}/'
env = {key: value for key, value in os.environ.items() if not key.startswith(('ARRAS_', 'PYTHON', 'VIRTUAL_ENV'))}
with (root / 'host.log').open('w') as log:
    process = subprocess.Popen([sys.executable, '-I', str(root / 'host.py'), str(theme), str(port)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    forced = False
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    page = response.read().decode()
                assert 'data-appearance="light"' in page
                assert '/theme-assets/' in page
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                assert process.poll() is None and time.monotonic() < deadline, 'installed stock host did not start'
                time.sleep(0.2)
        subprocess.run(['node', str(root / 'browser.mjs'), url, str(root / 'stock-theme-browser.json')], cwd=root, env=env, check=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            process.wait(timeout=10)
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1', port)) != 0, 'owned host port still accepts connections'
receipt = {'schema': 'arras.public-consumer-cleanup/1', 'status': 'passed', 'owned_host_pid': process.pid, 'owned_host_reaped': process.poll() is not None, 'forced_kill': forced, 'owned_port_closed': True, 'native_database_started': False}
(root / 'consumer-cleanup.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, sort_keys=True))
