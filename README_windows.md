# 部品番号抽出ツール（Windows PowerShell 用セットアップガイド）

<<<<<<< ours
このリポジトリは **PDF 図面から部品番号を抽出** するためのサンプル実装です。  
=======
このリポジトリは **PDF 図面から部品番号を抽出** するためのサンプル実装です。
>>>>>>> theirs
フロントエンドは **React (Vite) + Material UI**、バックエンドは **FastAPI** を使用しています。

---

## 🚀 機能概要

<<<<<<< ours
- 複数 PDF ファイルのアップロード  
- L 値・W 値の数値入力  
- 条件に一致した行の検索およびテーブル表示（L/W 値の変更時は自動で再検索）  
- 検索結果の CSV ダウンロード  
- バックエンドとの通信は REST API 経由  
- アップロードしたファイルの個別削除が可能  
=======
- 複数 PDF ファイルのアップロード
- L 値・W 値・T 値の数値入力（T 値は任意指定）
- 条件に一致した行の検索およびテーブル表示（条件変更時は自動で再検索）
- 検索結果の CSV ダウンロード
- バックエンドとの通信は REST API 経由
- アップロードしたファイルの個別削除が可能
>>>>>>> theirs

---

## 📁 ディレクトリ構成

<<<<<<< ours
backend/ # FastAPI アプリケーション
frontend/ # Vite + React フロントエンド

yaml
コードをコピーする
=======
```text
backend/                 # FastAPI アプリケーション
frontend/                # Vite + React フロントエンド
frontend_dist/           # Vite のビルド成果物（スタンドアロン配信用）
parts_extraction_release/
  frontend_dist/         # exe で配布するフロントエンド静的ファイル
  parts_extraction.exe   # PyInstaller で作成したワンファイル実行形式
```
>>>>>>> theirs

---

## ⚙️ バックエンド（FastAPI）起動手順

<<<<<<< ours
### 1️⃣ backend フォルダへ移動
```powershell
cd "C:\\Users\\<ユーザー名>\\Desktop\\codex\\parts-extraction-codex-add-multiple-pdf-upload-functionality\\backend"
2️⃣ 仮想環境を作成（初回のみ）
powershell
コードをコピーする
python -m venv .venv
3️⃣ 仮想環境を有効化
powershell
コードをコピーする
.\\.venv\\Scripts\\Activate.ps1
4️⃣ 依存ライブラリをインストール
powershell
コードをコピーする
pip install -r requirements.txt
5️⃣ FastAPI サーバーを起動
powershell
コードをコピーする
python -m uvicorn app.main:app --reload
✅ 動作確認
ブラウザで以下を開き、API ドキュメント（Swagger UI）が表示されれば成功です。
http://127.0.0.1:8000/docs

💻 フロントエンド（React + Vite + Material UI）起動手順
1️⃣ 別のターミナルで frontend フォルダへ移動
powershell
コードをコピーする
cd "C:\\Users\\<ユーザー名>\\Desktop\\codex\\parts-extraction-codex-add-multiple-pdf-upload-functionality\\frontend"
2️⃣ npm パッケージをインストール（初回のみ）
powershell
コードをコピーする
npm install
3️⃣ 開発サーバーを起動
powershell
コードをコピーする
npm run dev
✅ 動作確認
ターミナルに次のような表示が出れば成功です：

arduino
コードをコピーする
VITE v5.x  ready in 500ms
Local:   http://localhost:5173/
ブラウザで以下を開いてください👇
http://localhost:5173

🔗 バックエンドとの連携
Vite のプロキシ設定により、
フロントエンド（localhost:5173）→ バックエンド（localhost:8000）へ
API リクエストが自動的に転送されます。

したがって、バックエンドを起動した状態で フロントエンドを立ち上げてください。

🧪 提供 API 一覧
メソッドエンドポイント説明
POST /searchPDF + L/W値を受け取り、該当行を返す
POST /search?return_csv=true検索結果を CSV 形式で返す
GET /healthヘルスチェック用エンドポイント

⚠️ 注意事項
PDF テキスト抽出には PyPDF2 を使用しています。
PDF の構造によってはテキスト抽出結果が期待通りにならない場合があります。

Node.js が未インストールの場合は、
https://nodejs.org/ から最新版をインストールしてください。

CORS エラーが出る場合は、vite.config.js の proxy 設定を確認してください。

✅ 動作確認チェックリスト
項目URL結果
FastAPI (API)http://127.0.0.1:8000/docs✅ 表示されればOK
React UIhttp://localhost:5173✅ ツール画面が表示されればOK

この README は Windows + PowerShell 環境 での動作を前提に書かれています。
Linux / macOS 環境では source .venv/bin/activate の形式に戻してください。
=======
1. backend フォルダへ移動します。
   ```powershell
   cd "C:\Users\<ユーザー名>\Desktop\codex\parts-extraction-codex-add-multiple-pdf-upload-functionality\backend"
   ```
2. 仮想環境を作成します（初回のみ）。
   ```powershell
   python -m venv .venv
   ```
3. 仮想環境を有効化します。
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
4. 依存ライブラリをインストールします。
   ```powershell
   pip install -r requirements.txt
   ```
5. FastAPI サーバーを起動します。
   ```powershell
   python -m uvicorn app.main:app --reload
   ```
6. 以下へアクセスし、Swagger UI が表示されるか確認します。
   - http://127.0.0.1:8000/docs

---

## 💻 フロントエンド（React + Vite + Material UI）起動手順

1. 別のターミナルを開き、frontend フォルダへ移動します。
   ```powershell
   cd "C:\Users\<ユーザー名>\Desktop\codex\parts-extraction-codex-add-multiple-pdf-upload-functionality\frontend"
   ```
2. npm パッケージをインストールします（初回のみ）。
   ```powershell
   npm install
   ```
3. 開発サーバーを起動します。
   ```powershell
   npm run dev
   ```
4. ターミナルに以下のような表示が出れば準備完了です。
   ```text
   VITE v5.x  ready in 500ms
   Local:   http://localhost:5173/
   ```
5. ブラウザで http://localhost:5173 を開き、UI が表示されることを確認します。

---

## 🔗 バックエンドとの連携

Vite のプロキシ設定により、フロントエンド（http://localhost:5173）からの API リクエストは自動でバックエンド（http://localhost:8000）へ転送されます。バックエンドを起動した状態でフロントエンドを立ち上げてください。

---

## 🧪 提供 API 一覧

| メソッド | エンドポイント              | 説明                                   |
|---------|---------------------------|----------------------------------------|
| POST    | `/search`                 | PDF と L/W 値および任意の T 値を受け取り該当行を返す |
| POST    | `/search?return_csv=true` | 検索結果を CSV 形式でダウンロード提供 |
| GET     | `/health`                 | ヘルスチェック用エンドポイント         |

---

## 🟦 ワンファイル EXE での利用

環境構築なしで試したい場合は、`parts_extraction_release/parts_extraction.exe` を実行してください。実行するとローカルでサーバーが立ち上がり、ブラウザで http://localhost:8000 を開くと React UI が表示されます。

配布フォルダ構成は次の通りです。

```text
parts_extraction_release/
  parts_extraction.exe
  frontend_dist/
    index.html
    assets/
```

---

## ⚠️ 注意事項

- PDF テキスト抽出には PyPDF2 を使用しています。PDF の構造によっては期待通りに抽出できない場合があります。
- Node.js が未インストールの場合は https://nodejs.org/ から最新版をインストールしてください。
- CORS エラーが発生した場合は `frontend/vite.config.js` の proxy 設定を確認してください。

---

## ✅ 動作確認チェックリスト

| 項目        | URL                         | 結果例                 |
|-------------|-----------------------------|------------------------|
| FastAPI(API)| http://127.0.0.1:8000/docs  | ✅ 表示されれば OK     |
| React UI    | http://localhost:5173       | ✅ 画面が表示されれば OK |

この README は Windows + PowerShell 環境での動作を前提にしています。Linux / macOS 環境では `source .venv/bin/activate` 形式に読み替えてください。
>>>>>>> theirs
