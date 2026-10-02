"""Exercise the built executable with real browser assets and isolated records."""
import json
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright


exe = Path('dist/BirdVoiceLab/BirdVoiceLab.exe').resolve()
with tempfile.TemporaryDirectory() as folder:
    process = subprocess.Popen([str(exe), '--no-browser', '--data-dir', folder],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    try:
        url = None
        for _ in range(5):
            line = process.stdout.readline()
            if 'http://127.0.0.1:' in line:
                url = line[line.index('http://'):].strip(); break
            if not line: break
        assert url, 'Executable failed to publish its local session URL'
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url)
            page.locator('#demo').click()
            page.locator('.analysis-controls').wait_for()
            assert page.locator('.analysis-controls tbody tr').count() == 10
            with page.expect_download() as download:
                page.get_by_role('link', name='Export JSON', exact=True).click()
            evidence = Path(folder) / 'evidence.json'; download.value.save_as(str(evidence))
            assert json.loads(evidence.read_text(encoding='utf-8'))['software_version'] == '0.2.0'
            page.locator('.nav[data-view=sandbox]').click()
            page.locator('#simulation-form button[type=submit]').click()
            page.locator('#trace-step').wait_for()
            assert page.locator('.agent-grid article').count() == 5
            assert page.get_by_role('heading', name='Deterministic learner', exact=True).count() == 1
            page.locator('#quit').click()
            process.wait(timeout=10)
            assert process.returncode == 0 and not errors, (process.returncode, errors)
            browser.close()
        result = subprocess.run([str(exe), '--verify', str(evidence)], capture_output=True, text=True)
        assert result.returncode == 0 and json.loads(result.stdout)['valid'], result.stderr
        value = json.loads(evidence.read_text(encoding='utf-8'))
        value['events'][1]['payload']['prompt'] = 'tampered'
        evidence.write_text(json.dumps(value), encoding='utf-8')
        assert subprocess.run([str(exe), '--verify', str(evidence)], capture_output=True).returncode == 1
        print('PASS: packaged Windows executable serves assets, demo, exports, simulation, quit and integrity checks')
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
