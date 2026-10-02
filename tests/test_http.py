import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from app import make_server, csv_export


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.folder.name) / 'lab.sqlite')
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        # Bootstrap normally redirects to the clean URL; retain the session cookie.
        import http.cookiejar
        self.jar = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.client.open(self.url + '/?access=' + self.server.access_token).close()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        self.folder.cleanup()

    def request(self, path, data=None, headers=None):
        h = {'Content-Type': 'application/json'} if data is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(self.url + path, json.dumps(data).encode() if data is not None else None, h)
        with self.client.open(req) as response:
            return json.load(response)

    def test_session_host_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url + '/api/studies')
        self.assertEqual(error.exception.code, 403)
        error.exception.close()
        for headers in ({'Origin': 'https://example.com'}, {'Host': 'example.com'}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/demo', {}, headers)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        self.assertEqual(self.request('/api/studies')['studies'], [])

    def test_export_roundtrip_and_formula_neutralization(self):
        study = self.request('/api/demo', {})
        bundle = self.request('/api/studies/' + study['id'] + '/export')
        self.assertTrue(self.request('/api/verify', bundle)['valid'])
        bundle['events'][1]['payload']['prompt'] = 'modified'
        self.assertFalse(self.request('/api/verify', bundle)['valid'])
        full = self.request('/api/studies/' + study['id'])
        full['trials'][0]['observation']['notes'] = '=HYPERLINK("evil")'
        exported = csv_export(full)
        self.assertIn("'=HYPERLINK", exported.decode('utf-8-sig') if isinstance(exported, bytes) else exported)

    def test_bad_input_is_recoverable(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/simulate', {'steps': -1})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        self.assertIn('agents', self.request('/api/simulate', {'seed': 42, 'steps': 20, 'reverse_at': 10}))
