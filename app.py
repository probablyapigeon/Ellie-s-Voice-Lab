"""Run Bird Voice Lab locally in a browser; Python 3.10+ or packaged executable."""
import argparse
import csv
import hmac
import io
import json
import os
import secrets
import sys
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from lab import Lab, LabError, VERSION, simulate, verify_export

RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def data_directory():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BirdVoiceLab'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'BirdVoiceLab'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'bird-voice-lab'


def csv_export(study):
    buffer = io.StringIO(newline='')
    columns = ['trial', 'committed_at', 'context', 'prompt', 'display_order', 'objective_target',
        'recorded_at', 'outcome', 'choice', 'corroboration', 'initiated', 'latency_seconds', 'notes', 'media_reference', 'synthetic']
    writer = csv.DictWriter(buffer, fieldnames=columns); writer.writeheader()
    def safe(value):
        value = '' if value is None else str(value)
        # Neutralize spreadsheet formula interpretation without changing JSON evidence.
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    for trial in study['trials']:
        o = trial.get('observation', {})
        row = {'trial': trial['number'], 'committed_at': trial['committed_at'], 'context': trial['context'],
            'prompt': trial['prompt'], 'display_order': ' | '.join(trial['display_order']),
            'objective_target': trial['target'], 'synthetic': study['synthetic']}
        row.update({k: o.get(k) for k in columns if k in o})
        writer.writerow({k: safe(v) for k, v in row.items()})
    return buffer.getvalue().encode('utf-8-sig')


def make_server(path, port=0):
    lab = Lab(path)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not write access tokens, prompts, or observations to logs.

        def send(self, data, status=200, content_type='application/json', filename=None, cookie=False, location=None):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            elif isinstance(data, str):
                data = data.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie: self.send_header('Set-Cookie', f'bvl_session={token}; HttpOnly; SameSite=Strict; Path=/')
            if location: self.send_header('Location', location)
            if filename: self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            expected_host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected_host:
                return False
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{expected_host}':
                return False
            try:
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                actual = cookie['bvl_session'].value if 'bvl_session' in cookie else ''
                return hmac.compare_digest(actual, token)
            except Exception:
                return False

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/' and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}':
                supplied = parse_qs(url.query).get('access', [''])[0]
                if hmac.compare_digest(supplied, token):
                    return self.send(b'', 302, cookie=True, location='/')
            if not self.authorized():
                return self.send('Open Bird Voice Lab with its launcher to start a local session.', 403, 'text/plain; charset=utf-8')
            try:
                if url.path in ('/', '/app.js', '/style.css'):
                    name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                    mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[name]
                    return self.send((RESOURCES / 'web' / name).read_bytes(), content_type=mime)
                if url.path == '/api/studies':
                    return self.send({'studies': lab.list_studies(), 'version': VERSION, 'data_directory': str(lab.path.parent)})
                parts = url.path.strip('/').split('/')
                if len(parts) >= 3 and parts[:2] == ['api', 'studies']:
                    sid = parts[2]
                    if len(parts) == 3: return self.send(lab.get_study(sid))
                    if len(parts) == 4 and parts[3] == 'export':
                        return self.send(json.dumps(lab.export_study(sid), ensure_ascii=False, indent=2),
                            content_type='application/json', filename=f'bird-voice-{sid[:8]}.json')
                    if len(parts) == 4 and parts[3] == 'csv':
                        return self.send(csv_export(lab.get_study(sid)), content_type='text/csv; charset=utf-8', filename=f'bird-voice-{sid[:8]}.csv')
                    if len(parts) == 4 and parts[3] == 'receipt':
                        return self.send(lab.export_study(sid)['receipt'], filename=f'receipt-{sid[:8]}.json')
                return self.send({'error': 'Not found.'}, 404)
            except LabError as error:
                self.send({'error': str(error)}, 400)

        def do_POST(self):
            if not self.authorized(): return self.send({'error': 'Local session authorization required.'}, 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send({'error': 'Expected JSON.'}, 415)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000: return self.send({'error': 'Request size is invalid.'}, 413)
                data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
                if not isinstance(data, dict): raise LabError('Expected a JSON object.')
                path = urlsplit(self.path).path
                if path == '/api/studies': return self.send(lab.create_study(data), 201)
                if path == '/api/demo': return self.send(lab.demo(), 201)
                if path == '/api/simulate': return self.send(simulate(data))
                if path == '/api/verify': return self.send(verify_export(data))
                if path == '/api/shutdown':
                    self.send({'stopped': True}); threading.Thread(target=self.server.shutdown, daemon=True).start(); return
                parts = path.strip('/').split('/')
                if len(parts) == 4 and parts[:2] == ['api', 'studies']:
                    if parts[3] == 'trials': return self.send(lab.commit_trial(parts[2], data), 201)
                    if parts[3] == 'close': return self.send(lab.close_study(parts[2]))
                if len(parts) == 6 and parts[:2] == ['api', 'studies'] and parts[3] == 'trials' and parts[5] == 'observation':
                    return self.send(lab.record_observation(parts[2], parts[4], data))
                self.send({'error': 'Not found.'}, 404)
            except (LabError, ValueError, TypeError, KeyError) as error:
                self.send({'error': str(error)}, 400)
            except Exception:
                self.send({'error': 'The request could not be saved. Your prior records are preserved.'}, 500)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.access_token = token
    return server


def main():
    parser = argparse.ArgumentParser(description='Bird Voice Lab · local research notebook')
    parser.add_argument('--data-dir', type=Path, default=data_directory())
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--verify', type=Path, help='Verify a JSON evidence export without starting the app')
    args = parser.parse_args()
    if args.verify:
        try:
            report = verify_export(json.loads(args.verify.read_text(encoding='utf-8-sig')))
        except (OSError, ValueError) as error:
            report = {'valid': False, 'errors': [str(error)]}
        print(json.dumps(report, indent=2)); return 0 if report['valid'] else 1
    server = make_server(args.data_dir / 'lab.sqlite', args.port)
    address = f'http://127.0.0.1:{server.server_port}/'
    print(f'Bird Voice Lab {VERSION}\nRecords: {args.data_dir}\nUse Quit in the app, or close this window to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(address + '?access=' + server.access_token)
    else:
        print('Open this private session URL on this computer: ' + address + '?access=' + server.access_token, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
