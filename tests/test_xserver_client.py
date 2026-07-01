"""
Tests for XServerClient
"""

import json
from unittest import TestCase
from unittest.mock import MagicMock, patch, PropertyMock

from octodns_xserver import (
    XServerClient,
    XServerClientAuthError,
    XServerClientException,
    XServerClientNotFound,
    XServerClientRateLimitError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_RECORDS = [
    {
        'id': 1,
        'domain': 'example.com',
        'host': '@',
        'type': 'A',
        'content': '203.0.113.1',
        'ttl': 3600,
        'priority': None,
    },
    {
        'id': 2,
        'domain': 'example.com',
        'host': 'www',
        'type': 'A',
        'content': '203.0.113.1',
        'ttl': 3600,
        'priority': None,
    },
    {
        'id': 3,
        'domain': 'example.com',
        'host': '@',
        'type': 'MX',
        'content': 'mail.example.com.',
        'ttl': 3600,
        'priority': 10,
    },
    {
        'id': 4,
        'domain': 'example.com',
        'host': '@',
        'type': 'TXT',
        'content': 'v=spf1 include:xserver.ne.jp ~all',
        'ttl': 3600,
        'priority': None,
    },
]


def _make_response(status_code: int, body=None, headers=None):
    """Create a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = headers or {}
    if body is not None:
        mock.json.return_value = body
        mock.text = json.dumps(body)
    else:
        mock.json.side_effect = ValueError('no body')
        mock.text = ''
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestXServerClient(TestCase):

    def setUp(self):
        self.client = XServerClient(
            api_key='test-api-key',
            servername='xs123456.xsrv.jp',
        )

    # --- Initialisation ---

    def test_init_sets_servername(self):
        self.assertEqual(self.client._servername, 'xs123456.xsrv.jp')

    def test_init_sets_auth_header(self):
        headers = self.client._session.headers
        self.assertEqual(headers['Authorization'], 'Bearer test-api-key')
        self.assertEqual(headers['Content-Type'], 'application/json')

    def test_dns_url(self):
        expected = (
            'https://api.xserver.ne.jp/v1/server/xs123456.xsrv.jp/dns'
        )
        self.assertEqual(self.client._dns_url, expected)

    # --- list_records ---

    @patch('octodns_xserver.Session.request')
    def test_list_records_returns_list(self, mock_request):
        mock_request.return_value = _make_response(
            200, {'dns': FIXTURE_RECORDS}
        )
        records = self.client.list_records('example.com')
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0]['type'], 'A')

    @patch('octodns_xserver.Session.request')
    def test_list_records_passes_domain_param(self, mock_request):
        mock_request.return_value = _make_response(200, {'dns': []})
        self.client.list_records('example.com')
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['params']['domain'], 'example.com')

    @patch('octodns_xserver.Session.request')
    def test_list_records_empty_domain(self, mock_request):
        mock_request.return_value = _make_response(200, {'dns': []})
        records = self.client.list_records('empty.com')
        self.assertEqual(records, [])

    # --- create_record ---

    @patch('octodns_xserver.Session.request')
    def test_create_record_returns_created(self, mock_request):
        created = {**FIXTURE_RECORDS[0], 'id': 99}
        mock_request.return_value = _make_response(201, {'dns': created})
        result = self.client.create_record('example.com', {
            'host': '@',
            'type': 'A',
            'content': '203.0.113.1',
            'ttl': 3600,
        })
        self.assertEqual(result['id'], 99)
        self.assertEqual(result['type'], 'A')

    @patch('octodns_xserver.Session.request')
    def test_create_record_sends_domain_in_payload(self, mock_request):
        mock_request.return_value = _make_response(
            201, {'dns': FIXTURE_RECORDS[0]}
        )
        self.client.create_record('example.com', {
            'host': '@', 'type': 'A', 'content': '1.2.3.4',
        })
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['json']['domain'], 'example.com')

    # --- update_record ---

    @patch('octodns_xserver.Session.request')
    def test_update_record_uses_correct_url(self, mock_request):
        updated = {**FIXTURE_RECORDS[0], 'content': '203.0.113.2'}
        mock_request.return_value = _make_response(200, {'dns': updated})
        result = self.client.update_record(1, {'content': '203.0.113.2'})
        self.assertEqual(result['content'], '203.0.113.2')
        args, _ = mock_request.call_args
        self.assertIn('/dns/1', args[1])

    # --- delete_record ---

    @patch('octodns_xserver.Session.request')
    def test_delete_record_uses_correct_url(self, mock_request):
        mock_request.return_value = _make_response(204)
        self.client.delete_record(42)
        args, _ = mock_request.call_args
        self.assertEqual(args[0], 'DELETE')
        self.assertIn('/dns/42', args[1])

    @patch('octodns_xserver.Session.request')
    def test_delete_record_returns_none(self, mock_request):
        mock_request.return_value = _make_response(204)
        result = self.client.delete_record(1)
        self.assertIsNone(result)

    # --- Error handling ---

    @patch('octodns_xserver.Session.request')
    def test_401_raises_auth_error(self, mock_request):
        mock_request.return_value = _make_response(401)
        with self.assertRaises(XServerClientAuthError):
            self.client.list_records('example.com')

    @patch('octodns_xserver.Session.request')
    def test_403_raises_auth_error(self, mock_request):
        mock_request.return_value = _make_response(403)
        with self.assertRaises(XServerClientAuthError):
            self.client.list_records('example.com')

    @patch('octodns_xserver.Session.request')
    def test_404_raises_not_found(self, mock_request):
        mock_request.return_value = _make_response(404)
        with self.assertRaises(XServerClientNotFound):
            self.client.list_records('notexist.com')

    @patch('octodns_xserver.Session.request')
    def test_500_raises_exception(self, mock_request):
        mock_request.return_value = _make_response(
            500,
            {'error': {'code': 'SERVER_ERROR', 'message': 'Internal error'}},
        )
        with self.assertRaises(XServerClientException):
            self.client.list_records('example.com')

    @patch('octodns_xserver.sleep')
    @patch('octodns_xserver.Session.request')
    def test_429_retries_then_raises(self, mock_request, mock_sleep):
        mock_request.return_value = _make_response(
            429, headers={'Retry-After': '2'}
        )
        with self.assertRaises(XServerClientRateLimitError):
            self.client.list_records('example.com')
        # Should retry _RETRY_COUNT times
        self.assertEqual(mock_request.call_count, XServerClient._RETRY_COUNT)

    @patch('octodns_xserver.sleep')
    @patch('octodns_xserver.Session.request')
    def test_429_succeeds_on_retry(self, mock_request, mock_sleep):
        """Rate limit on first call, success on second."""
        rate_limited = _make_response(429, headers={'Retry-After': '1'})
        success = _make_response(200, {'dns': FIXTURE_RECORDS})
        mock_request.side_effect = [rate_limited, success]

        records = self.client.list_records('example.com')
        self.assertEqual(len(records), 4)
        self.assertEqual(mock_request.call_count, 2)
        mock_sleep.assert_called_once_with(1)
