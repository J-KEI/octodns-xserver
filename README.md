# octodns-xserver

[octoDNS](https://github.com/octodns/octodns) provider for [XServer](https://www.xserver.ne.jp/) DNS API.

XServerのDNSレコードをYAMLファイルで管理し、GitHub Actionsで自動同期するためのoctoDNSプロバイダーです。

> **Note**: XServer API は2026年4月にリリースされました。本プロバイダーはXServer API に対応した最初のoctoDNSプロバイダーです。

---

## 対応レコードタイプ

| タイプ | 対応 |
|--------|------|
| A      | ✅   |
| AAAA   | ✅   |
| CNAME  | ✅   |
| MX     | ✅   |
| TXT    | ✅   |
| SRV    | ✅   |
| CAA    | ✅   |

---

## インストール

```bash
pip install octodns-xserver
```

開発版(GitHubから直接):

```bash
pip install git+https://github.com/hosting-memo/octodns-xserver.git
```

---

## セットアップ

### 1. XServer APIキーを発行する

XServerアカウントの「APIキー管理」からAPIキーを発行してください。

必要な権限: **DNS 読み取り + 書き込み**

### 2. GitHub Secretsを設定する

リポジトリの `Settings > Secrets and variables > Actions` に以下を登録します。

| シークレット名       | 値                                        |
|---------------------|------------------------------------------|
| `XSERVER_API_KEY`    | 発行したAPIキー                           |
| `XSERVER_SERVERNAME` | 初期ドメイン (例: `xs123456.xsrv.jp`)    |

> **初期ドメインとは**: サーバー契約時に自動付与されるドメインです。追加した独自ドメインは指定できません。

### 3. リポジトリを構成する

```
your-dns-repo/
├── octodns-config.yaml     # octoDNS設定ファイル
├── zones/
│   ├── example.com.yaml    # ドメインごとのゾーンファイル
│   └── another.jp.yaml
└── .github/
    └── workflows/
        ├── dns-dry-run.yml  # PR時のプレビュー
        └── dns-sync.yml     # mainマージ時の同期
```

---

## 設定ファイル

### octodns-config.yaml

```yaml
providers:
  config:
    class: octodns.provider.yaml.YamlProvider
    directory: ./zones
    default_ttl: 3600

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

### zones/example.com.yaml

```yaml
---
# apex (example.com)
'':
  type: A
  values:
    - 203.0.113.1

www:
  type: A
  values:
    - 203.0.113.1

'':
  type: MX
  values:
    - preference: 10
      exchange: mail.example.com.

'':
  type: TXT
  values:
    - 'v=spf1 include:xserver.ne.jp ~all'

_dmarc:
  type: TXT
  values:
    - 'v=DMARC1; p=none; rua=mailto:dmarc@example.com'
```

---

## GitHub Actions ワークフロー

本リポジトリの `.github/workflows/` にワークフローのサンプルが含まれています。

### dns-dry-run.yml (PR時)

`zones/` 配下のYAMLを変更してPRを作成すると、実際のDNS変更内容がPRコメントとして自動投稿されます。

```
## DNS変更プレビュー (dry-run)

Creates=1, Updates=2, Deletes=0
```

### dns-sync.yml (mainマージ時)

PRをmainにマージすると、XServer DNSに実際の変更が反映されます。

`environment: production` を設定しておくと、GitHub上で承認者を指定できます(追加の安全策)。

---

## ローカルでの実行

```bash
# インストール
pip install -e .

# dry-run (変更内容の確認のみ)
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml --dry-run

# 本番同期
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml --doit
```

---

## 初回導入手順

既存のDNSレコードをYAMLに取り込む初回エクスポートは現在未実装です(v0.1.0で対応予定)。

現時点では以下の手順で初回導入を行ってください。

1. XServerのDNSレコード設定画面を開く
2. 現在のレコードを確認しながら `zones/your-domain.yaml` を手動で作成する
3. `--dry-run` で差分が0件になることを確認する
4. `--doit` で初回同期を実行する

---

## 開発・テスト

```bash
git clone https://github.com/hosting-memo/octodns-xserver.git
cd octodns-xserver
pip install -e ".[dev]"
pytest tests/ -v
```

---

## ライセンス

MIT
