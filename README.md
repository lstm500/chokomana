# ちょこまな統合アプリ ver.01

## ファイル
- `app.py` : Streamlit統合アプリ。学習アプリの起動、今日・過去のスタンプ表示、音声再生。
- `requirements.txt` : Streamlit CloudがインストールするPythonライブラリ。SupabaseはREST（Python標準ライブラリ）で接続するため `supabase` パッケージは不要です。
- `supabase_check.sql` : **任意**。既存テーブルの存在・RLS・権限を確認する読み取り専用SQL。実行しなくてもデプロイできます。

## GitHub / Streamlit Cloud
1. 新規のちょこまな用GitHubリポジトリのルートに `app.py` と `requirements.txt` を配置する。
2. Streamlit Cloudの起動ファイルを `app.py` に設定する。
3. Streamlit CloudのApp settings > Secretsに次の値を設定する（値は例・説明です）。

```toml
SUPABASE_URL = "https://keewulninyoeylgflshb.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "Supabaseのサーバー用秘密鍵"
CHOCOMANA_PROFILE_ID = "全学習アプリで同じ学習者ID"

KOTOBA_APP_URL = "https://国語アプリ.streamlit.app"
SOROBAN_APP_URL = "https://そろばんアプリ.streamlit.app"
GEOMETRY_APP_URL = "https://図形アプリ.streamlit.app"
```

**注意**：本物の秘密鍵と学習者IDは、GitHubのファイル、コミット、HTML、JavaScriptに含めず、Streamlit CloudのSecretsでのみ管理してください。
他の利用者がアクセスできないよう、学習者の記録を表示するハブ側にもアクセス制御を設けてください。

## Supabase用SQLについて
接続先 `kotoba_app` には `public.chokomana_stamps` が既に作成されています。新たなテーブル作成SQLやマイグレーションは必要ありません。
必要な場合だけ `supabase_check.sql` をSupabase SQL Editorで実行してください。読み取り専用です。

## 動作と制約
- 「今日の成果」「過去のスタンプ」を開くと共通テーブルを読み取ります。スタンプの保存処理は各学習アプリが担当します。
- 学習アプリのURLが未設定の場合、起動できません。URLはSecretsに登録してください。
- 埋め込み表示が禁止されたアプリは別タブで開きます。
- ブラウザの日本語音声は環境依存です。日本語音声とメロディーの完全同期は保証されません。
- ZIP作成時には構文・アーカイブ検査を実施しましたが、この環境にはStreamlitがないため本番サーバー起動と実Supabase認証は未検証です。
