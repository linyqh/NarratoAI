"""Local HTTP fixtures, not recorded Parallel responses or live provider tests."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests

from app.services import parallel_search as parallel
from app.services.tavily_search import TavilySearchError, search_story_context


class ParallelOpenStreamTests(unittest.TestCase):
    def run_workflow(self, *, ending='\n', rpc_error=False, sse=True):
        release = threading.Event()
        returned = threading.Event()
        flushed = threading.Event()
        requests_seen = []
        responses = []
        outcome = {}
        excerpt = 'Edmond\u0085escapes\u2028prison\u2029and returns.'

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                method = body['method']
                requests_seen.append((method, self.headers.get('User-Agent')))
                if method == 'notifications/initialized':
                    self.send_response(202)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if method == 'initialize':
                    result = {'protocolVersion': parallel.PROTOCOL_VERSION}
                elif method == 'tools/list':
                    result = {'tools': [{'name': 'web_search'}]}
                else:
                    result = {'structuredContent': {'results': [{
                        'url': 'https://example.org/plot', 'excerpts': [excerpt],
                    }]}}
                message = {'jsonrpc': '2.0', 'id': body['id'], 'result': result}
                if rpc_error and method == 'tools/call':
                    message = {'jsonrpc': '2.0', 'id': body['id'], 'error': {'code': -32000, 'message': 'fixture error'}}
                self.send_response(200)
                if method == 'initialize':
                    self.send_header('Mcp-Session-Id', 'local-fixture')
                if sse:
                    self.send_header('Content-Type', 'Text/Event-Stream ; charset=UTF-8')
                    self.end_headers()
                    # Small flushed events have no Content-Length and no EOF yet.
                    wire = ': heartbeat' + ending * 2
                    wire += 'data: {"method":"notifications/message"}' + ending * 2
                    wire += 'data: {"id":999,"result":{}}' + ending * 2
                    # Several data lines, with literal UTF-8 Unicode separators.
                    wire += ending.join('data: ' + line for line in json.dumps(
                        message, ensure_ascii=False, indent=2
                    ).split('\n')) + ending * 2
                    # Must return at the matching ID, without parsing later events.
                    wire += 'data: not json' + ending * 2
                    self.wfile.write(wire.encode('utf-8'))
                    self.wfile.flush()
                    flushed.set()
                    release.wait(10)
                    self.close_connection = True
                else:
                    data = json.dumps(message, ensure_ascii=False).encode('utf-8')
                    self.send_header('Content-Type', 'Application/JSON ; charset=UTF-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    self.wfile.flush()
                    flushed.set()

            def do_DELETE(self):
                requests_seen.append(('DELETE', self.headers.get('User-Agent')))
                self.send_response(200)
                self.send_header('Content-Length', '0')
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        serving.start()
        original = requests.adapters.HTTPAdapter.send

        def observe(adapter, request, **kwargs):
            r = original(adapter, request, **kwargs)
            responses.append((r, kwargs.get('stream')))
            return r

        def client():
            try:
                outcome['result'] = search_story_context('Monte Cristo', provider='parallel', timeout=3)
            except Exception as exc:
                outcome['error'] = exc
            finally:
                returned.set()

        # Only loopback bypasses the sandbox proxy for this local fixture.
        with patch.object(parallel, 'MCP_URL', f'http://127.0.0.1:{server.server_port}/mcp'), patch.dict(
            os.environ, {'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost', 'TAVILY_API_KEY': ''}
        ), patch.object(requests.adapters.HTTPAdapter, 'send', observe):
            worker = threading.Thread(target=client, daemon=True)
            worker.start()
            try:
                self.assertTrue(flushed.wait(2), 'fixture did not flush a complete RPC event')
                self.assertTrue(returned.wait(2), 'client waited for EOF after a complete RPC event')
                self.assertFalse(release.is_set(), 'server must still hold SSE connections open')
                if rpc_error:
                    self.assertIsInstance(outcome.get('error'), TavilySearchError)
                    self.assertIn('MCP 返回错误', str(outcome['error']))
                else:
                    self.assertNotIn('error', outcome)
                    self.assertEqual(excerpt, outcome['result']['results'][0]['content'])
                self.assertEqual(
                    ['initialize', 'notifications/initialized', 'tools/list', 'tools/call', 'DELETE'],
                    [method for method, _ in requests_seen],
                )
                self.assertTrue(all(ua == parallel.USER_AGENT for _, ua in requests_seen))
                self.assertTrue(all(stream for _, stream in responses))
                self.assertTrue(all(r.raw.closed for r, _ in responses))
                if sse:
                    self.assertTrue(all(r._content is False for r, _ in responses))
            finally:
                release.set()
                worker.join(4)
                server.shutdown()
                server.server_close()
            self.assertFalse(worker.is_alive())

    def test_results_return_and_close_before_sse_eof(self):
        for ending in ['\n', '\r\n', '\r']:
            with self.subTest(ending=repr(ending)):
                self.run_workflow(ending=ending)

    def test_rpc_errors_return_and_cleanup_before_sse_eof(self):
        for ending in ['\n', '\r\n', '\r']:
            with self.subTest(ending=repr(ending)):
                self.run_workflow(ending=ending, rpc_error=True)

    def test_json_response_remains_supported(self):
        self.run_workflow(sse=False)
