"""Synthetic transport and provider compatibility tests; live checks are separate."""
import json
import os
import unittest
from unittest.mock import patch

import requests

from app.services import parallel_search as parallel
from app.services.tavily_search import (
    TavilySearchError, format_search_context, search_short_drama, search_story_context,
)


def response(data, *, sse=False, status=200, headers=None):
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = ("event: message\r\ndata: " + json.dumps(data, ensure_ascii=False) + "\r\n\r\n" if sse else json.dumps(data)).encode()
    r.headers['Content-Type'] = 'text/event-stream' if sse else 'application/json'
    return r


RESULT = {'results': [{'url': 'https://example.org/plot', 'title': '剧情', 'excerpts': ['Edmond escapes prison.', 'He seeks revenge.']}]}


class ParallelSearchTests(unittest.TestCase):
    def transport(self, *, result=None, tools=None, status=200, fail=None):
        self.requests = []

        def send(adapter, request, **kwargs):
            self.requests.append(request)
            if fail:
                raise fail
            body = json.loads(request.body) if request.body else {}
            method = body.get('method')
            if request.method == 'DELETE' or method == 'notifications/initialized':
                return response({}, status=202)
            if method == 'initialize':
                return response({'id': 1, 'result': {'protocolVersion': parallel.PROTOCOL_VERSION}}, sse=True, headers={'Mcp-Session-Id': 'synthetic'})
            if method == 'tools/list':
                return response({'id': 2, 'result': tools if tools is not None else {'tools': [{'name': 'web_search'}]}})
            return response({'id': 3, 'result': result if result is not None else {'structuredContent': RESULT}}, sse=True, status=status)

        return patch.object(requests.adapters.HTTPAdapter, 'send', send)

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_anonymous_lifecycle_and_all_final_headers(self):
        with self.transport():
            data = search_short_drama('Monte Cristo')
        self.assertEqual('parallel', data['provider'])
        self.assertIn('Edmond escapes', format_search_context(data))
        self.assertIn('# Parallel', format_search_context(data))
        self.assertIn('短剧', data['query'])
        self.assertEqual(['POST'] * 4 + ['DELETE'], [r.method for r in self.requests])
        for r in self.requests:
            self.assertEqual(parallel.USER_AGENT, r.headers['User-Agent'])
            self.assertNotIn('Authorization', r.headers)
        self.assertEqual(parallel.PROTOCOL_VERSION, self.requests[-1].headers['MCP-Protocol-Version'])

    def test_text_content_and_result_limit(self):
        with self.transport(result={'content': [{'type': 'text', 'text': json.dumps(RESULT)}]}):
            data = search_story_context('Monte Cristo', provider='parallel', max_results=1)
        self.assertEqual(1, len(data['results']))
        self.assertEqual('Edmond escapes prison.\n\nHe seeks revenge.', data['results'][0]['content'])

    def test_tool_errors_malformed_and_http_failures(self):
        for result in [{'isError': True}, {'structuredContent': []}, {'structuredContent': {'results': 'bad'}},
                       {'structuredContent': {'results': [{}]}}, {'content': None}, {'content': [{'type': 'text', 'text': 'invalid'}]}]:
            with self.subTest(result=result), self.transport(result=result), self.assertRaises(TavilySearchError):
                search_story_context('test', provider='parallel')
            self.assertEqual('DELETE', self.requests[-1].method)
        for status in [302, 401, 429, 500]:
            with self.subTest(status=status), self.transport(status=status), self.assertRaises(TavilySearchError):
                search_story_context('test', provider='parallel')
            self.assertEqual(5, len(self.requests))

    def test_discovery_and_network_failure(self):
        for tools in [{}, {'tools': None}, {'tools': [{'name': 'other'}]}]:
            with self.transport(tools=tools), self.assertRaises(TavilySearchError):
                search_story_context('test', provider='parallel')
        with self.transport(fail=requests.Timeout()), self.assertRaises(TavilySearchError):
            search_story_context('test', provider='parallel')

    def test_json_rpc_validation_and_utf8_sse(self):
        r = response({'id': 7, 'result': {'text': '剧情'}}, sse=True)
        self.assertEqual('剧情', parallel._rpc_result(r, 7)['text'])
        for body in [{'id': 8, 'result': {}}, {'id': 7, 'error': {'code': -1}}, [], {'id': 7, 'result': None}]:
            with self.assertRaises(TavilySearchError):
                parallel._rpc_result(response(body), 7)
        r._content = b'data: not json\n\n'
        with self.assertRaises(TavilySearchError):
            parallel._rpc_result(r, 7)

    @patch.dict(os.environ, {}, clear=True)
    def test_explicit_missing_disabled_unknown_and_empty_never_connect(self):
        with patch('requests.sessions.Session.request') as send:
            for provider in ['tavily', 'disabled', 'unknown']:
                with self.assertRaises(TavilySearchError):
                    search_story_context('test', provider=provider)
            with self.assertRaises(TavilySearchError):
                search_story_context(' ', provider='parallel')
        send.assert_not_called()

    def test_tavily_configured_env_explicit_and_bad_key_never_fall_back(self):
        for provider, key, env in [('auto', 'saved-key', ''), ('tavily', 'saved-key', ''), ('auto', None, 'env-key')]:
            with self.subTest(provider=provider, env=bool(env)), patch.dict(os.environ, {'TAVILY_API_KEY': env}), patch('requests.post') as post, patch.object(parallel, 'search_parallel_context') as fallback:
                post.return_value = response({'query': 'test', 'answer': 'answer', 'results': []})
                self.assertIn('# Tavily', format_search_context(search_story_context('test', key, provider=provider)))
                self.assertEqual('Bearer ' + (key or env), post.call_args.kwargs['headers']['Authorization'])
                self.assertEqual('basic', post.call_args.kwargs['json']['search_depth'])
                post.return_value = response({}, status=401)
                with self.assertRaises(TavilySearchError):
                    search_story_context('test', key, provider=provider)
                post.side_effect = requests.Timeout()
                with self.assertRaises(TavilySearchError):
                    search_story_context('test', key, provider=provider)
                fallback.assert_not_called()

    def test_explicit_parallel_ignores_tavily_key(self):
        with self.transport(), patch('requests.post') as tavily:
            self.assertEqual('parallel', search_story_context('test', 'bad-key', provider='parallel')['provider'])
        tavily.assert_not_called()
