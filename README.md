# 部品番号抽出ツール

このリポジトリは PDF 図面から部品番号を抽出するためのサンプル実装です。フロントエンドは React (Vite) + Material UI、バックエンドは FastAPI を使用しています。

## 機能概要

- 複数 PDF ファイルのアップロード
<<<<<<< ours
- L 値・W 値の数値入力
- 条件に一致した行の検索およびテーブル表示（L/W 値の変更時は自動で再検索）
=======
- L 値・W 値・T 値の数値入力（T 値は任意指定）
- 条件に一致した行の検索およびテーブル表示（条件変更時は自動で再検索）
>>>>>>> theirs
- 検索結果の CSV ダウンロード
- バックエンドとの通信は REST API 経由
- アップロードしたファイルの個別削除が可能

## ディレクトリ構成

```
backend/   # FastAPI アプリケーション
frontend/  # Vite + React フロントエンド
```

## 事前準備

### バックエンド

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### フロントエンド

別のターミナルで次を実行します。

```bash
cd frontend
npm install
npm run dev
```

開発サーバーは http://localhost:5173 で起動します。Vite のプロキシ設定により API へのリクエストは `http://localhost:8000` の FastAPI へ転送されます。

## API

<<<<<<< ours
- `POST /search`: PDF と L/W 値を受け取り、条件に一致する行を返します。
=======
- `POST /search`: PDF と L/W 値および任意の T 値を受け取り、条件に一致する行を返します。
>>>>>>> theirs
- `POST /search` (return_csv=true): CSV 形式の結果を返します。
- `GET /health`: ヘルスチェック用のエンドポイント。

## 注意事項

PDF テキスト抽出には PyPDF2 を利用しています。PDF の構造によってはテキスト抽出結果が期待通りにならない場合があります。
