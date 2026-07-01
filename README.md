# octodns-xserver

> 日本語のドキュメントは [README.ja.md](README.ja.md) をご覧ください。

[octoDNS](https://github.com/octodns/octodns) provider for [XServer](https://www.xserver.ne.jp/) DNS API.

Manage XServer DNS records as code using YAML files, with automatic sync via GitHub Actions.

> **Note**: The XServer API was released in April 2026. This is the first octoDNS provider to support XServer DNS.

---

## Supported record types

| Type  | Supported |
|-------|-----------|
| A     | ✅ |
| AAAA  | ✅ |
| CNAME | ✅ |
| MX    | ✅ |
| TXT   | ✅ |
| SRV   | ✅ |
| CAA   | ✅ |

---

## Installation

```bash
pip install octodns-xserver
```

Development version (from GitHub):

```bash
pip install git+https://github.com/J-KEI/octodns-xserver.git
```

---

## Requirements

- Python 3.10+
- octoDNS 1.9.0+
- An XServer account with API access enabled

---

## Setup

### 1. Issue an XServer API key

Log in to the XServer account panel and navigate to **API key management** to issue a new API key.

Required permissions: **DNS read + write**

### 2. Identify your server name

The `servername` is the initial domain assigned at contract time, not a custom domain you added later.

Format:
- XServer レンタルサーバー: `xs123456.xsrv.jp`
- XServerビジネス: `xs123456.xbiz.jp`

### 3. Configure octodns-config.yaml

```yaml
providers:
  config:
    class: octodns.provider.yaml.YamlProvider
    directory: ./zones
    default_ttl: 3600
    enforce_order: false

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
```

### 4. Create a zone file

Create `zones/example.com.yaml` with your DNS records.
See [zones/example.com.yaml](zones/example.com.yaml) for a complete example.

Key points:
- Use `''` (empty string) for the zone apex (`@`)
- Wildcard records must be quoted: `'*'`
- When multiple record types share the same name, use a list under the same key
- Semicolons in TXT values must be escaped as `\;`

```yaml
---
'':
  - type: A
    values:
      - 203.0.113.1
  - type: MX
    values:
      - preference: 10
        exchange: mail.example.com.
  - type: TXT
    values:
      - 'v=spf1 include:spf.example.com ~all'

www:
  type: A
  values:
    - 203.0.113.1

'*':
  type: A
  values:
    - 203.0.113.1

# Semicolons in TXT values must be escaped as '\;'
_dmarc:
  type: TXT
  values:
    - 'v=DMARC1\; p=none\; rua=mailto:dmarc@example.com'
```

---

## Usage

### Preview changes (dry run)

```bash
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml
```

No changes are made. The planned changes are displayed only.

### Apply changes

```bash
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml --doit
```

---

## GitHub Actions

Sample workflow files are included in `.github/workflows/`.

### dns-dry-run.yml

Triggered when `zones/` YAML files are changed in a pull request.
Posts a preview of DNS changes as a PR comment — no actual changes are made.

### dns-sync.yml

Triggered when changes are merged to the `main` branch.
Applies DNS changes to XServer.

Set the following secrets in your repository:

| Secret name          | Value                                      |
|---------------------|--------------------------------------------|
| `XSERVER_API_KEY`    | API key issued from the XServer panel      |
| `XSERVER_SERVERNAME` | Initial domain (e.g. `xs123456.xsrv.jp`)  |

---

## Important notes

### Zone files contain sensitive information

Your zone files (`zones/*.yaml`) may contain IP addresses, SPF records, and DKIM public keys. **Do not commit zone files to a public repository.**

Recommended approach:
- Keep this library in a public repository
- Manage your zone files in a **private** repository

### First-time import

octodns-xserver does not yet include an export script to generate YAML from existing XServer DNS records. For the initial setup:

1. Open the DNS record settings in the XServer panel
2. Manually create `zones/your-domain.yaml` based on the current records
3. Run a dry run and verify that `No changes were planned` is shown
4. Then run with `--doit` to confirm the sync works correctly

### TXT record semicolons

octoDNS requires semicolons in TXT values to be escaped as `\;` in YAML files.
This provider automatically handles the conversion when reading from and writing to the XServer API.

### NS records

NS records managed by XServer are automatically skipped during sync.

---

## Development

```bash
git clone https://github.com/J-KEI/octodns-xserver.git
cd octodns-xserver
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

MIT
