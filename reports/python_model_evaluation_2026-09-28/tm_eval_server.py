from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PORT = 8765

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != '/__save_tm_predictions':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if length < 2 or length > 5_000_000:
            self.send_error(400, 'Invalid result size')
            return
        payload = json.loads(self.rfile.read(length).decode('utf-8'))
        if payload.get('source') != 'holdout_test' or len(payload.get('rows', [])) != 225:
            self.send_error(400, 'Expected 225 holdout test predictions')
            return
        (OUT / 'teachable_machine_test_predictions.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
        body = b'Predictions saved.'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

if __name__ == '__main__':
    print(f'Serving {ROOT} on http://127.0.0.1:{PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
