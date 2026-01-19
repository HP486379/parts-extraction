# 部品番号抽出ツール（Windows PowerShell 用セットアップガイド）

このリポジトリは **PDF 図面から部品番号を抽出** するためのサンプル実装です。フロントエンドは **React (Vite) + Material UI**、バックエンドは **FastAPI** を使用しています。

---

## 🚀 機能概要

- 複数 PDF ファイルのアップロード
- L 値・W 値・T 値の数値入力（T 値は任意指定）
- 条件に一致した行の検索およびテーブル表示（条件変更時は自動で再検索）
- 検索結果の CSV ダウンロード
- バックエンドとの通信は REST API 経由
- アップロードしたファイルの個別削除が可能

---

## 📁 ディレクトリ構成

```text
backend/                 # FastAPI アプリケーション
frontend/                # Vite + React フロントエンド
frontend_dist/           # Vite のビルド成果物（スタンドアロン配信用）
parts_extraction_release/
  frontend_dist/         # exe で配布するフロントエンド静的ファイル
  parts_extraction.exe   # PyInstaller で作成したワンファイル実行形式
```

---

## ⚙️ バックエンド（FastAPI）起動手順

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

## 🧾 OCR 依存関係（スキャン PDF 対応）

スキャン PDF は OCR ルートで処理します。Windows では `poppler` を PATH に追加してください。

1. [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) から zip をダウンロード
2. 解凍後、`poppler-xx\Library\bin` を環境変数 `PATH` に追加
3. PowerShell を再起動し、`pdftoppm -h` が動くことを確認

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

Vite のプロキシ設定により、フロントエンド（http://localhost:5173）からの API リクエストは自動的にバックエンド（http://localhost:8000）へ転送されます。バックエンドを起動した状態でフロントエンドを立ち上げてください。

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
