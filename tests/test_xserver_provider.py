"""
Tests for XServerProvider
"""

from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from octodns.zone import Zone

from octodns_xserver import XServerClientNotFound, XServerProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ZONE_NAME = 'example.com.'
DOMAIN = 'example.com'

RAW_RECORDS = [
    # A (apex, 2 values)
    {'id': 1, 'domain': DOMAIN, 'host': '@',
     'type': 'A', 'content': '203.0.113.1', 'ttl': 3600, 'priority': None},
    {'id': 2, 'domain': DOMAIN, 'host': '@',
     'type': 'A', 'content': '203.0.113.2', 'ttl': 3600, 'priority': None},
    # A (www)
    {'id': 3, 'domain': DOMAIN, 'host': 'www',
     'type': 'A', 'content': '203.0.113.1', 'ttl': 3600, 'priority': None},
    # AAAA
    {'id': 4, 'domain': DOMAIN, 'host': 'www',
     'type': 'AAAA', 'content': '2001:db8::1', 'ttl': 3600, 'priority': None},
    # CNAME
    {'id': 5, 'domain': DOMAIN, 'host': 'mail',
     'type': 'CNAME', 'content': 'mail.xserver.ne.jp.',
     'ttl': 3600, 'priority': None},
    # MX (2 values)
    {'id': 6, 'domain': DOMAIN, 'host': '@',
     'type': 'MX', 'content': 'mx1.example.com.',
     'ttl': 3600, 'priority': 10},
    {'id': 7, 'domain': DOMAIN, 'host': '@',
     'type': 'MX', 'content': 'mx2.example.com.',
     'ttl': 3600, 'priority': 20},
    # TXT (SPF)
    {'id': 8, 'domain': DOMAIN, 'host': '@',
     'type': 'TXT', 'content': 'v=spf1 include:xserver.ne.jp ~all',
     'ttl': 3600, 'priority': None},
    # TXT (DMARC)
    {'id': 9, 'domain': DOMAIN, 'host': '_dmarc',
     'type': 'TXT', 'content': 'v=DMARC1; p=none',
     'ttl': 3600, 'priority': None},
    # SRV
    {'id': 10, 'domain': DOMAIN, 'host': '_sip._tcp',
     'type': 'SRV', 'content': '20 5060 sip.example.com.',
     'ttl': 3600, 'priority': 10},
    # CAA
    {'id': 11, 'domain': DOMAIN, 'host': '@',
     'type': 'CAA', 'content': '0 issue "letsencrypt.org"',
     'ttl': 3600, 'priority': None},
    # Unsupported type (should be skipped)
    {'id': 12, 'domain': DOMAIN, 'host': 'ns1',
     'type': 'NS', 'content': 'ns1.xserver.ne.jp.',
     'ttl': 3600, 'priority': None},
]


def _make_provider(**kwargs):
    """Create an XServerProvider with a mocked XServerClient."""
    with patch('octodns_xserver.XServerClient'):
        provider = XServerProvider(
            'test',
            api_key='test-key',
            servername='xs123456.xsrv.jp',
            **kwargs,
        )
    return provider


# ---------------------------------------------------------------------------
# Tests: populate()
# ---------------------------------------------------------------------------

class TestXServerProviderPopulate(TestCase):

    def setUp(self):
        self.provider = _make_provider()
        self.provider._client.list_records = MagicMock(
            return_value=RAW_RECORDS
        )

    def _populated_zone(self):
        zone = Zone(ZONE_NAME, [])
        self.provider.populate(zone)
        return zone

    def test_populate_returns_true_when_zone_exists(self):
        zone = Zone(ZONE_NAME, [])
        result = self.provider.populate(zone)
        self.assertTrue(result)

    def test_populate_returns_false_when_zone_not_found(self):
        self.provider._client.list_records.side_effect = (
            XServerClientNotFound('not found')
        )
        zone = Zone(ZONE_NAME, [])
        result = self.provider.populate(zone)
        self.assertFalse(result)

    def test_populate_passes_domain_without_trailing_dot(self):
        zone = Zone(ZONE_NAME, [])
        self.provider.populate(zone)
        self.provider._client.list_records.assert_called_once_with(DOMAIN)

    def test_populate_caches_raw_records(self):
        zone = Zone(ZONE_NAME, [])
        self.provider.populate(zone)
        self.assertIn(ZONE_NAME, self.provider._raw_cache)
        self.assertEqual(
            len(self.provider._raw_cache[ZONE_NAME]), len(RAW_RECORDS)
        )

    def test_populate_A_apex_multi_value(self):
        zone = self._populated_zone()
        record = zone.records.pop()
        a_records = [r for r in zone.records if r._type == 'A' and r.name == '']
        # apex A record
        apex_a = next(
            (r for r in zone.records if r._type == 'A' and r.name == ''), None
        )
        self.assertIsNotNone(apex_a)
        self.assertIn('203.0.113.1', apex_a.values)
        self.assertIn('203.0.113.2', apex_a.values)

    def test_populate_MX(self):
        zone = self._populated_zone()
        mx = next(
            (r for r in zone.records if r._type == 'MX'), None
        )
        self.assertIsNotNone(mx)
        self.assertEqual(len(mx.values), 2)
        preferences = {v.preference for v in mx.values}
        self.assertEqual(preferences, {10, 20})

    def test_populate_TXT_dmarc(self):
        zone = self._populated_zone()
        dmarc = next(
            (r for r in zone.records
             if r._type == 'TXT' and r.name == '_dmarc'), None
        )
        self.assertIsNotNone(dmarc)
        self.assertIn('v=DMARC1; p=none', dmarc.values)

    def test_populate_CNAME_has_trailing_dot(self):
        zone = self._populated_zone()
        cname = next(
            (r for r in zone.records if r._type == 'CNAME'), None
        )
        self.assertIsNotNone(cname)
        self.assertTrue(cname.value.endswith('.'))

    def test_populate_SRV(self):
        zone = self._populated_zone()
        srv = next(
            (r for r in zone.records if r._type == 'SRV'), None
        )
        self.assertIsNotNone(srv)
        v = srv.values[0]
        self.assertEqual(v.priority, 10)
        self.assertEqual(v.weight, 20)
        self.assertEqual(v.port, 5060)

    def test_populate_CAA(self):
        zone = self._populated_zone()
        caa = next(
            (r for r in zone.records if r._type == 'CAA'), None
        )
        self.assertIsNotNone(caa)
        v = caa.values[0]
        self.assertEqual(v.flags, 0)
        self.assertEqual(v.tag, 'issue')
        self.assertEqual(v.value, 'letsencrypt.org')

    def test_populate_skips_unsupported_type(self):
        zone = self._populated_zone()
        ns_records = [r for r in zone.records if r._type == 'NS']
        self.assertEqual(ns_records, [])


# ---------------------------------------------------------------------------
# Tests: _apply()
# ---------------------------------------------------------------------------

class TestXServerProviderApply(TestCase):

    def setUp(self):
        self.provider = _make_provider()
        self.provider._client.list_records = MagicMock(
            return_value=RAW_RECORDS
        )
        self.provider._client.create_record = MagicMock(
            return_value={'id': 99}
        )
        self.provider._client.delete_record = MagicMock(return_value=None)

        # Pre-populate so _raw_cache is filled
        self.zone = Zone(ZONE_NAME, [])
        self.provider.populate(self.zone)

    def _make_desired_zone(self):
        """Return a fresh desired zone with the same name."""
        return Zone(ZONE_NAME, [])

    # --- Create ---

    def test_apply_create_A(self):
        from octodns.record import Record
        from octodns.record.change import Create

        desired = self._make_desired_zone()
        new_record = Record.new(
            desired, 'new',
            {'type': 'A', 'ttl': 3600, 'values': ['1.2.3.4', '5.6.7.8']},
        )
        desired.add_record(new_record)

        plan = MagicMock()
        plan.desired = desired
        plan.changes = [Create(new_record)]

        self.provider._apply(plan)

        # Should call create_record twice (one per IP)
        self.assertEqual(self.provider._client.create_record.call_count, 2)
        calls = self.provider._client.create_record.call_args_list
        payloads = [c[0][1] for c in calls]
        contents = {p['content'] for p in payloads}
        self.assertEqual(contents, {'1.2.3.4', '5.6.7.8'})
        for p in payloads:
            self.assertEqual(p['host'], 'new')
            self.assertEqual(p['type'], 'A')
            self.assertEqual(p['ttl'], 3600)

    def test_apply_create_MX(self):
        from octodns.record import Record
        from octodns.record.change import Create

        desired = self._make_desired_zone()
        new_record = Record.new(
            desired, '',
            {'type': 'MX', 'ttl': 3600,
             'values': [{'preference': 10, 'exchange': 'mail.example.com.'}]},
        )
        desired.add_record(new_record)

        plan = MagicMock()
        plan.desired = desired
        plan.changes = [Create(new_record)]

        self.provider._apply(plan)
        self.provider._client.create_record.assert_called_once()
        _, xr = self.provider._client.create_record.call_args[0]
        self.assertEqual(xr['type'], 'MX')
        self.assertEqual(xr['priority'], 10)
        self.assertEqual(xr['content'], 'mail.example.com.')
        self.assertEqual(xr['host'], '@')

    # --- Delete ---

    def test_apply_delete_removes_all_matching_records(self):
        from octodns.record.change import Delete

        # apex A record has ids 1 and 2
        existing_a = next(
            r for r in self.zone.records if r._type == 'A' and r.name == ''
        )

        plan = MagicMock()
        plan.desired = self._make_desired_zone()
        plan.changes = [Delete(existing_a)]

        self.provider._apply(plan)

        deleted_ids = {
            c[0][0]
            for c in self.provider._client.delete_record.call_args_list
        }
        self.assertIn(1, deleted_ids)
        self.assertIn(2, deleted_ids)

    # --- Update ---

    def test_apply_update_deletes_old_then_creates_new(self):
        from octodns.record import Record
        from octodns.record.change import Update

        existing_a = next(
            r for r in self.zone.records if r._type == 'A' and r.name == 'www'
        )
        desired = self._make_desired_zone()
        new_a = Record.new(
            desired, 'www',
            {'type': 'A', 'ttl': 3600, 'values': ['10.0.0.1']},
        )
        desired.add_record(new_a)

        plan = MagicMock()
        plan.desired = desired
        plan.changes = [Update(existing_a, new_a)]

        self.provider._apply(plan)

        # Old record (id=3) should be deleted
        self.provider._client.delete_record.assert_called_once_with(3)
        # New record should be created
        self.provider._client.create_record.assert_called_once()
        _, xr = self.provider._client.create_record.call_args[0]
        self.assertEqual(xr['content'], '10.0.0.1')


# ---------------------------------------------------------------------------
# Tests: host / name / domain conversion
# ---------------------------------------------------------------------------

class TestXServerProviderConversions(TestCase):

    def test_host_to_name_apex(self):
        self.assertEqual(XServerProvider._host_to_name('@'), '')

    def test_host_to_name_subdomain(self):
        self.assertEqual(XServerProvider._host_to_name('www'), 'www')

    def test_name_to_host_apex(self):
        self.assertEqual(XServerProvider._name_to_host(''), '@')

    def test_name_to_host_subdomain(self):
        self.assertEqual(XServerProvider._name_to_host('www'), 'www')

    def test_domain_from_zone(self):
        self.assertEqual(
            XServerProvider._domain_from_zone('example.com.'), 'example.com'
        )
