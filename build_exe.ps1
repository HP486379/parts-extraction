# build_exe.ps1
# FastAPI + React アプリを exe 化して配布用にまとめるスクリプト
# 対応環境：Windows PowerShell

Write-Host "🔧 FastAPI + React アプリの EXE ビルドを開始します..." -ForegroundColor Cyan

# --- 1. backend 環境構築 ---
Write-Host "`n[1/5] 仮想環境を構築中..." -ForegroundColor Yellow
cd backend

if (-Not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Host "✅ 仮想環境を作成しました。"
} else {
    Write-Host "⚙️ 既存の仮想環境を使用します。"
}

.\.venv\Scripts\Activate.ps1

Write-Host "`n[2/5] パッケージをインストール中..." -ForegroundColor Yellow
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# --- 2. exe ビルド ---
Write-Host "`n[3/5] PyInstaller による EXE ビルド中..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item dist -Recurse -Force }
if (Test-Path "build") { Remove-Item build -Recurse -Force }

pyinstaller --onefile run_app.py

# --- 3. フロントエンドビルド ---
Write-Host "`n[4/5] React (Vite) フロントエンドをビルド中..." -ForegroundColor Yellow
cd ../frontend
npm install
npm run build

# --- 4. 配布フォルダ作成 ---
Write-Host "`n[5/5] 配布フォルダを整理中..." -ForegroundColor Yellow
cd ..
$releaseDir = "parts_extraction_release"
if (Test-Path $releaseDir) { Remove-Item $releaseDir -Recurse -Force }
New-Item -ItemType Directory -Path $releaseDir | Out-Null

Copy-Item backend\dist\run_app.exe "$releaseDir\parts_extraction.exe"
Copy-Item -Recurse frontend\dist "$releaseDir\frontend_dist"

Write-Host "`n✅ ビルド完了！" -ForegroundColor Green
Write-Host "-------------------------------------------"
Write-Host " 出力フォルダ: $releaseDir"
Write-Host " 実行ファイル: $releaseDir\parts_extraction.exe"
Write-Host "-------------------------------------------"
Write-Host "▶ exe を実行すると FastAPI + React アプリが起動します。"
Write-Host "-------------------------------------------"
