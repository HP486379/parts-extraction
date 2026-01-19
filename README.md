# 部品番号抽出ツール

このリポジトリは PDF 図面から部品番号を抽出するためのサンプル実装です。フロントエンドは React (Vite) + Material UI、バックエンドは FastAPI を使用しています。

## 機能概要

- 複数 PDF ファイルのアップロード
- L 値・W 値・T 値の数値入力（T 値は任意指定）
- 条件に一致した行の検索およびテーブル表示（条件変更時は自動で再検索）
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

#### OCR 依存関係

- スキャン PDF 向け OCR は `pdf2image` + `PaddleOCR` を利用します。
- macOS/Linux では `poppler` のインストールが必要です。
  - 例: macOS `brew install poppler`, Ubuntu `sudo apt-get install poppler-utils`

### フロントエンド

別のターミナルで次を実行します。

```bash
cd frontend
npm install
npm run dev
```

開発サーバーは http://localhost:5173 で起動します。Vite のプロキシ設定により API へのリクエストは `http://localhost:8000` の FastAPI へ転送されます。

## API

- `POST /search`: PDF と L/W 値および任意の T 値を受け取り、条件に一致する行を返します。
- `POST /search` (return_csv=true): CSV 形式の結果を返します。
- `GET /health`: ヘルスチェック用のエンドポイント。

## 注意事項

PDF テキスト抽出には PyPDF2、スキャン PDF には PaddleOCR を利用しています。PDF の構造や品質によっては抽出結果が期待通りにならない場合があります。
