from http.server import BaseHTTPRequestHandler, HTTPServer
import asyncio
import logging

log = logging.getLogger(__name__)

_INDEX = """<!doctype html>
<html>
    <head>
        <title>JSON-RPC Inspect</title>
        <meta charset="utf-8">
        <meta name="author" content="Marian Plivelic"</meta>
        <meta name="description" content="Inspector for my JSON-RPC implementation."</meta>
    </head>
    <body id="container">
        <p> Waiting for first update... </p>
    </body>
    <script>
        function get(url) {
            return new Promise((resolve, reject) => {
                const req = new XMLHttpRequest();
                req.open('GET', url);
                req.onload = () => req.status === 200 ? resolve(req.response) : reject(Error(req.statusText));
                req.onerror = (e) => reject(Error(`Network Error: ${e}`));
                req.send();
            });
        }

        function update() {
            console.log('Update...')
            const container = document.getElementById('container')
            get('content.html').then(data => {
                console.log('Successs')
                container.innerHTML = data
            }).catch(console.error);
        }

        setInterval(update, 5000)
    </script>
</html>
"""

_CONTENT = '<p> Hello, World! </p>'

class InspectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        log.debug('GET %s', self.path)
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            self.wfile.write(_INDEX.encode('utf-8'))
        elif self.path in ('/content.html',):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            self.wfile.write(_CONTENT.encode('utf-8'))
        else:
            log.warning('Access to invalid path %s', self.path)
            self.send_response(404)
            self.end_headers()

with HTTPServer(('localhost', 8000), InspectHandler) as server:
    sockname = server.socket.getsockname()
    log.info('Starting inspect server at %s', sockname)
    print('Starting server at http://%s:%i' % sockname)
    server.serve_forever()
