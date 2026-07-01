# octodns-xserver

[octoDNS](https://github.com/octodns/octodns) の XServer DNS プロバイダーです。

XServerのDNSレコードをYAMLファイルで管理し、GitHub Actionsで自動同期できます。

> **Note**: XServer API は2026年4月にリリースされました。本プロバイダーはXServer DNSに対応した世界初のoctoDNSプロバイダーです。

---

## 対応レコードタイプ

| タイプ | 対応 |
|--------|------|
| A      | ✅ |
| AAAA   | ✅ |
| CNAME  | ✅ |
| MX     | ✅ |
| TXT    | ✅ |
| SRV    | ✅ |
| CAA    | ✅ |

---

## インストール

```bash
pip install octodns-xserver
```

---

## 動作要件

- Python 3.10以上
- octoDNS 1.9.0以上
- XServerアカウント(APIキー発行済み)

---

## セットアップ

### 1. XServer APIキーを発行する

XServerアカウントパネルの **「APIキー管理」** から新しいAPIキーを発行します。

必要な権限: **DNS 読み取り + 書き込み**

### 2. サーバー名を確認する

`servername` はサーバー契約時に自動付与される初期ドメインです。後から追加した独自ドメインは指定できません。

| サービス | 形式 |
|---|---|
| XServerレンタルサーバー | `xs123456.xsrv.jp` |
| XServerビジネス | `xs123456.xbiz.jp` |

### 3. octodns-config.yaml を作成する

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

### 4. ゾーンファイルを作成する

`zones/example.com.yaml` にDNSレコードを定義します。
サンプルは [zones/example.com.yaml](zones/example.com.yaml) を参照してください。

**記述のポイント:**

- ゾーンの apex(`@`)は `''`(空文字)で指定する
- ワイルドカードレコードはクォートが必要: `'*'`
- 同じ名前に複数タイプを定義する場合はリスト形式で書く
- TXT値のセミコロンは `\;` とエスケープする

```yaml
---
# apex(ドメイン自体)にA・MX・TXTをまとめて定義する
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

# ワイルドカードはクォート必須
'*':
  type: A
  values:
    - 203.0.113.1

# TXT値のセミコロンは \; とエスケープする
_dmarc:
  type: TXT
  values:
    - 'v=DMARC1\; p=none\; rua=mailto:dmarc@example.com'
```

---

## 使い方

### 変更内容を確認する(dry run)

実際のDNSは変更されません。変更予定の内容だけ表示されます。

```bash
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml
```

### DNSに反映する

dry runで内容を確認した後、`--doit` を付けて実行します。

```bash
XSERVER_API_KEY=xxx XSERVER_SERVERNAME=xs123456.xsrv.jp \
  octodns-sync --config-file octodns-config.yaml --doit
```

---

## GitHub Actionsで自動化する

`.github/workflows/` にサンプルのワークフローファイルを同梱しています。

### dns-dry-run.yml(PR作成時)

`zones/` 配下のYAMLを変更してPRを作成すると、変更内容がPRコメントに自動投稿されます。実際のDNSは変更されません。

### dns-sync.yml(mainマージ時)

`main` ブランチへのマージ時にXServer DNSへ自動同期します。

リポジトリのSecretsに以下を登録してください。

| シークレット名 | 値 |
|---|---|
| `XSERVER_API_KEY` | XServerパネルで発行したAPIキー |
| `XSERVER_SERVERNAME` | 初期ドメイン(例: `xs123456.xsrv.jp`) |

---

## 注意事項

### ゾーンファイルはパブリックリポジトリに含めない

ゾーンファイル(`zones/*.yaml`)にはIPアドレス・SPFレコード・DKIM公開鍵などが含まれます。**パブリックリポジトリにコミットしないでください。**

推奨する構成:

```
パブリックリポジトリ  → octodns-xserver(このライブラリ)
プライベートリポジトリ → 実際のゾーンファイル
```

### 初回導入時の手順

既存のDNSレコードをYAMLに書き出す export スクリプトは現在未実装です。初回導入は以下の手順で進めてください。

1. XServerパネルのDNSレコード設定画面を開く
2. 現在のレコードを確認しながら `zones/your-domain.yaml` を手動で作成する
3. dry runを実行して `No changes were planned` になることを確認する
4. `--doit` で初回同期を実行する

### TXTレコードのセミコロンについて

octoDNSのバリデーターはTXT値のセミコロンをエスケープ(`\;`)することを要求します。本プロバイダーはXServer APIとのやり取りで自動的に変換処理を行います。

- YAMLファイル内: `\;` と記述する
- XServer APIとの通信: `;` として自動変換される

### NSレコードについて

XServerが自動管理するNSレコードは同期対象から自動的に除外されます。

---

## 開発・テスト

```bash
git clone https://github.com/J-KEI/octodns-xserver.git
cd octodns-xserver

# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac/Linux
python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
pytest tests/ -v
```

---

## ライセンス

MIT
