"""
octodns_xserver
~~~~~~~~~~~~~~~

XServer DNS provider for octoDNS.

XServer API documentation:
    https://developer.xserver.ne.jp/api/server/
"""

from logging import getLogger
from time import sleep

from requests import Session
from requests.exceptions import RequestException

__version__ = '0.0.1'
__all__ = ['XServerProvider']


class XServerClientException(Exception):
    """Base exception for XServerClient errors."""
    pass


class XServerClientNotFound(XServerClientException):
    """Raised when a requested resource is not found (HTTP 404)."""
    pass


class XServerClientRateLimitError(XServerClientException):
    """Raised when the API rate limit is exceeded (HTTP 429)."""
    pass


class XServerClientAuthError(XServerClientException):
    """Raised when authentication fails (HTTP 401/403)."""
    pass


class XServerClient:
    """
    REST API client for XServer DNS.

    XServer API base URL:
        https://api.xserver.ne.jp/v1/server/{servername}/dns

    Rate limits (as of 2026-04):
        - 60 requests/minute
        - 5 concurrent requests
        On exceeded: HTTP 429 with Retry-After header

    Authentication:
        Bearer token via Authorization header

    Args:
        api_key (str):
            XServer API key issued from the XServer account panel.
        servername (str):
            The initial domain assigned at server contract time.
            Format: ``<server_id>.xsrv.jp`` (XServer)
                 or ``<server_id>.xbiz.jp`` (XServerBusiness)
            Note: Additional/custom domains cannot be used here.
    """

    BASE_URL = 'https://api.xserver.ne.jp/v1'

    # Retry settings for rate limiting
    _RETRY_COUNT = 3
    _RETRY_WAIT = 5  # seconds

    def __init__(self, api_key: str, servername: str):
        self.log = getLogger(f'XServerClient[{servername}]')
        self.log.debug('__init__: servername=%s', servername)

        self._servername = servername
        self._session = Session()
        self._session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _dns_url(self) -> str:
        """Return the base DNS endpoint URL for this server."""
        return f'{self.BASE_URL}/server/{self._servername}/dns'

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict | list | None:
        """
        Execute an HTTP request against the XServer API.

        Handles:
        - JSON serialisation/deserialisation
        - Rate limit retries (HTTP 429 with Retry-After)
        - Common HTTP error mapping to typed exceptions

        Args:
            method:  HTTP verb ('GET', 'POST', 'PUT', 'DELETE')
            url:     Full endpoint URL
            params:  Query string parameters (GET)
            data:    Request body as dict (POST/PUT, will be JSON-encoded)

        Returns:
            Parsed JSON response body, or None for 204 No Content.

        Raises:
            XServerClientAuthError:       401 / 403
            XServerClientNotFound:        404
            XServerClientRateLimitError:  429 (after retries exhausted)
            XServerClientException:       Other non-2xx responses
        """
        self.log.debug('_request: method=%s url=%s', method, url)

        for attempt in range(1, self._RETRY_COUNT + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    timeout=30,
                )
            except RequestException as exc:
                raise XServerClientException(
                    f'HTTP request failed: {exc}'
                ) from exc

            status = response.status_code

            # --- Success ---
            if status in (200, 201):
                return response.json()

            if status == 204:
                return None

            # --- Rate limit ---
            if status == 429:
                retry_after = int(
                    response.headers.get('Retry-After', self._RETRY_WAIT)
                )
                if attempt < self._RETRY_COUNT:
                    self.log.warning(
                        '_request: rate limited, waiting %ds '
                        '(attempt %d/%d)',
                        retry_after, attempt, self._RETRY_COUNT,
                    )
                    sleep(retry_after)
                    continue
                raise XServerClientRateLimitError(
                    'Rate limit exceeded after '
                    f'{self._RETRY_COUNT} retries'
                )

            # --- Auth errors ---
            if status in (401, 403):
                raise XServerClientAuthError(
                    f'Authentication failed: HTTP {status}'
                )

            # --- Not found ---
            if status == 404:
                raise XServerClientNotFound(
                    f'Resource not found: {url}'
                )

            # --- Other errors ---
            try:
                error_body = response.json()
                message = error_body.get('error', {}).get(
                    'message', response.text
                )
            except Exception:
                message = response.text

            raise XServerClientException(
                f'API error HTTP {status}: {message}'
            )

        # Should not reach here, but satisfies type checkers
        raise XServerClientException('Unexpected state in _request()')

    # ------------------------------------------------------------------
    # DNS record operations
    # ------------------------------------------------------------------

    def list_records(self, domain: str) -> list[dict]:
        """
        Fetch all DNS records for the specified domain.

        XServer API: GET /v1/server/{servername}/dns?domain={domain}

        Args:
            domain: Fully-qualified domain name (e.g. ``example.com``).
                    Punycode conversion for IDN must be done by the caller.

        Returns:
            List of record dicts. Each dict contains at minimum::

                {
                    "id":       int,      # XServer-internal record ID
                    "domain":   str,      # e.g. "example.com"
                    "host":     str,      # subdomain or "@" for apex
                    "type":     str,      # "A", "MX", "TXT", ...
                    "content":  str,      # record value
                    "ttl":      int,      # seconds (60–86400)
                    "priority": int|None  # MX/SRV only
                }

        Raises:
            XServerClientNotFound:   Domain not managed on this server.
            XServerClientAuthError:  Invalid or expired API key.
            XServerClientException:  Any other API error.
        """
        self.log.debug('list_records: domain=%s', domain)
        result = self._request('GET', self._dns_url, params={'domain': domain})
        # API returns {"dns": [...]} or a bare list depending on version;
        # normalise to a list.
        if isinstance(result, dict):
            return result.get('dns', [])
        return result or []

    def create_record(self, domain: str, record: dict) -> dict:
        """
        Add a new DNS record to the specified domain.

        XServer API: POST /v1/server/{servername}/dns

        Args:
            domain: Target domain name.
            record: Record definition dict with the following keys:

                Required:
                    - ``host``    (str)  – Subdomain label or ``""`` for apex.
                    - ``type``    (str)  – Record type (A, AAAA, CNAME, MX,
                                           TXT, SRV, CAA).
                    - ``content`` (str)  – Record value.

                Optional:
                    - ``ttl``      (int) – Time-to-live in seconds
                                           (60–86400, default 3600).
                    - ``priority`` (int) – Priority for MX/SRV records.

        Returns:
            The created record dict including the XServer-assigned ``id``.

        Raises:
            XServerClientException: Validation error or duplicate record.
        """
        self.log.debug(
            'create_record: domain=%s host=%s type=%s',
            domain, record.get('host'), record.get('type'),
        )
        payload = {'domain': domain, **record}
        result = self._request('POST', self._dns_url, data=payload)
        # API returns {"dns": {...}} wrapping the created record
        if isinstance(result, dict) and 'dns' in result:
            return result['dns']
        return result

    def update_record(self, dns_id: int, record: dict) -> dict:
        """
        Update an existing DNS record by its XServer-internal ID.

        XServer API: PUT /v1/server/{servername}/dns/{dns_id}

        Only fields included in ``record`` are updated; omitted fields
        retain their current values.

        Args:
            dns_id: The ``id`` field from a previously fetched record.
            record: Partial or full record dict (same schema as
                    :meth:`create_record`).

        Returns:
            The updated record dict.

        Raises:
            XServerClientNotFound: ``dns_id`` does not exist.
            XServerClientException: Other API error.
        """
        self.log.debug('update_record: dns_id=%d', dns_id)
        url = f'{self._dns_url}/{dns_id}'
        result = self._request('PUT', url, data=record)
        if isinstance(result, dict) and 'dns' in result:
            return result['dns']
        return result

    def delete_record(self, dns_id: int) -> None:
        """
        Delete a DNS record by its XServer-internal ID.

        XServer API: DELETE /v1/server/{servername}/dns/{dns_id}

        Args:
            dns_id: The ``id`` field from a previously fetched record.

        Raises:
            XServerClientNotFound: ``dns_id`` does not exist.
            XServerClientException: Other API error.
        """
        self.log.debug('delete_record: dns_id=%d', dns_id)
        url = f'{self._dns_url}/{dns_id}'
        self._request('DELETE', url)


# ---------------------------------------------------------------------------
# XServerProvider
# ---------------------------------------------------------------------------

from collections import defaultdict

from octodns.provider.base import BaseProvider
from octodns.record import Record
from octodns.record.change import Create, Delete, Update


class XServerProvider(BaseProvider):
    """
    octoDNS provider for XServer DNS API.

    Manages DNS records on XServer レンタルサーバー / XServerビジネス
    via the XServer API (released 2026-04-16).

    Supported record types: A, AAAA, CNAME, MX, TXT, SRV, CAA

    Example ``octodns-config.yaml``::

        providers:
          xserver:
            class: octodns_xserver.XServerProvider
            api_key: env/XSERVER_API_KEY
            servername: env/XSERVER_SERVERNAME

        zones:
          example.com.:
            sources:
              - config
            targets:
              - xserver

    Args:
        id (str):        octoDNS provider identifier.
        api_key (str):   XServer API key.
        servername (str): XServer initial domain (e.g. xs123456.xsrv.jp).
    """

    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS = frozenset(('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'CAA'))

    def __init__(self, id: str, api_key: str, servername: str,
                 *args, **kwargs):
        self.log = getLogger(f'XServerProvider[{id}]')
        self.log.debug('__init__: id=%s servername=%s', id, servername)
        super().__init__(id, *args, **kwargs)
        self._client = XServerClient(api_key, servername)
        # Zone-level cache: zone_name -> list of raw XServer record dicts
        self._raw_cache: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Host / name conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _host_to_name(host: str) -> str:
        """XServer '@' -> octoDNS '' (apex)."""
        return '' if host == '@' else host

    @staticmethod
    def _name_to_host(name: str) -> str:
        """octoDNS '' (apex) -> XServer '@'."""
        return '@' if name == '' else name

    @staticmethod
    def _domain_from_zone(zone_name: str) -> str:
        """'example.com.' -> 'example.com'"""
        return zone_name.rstrip('.')

    # ------------------------------------------------------------------
    # XServer record dicts -> octoDNS data dicts
    # ------------------------------------------------------------------

    def _data_for_A(self, records: list[dict]) -> dict:
        return {'ttl': records[0]['ttl'],
                'values': [r['content'] for r in records]}

    def _data_for_AAAA(self, records: list[dict]) -> dict:
        return self._data_for_A(records)

    def _data_for_CNAME(self, records: list[dict]) -> dict:
        content = records[0]['content']
        if not content.endswith('.'):
            content += '.'
        return {'ttl': records[0]['ttl'], 'value': content}

    def _data_for_MX(self, records: list[dict]) -> dict:
        values = []
        for r in records:
            exchange = r['content']
            if not exchange.endswith('.'):
                exchange += '.'
            values.append({'preference': r.get('priority') or 10,
                           'exchange': exchange})
        return {'ttl': records[0]['ttl'], 'values': values}

    def _data_for_TXT(self, records: list[dict]) -> dict:
        return {'ttl': records[0]['ttl'],
                'values': [r['content'] for r in records]}

    def _data_for_SRV(self, records: list[dict]) -> dict:
        """XServer SRV content format: 'weight port target'"""
        values = []
        for r in records:
            parts = r['content'].split(' ', 2)
            weight = int(parts[0]) if len(parts) > 0 else 0
            port   = int(parts[1]) if len(parts) > 1 else 0
            target = parts[2]      if len(parts) > 2 else '.'
            if not target.endswith('.'):
                target += '.'
            values.append({'priority': r.get('priority') or 0,
                           'weight': weight, 'port': port, 'target': target})
        return {'ttl': records[0]['ttl'], 'values': values}

    def _data_for_CAA(self, records: list[dict]) -> dict:
        """XServer CAA content format: 'flags tag "value"'"""
        values = []
        for r in records:
            parts = r['content'].split(' ', 2)
            flags = int(parts[0]) if len(parts) > 0 else 0
            tag   = parts[1]      if len(parts) > 1 else 'issue'
            value = parts[2].strip('"') if len(parts) > 2 else ''
            values.append({'flags': flags, 'tag': tag, 'value': value})
        return {'ttl': records[0]['ttl'], 'values': values}

    # ------------------------------------------------------------------
    # octoDNS Record -> XServer record dicts
    # ------------------------------------------------------------------

    def _records_for_A(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'A',
                 'content': v, 'ttl': record.ttl}
                for v in record.values]

    def _records_for_AAAA(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'AAAA',
                 'content': v, 'ttl': record.ttl}
                for v in record.values]

    def _records_for_CNAME(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'CNAME',
                 'content': record.value, 'ttl': record.ttl}]

    def _records_for_MX(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'MX', 'content': v.exchange,
                 'ttl': record.ttl, 'priority': v.preference}
                for v in record.values]

    def _records_for_TXT(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'TXT',
                 'content': v, 'ttl': record.ttl}
                for v in record.values]

    def _records_for_SRV(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'SRV',
                 'content': f'{v.weight} {v.port} {v.target}',
                 'ttl': record.ttl, 'priority': v.priority}
                for v in record.values]

    def _records_for_CAA(self, host: str, record) -> list[dict]:
        return [{'host': host, 'type': 'CAA',
                 'content': f'{v.flags} {v.tag} "{v.value}"',
                 'ttl': record.ttl}
                for v in record.values]

    def _to_xserver_records(self, record) -> list[dict]:
        """Convert an octoDNS Record to a list of XServer record dicts."""
        host = self._name_to_host(record.name)
        rtype = record._type
        converter = getattr(self, f'_records_for_{rtype}', None)
        if converter is None:
            self.log.warning('_to_xserver_records: unsupported type %s', rtype)
            return []
        return converter(host, record)

    # ------------------------------------------------------------------
    # populate()
    # ------------------------------------------------------------------

    def populate(self, zone, target: bool = False,
                 lenient: bool = False) -> bool:
        self.log.debug('populate: zone=%s target=%s', zone.name, target)
        domain = self._domain_from_zone(zone.name)

        try:
            raw_records = self._client.list_records(domain)
        except XServerClientNotFound:
            self.log.info('populate: zone %s not found', zone.name)
            return False

        # Cache for use in _apply()
        self._raw_cache[zone.name] = raw_records

        # Group by (host, type)
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for r in raw_records:
            grouped[(r['host'], r['type'])].append(r)

        for (host, rtype), records in grouped.items():
            if rtype not in self.SUPPORTS:
                self.log.warning(
                    'populate: skipping unsupported type %s host %s',
                    rtype, host)
                continue
            converter = getattr(self, f'_data_for_{rtype}', None)
            if converter is None:
                continue
            name = self._host_to_name(host)
            data = {**converter(records), 'type': rtype}
            record = Record.new(zone, name, data, source=self, lenient=True)
            zone.add_record(record, lenient=True)

        self.log.info('populate: found %d records for %s',
                      len(zone.records), zone.name)
        return True

    # ------------------------------------------------------------------
    # _apply()
    # ------------------------------------------------------------------

    def _apply(self, plan) -> None:
        desired = plan.desired
        zone_name = desired.name
        domain = self._domain_from_zone(zone_name)
        self.log.debug('_apply: zone=%s changes=%d',
                       zone_name, len(plan.changes))

        def _delete_existing(record) -> None:
            """Delete all XServer records matching (host, type)."""
            host = self._name_to_host(record.name)
            rtype = record._type
            for r in self._raw_cache.get(zone_name, []):
                if r['host'] == host and r['type'] == rtype:
                    self.log.debug('_apply: delete id=%d host=%s type=%s',
                                   r['id'], host, rtype)
                    self._client.delete_record(r['id'])

        def _create_records(record) -> None:
            """Create XServer records from an octoDNS Record."""
            for xr in self._to_xserver_records(record):
                self.log.debug('_apply: create host=%s type=%s content=%s',
                               xr.get('host'), xr.get('type'),
                               xr.get('content'))
                self._client.create_record(domain, xr)

        for change in plan.changes:
            if isinstance(change, Create):
                _create_records(change.new)
            elif isinstance(change, Update):
                _delete_existing(change.existing)
                _create_records(change.new)
            elif isinstance(change, Delete):
                _delete_existing(change.existing)

        self.log.info('_apply: applied %d changes to %s',
                      len(plan.changes), zone_name)
