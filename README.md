# 部品番号抽出ツール

このリポジトリは、PDF 図面・仕様書から **部品番号（PART No.）を抽出**し、  
L / W / T 条件で絞り込み、CSV 出力できるツールのサンプル実装です。

フロントエンドは **React (Vite) + Material UI**、バックエンドは **FastAPI** を使用しています。

---

## 機能概要

- 複数 PDF ファイルのアップロード
- L 値・W 値・T 値（厚み）の数値入力（T 値は任意）
- 条件に一致した行の検索およびテーブル表示
- PART No. 一覧の表示
- 検索結果の CSV ダウンロード（parts_list.csv）
- バックエンドとの通信は REST API 経由
- アップロードしたファイルの個別削除が可能

---

## ディレクトリ構成

backend/ # FastAPI アプリケーション
frontend/ # Vite + React フロントエンド


---

## 動作環境

- Windows 10 / 11
- PowerShell
- Python 3.11 推奨（※3.13は非推奨）
- Node.js 18 以上

---

## 重要な注意

⚠ Windows + PowerShell + venv の組み合わせは不安定になりやすいため、  
**このプロジェクトでは venv を使用しません。**

⚠ グローバル Python 環境でそのまま実行してください。

---

## セットアップ手順（Windows / PowerShell）

### 1. リポジトリをクローン

```powershell
git clone https://github.com/HP486379/parts-extraction.git
cd parts-extraction
バックエンド起動（FastAPI）
cd backend
依存関係インストール
pip install -r requirements.txt
※ pandas / camelot / opencv などがインストールされます
※ 「PATH が通っていない」等の WARNING は無視して OK です

FastAPI 起動
python -m uvicorn app.main:app --reload
成功すると以下が表示されます：

INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
フロントエンド起動
別の PowerShell を開き、以下を実行します。

cd frontend
npm install
npm run dev
表示例：

Local: http://localhost:5173/
ブラウザでアクセス
http://localhost:5173
API
機能	エンドポイント
PART No 抽出	POST /api/extract_part_numbers_from_table
CSV 出力	POST /api/extract_parts_list_csv
ヘルスチェック	GET /health
よくあるエラーと対処法
❌ ModuleNotFoundError: camelot
pip install camelot-py[cv]
❌ pandas のビルドエラー（Visual Studio が無い）
Python 3.13 を使っている可能性があります。

👉 Python 3.11 を使用してください

❌ venv\Scripts\Activate.ps1 が動かない
このプロジェクトでは venv を使いません。
そのままグローバル Python で実行してください。

❌ Scripts is not on PATH（警告）
無視して OK です。
このプロジェクトではコマンド直打ちは使用しません。

推奨 Python バージョン
Version	状態
3.11	✅ 安定（推奨）
3.12	⚠️ たまに不安定
3.13	❌ pandas / camelot が壊れやすい
最短起動手順（まとめ）
バックエンド
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
フロントエンド
cd frontend
npm install
npm run dev
ブラウザ
http://localhost:5173
注意事項
PDF テキスト抽出には PyPDF2 / Camelot を利用しています。
PDF の構造によってはテキスト抽出結果が期待通りにならない場合があります。

今後の拡張予定
PART No. 抽出精度の改善

L / W / T 条件の厳密化

PDF 形式別最適化

Docker 対応

exe 化（社内配布用）
