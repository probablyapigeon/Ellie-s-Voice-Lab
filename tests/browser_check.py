"""Real-browser workflow check; requires Playwright and its Chromium download."""
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import make_server
from playwright.sync_api import sync_playwright


def main():
    artifacts = Path('test-artifacts'); artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        server = make_server(Path(folder) / 'lab.sqlite')
        thread = threading.Thread(target=server.serve_forever); thread.start()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/?access={server.access_token}')
                page.locator('#version').wait_for()
                page.screenshot(path=str(artifacts / 'home.png'), full_page=True)
                page.locator('#home-new').click()
                for name, value in {'title':'Browser workflow', 'subject':'Bird A', 'question':'Context choices?', 'choices':'apple\nmusic\nrest', 'criterion':'Uses the selected activity', 'max_trials':'1'}.items():
                    page.locator(f'#study-form [name="{name}"]').fill(value)
                page.locator('#study-form button[type=submit]').click()
                page.locator('#trial-form').wait_for()
                page.locator('#trial-form [name=prompt]').fill('Would you like music?')
                page.locator('#trial-form button[type=submit]').click()
                page.locator('#observation-form').wait_for()
                assert page.locator('#observation-form').get_by_text('Control predictions are locked').count() == 1
                page.locator('#observation-choice').select_option('music')
                page.locator('#observation-corroboration').select_option('yes')
                page.locator('#observation-form [name=notes]').fill('<script>alert(1)</script> observed behavior')
                page.locator('#observation-form button[type=submit]').click()
                page.locator('.analysis-controls').wait_for()
                assert page.locator('.analysis-controls tbody tr').count() == 6
                with page.expect_download() as download:
                    page.get_by_role('link', name='Export JSON', exact=True).click()
                download.value.save_as(str(artifacts / 'browser-evidence.json'))
                page.screenshot(path=str(artifacts / 'study.png'), full_page=True)
                page.locator('.nav[data-view=sandbox]').click()
                page.locator('#simulation-form button[type=submit]').click()
                page.locator('#trace-step').wait_for()
                page.locator('#trace-step').fill('40'); page.locator('#trace-step').dispatch_event('input')
                page.screenshot(path=str(artifacts / 'sandbox.png'), full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.locator('.nav[data-view=home]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
                page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
                assert not errors, errors
                browser.close()
            print('PASS: create, commit, observe, score, export, agent trace, mobile layout; no browser errors')
        finally:
            server.shutdown(); thread.join(); server.server_close()


if __name__ == '__main__':
    main()
