from __future__ import annotations

import os
import re
import math
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import camelot

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi import FastAPI, UploadFile, File, Form, HTTPException


# ======================
# FastAPI
# ======================

app = FastAPI(title="Parts Extractor API (Tkinter-logic port)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# Patterns (ゆるく拾う)
# ======================

# 部品番号：ハイフン/スラッシュ/英数字/末尾枝番などを許容（fullmatchしない）
# 例: "ABC-123", "12-3456-78", "A12B-3", "12345", "X-12/34"
PART_NO_LOOSE = re.compile(r"[A-Z0-9][A-Z0-9\-\/]*[A-Z0-9]", re.IGNORECASE)

# L/W/Tっぽい数値：2, 2.0, 2.00, 2mm, t=2 など
NUM_LOOSE = re.compile(r"[-+]?\d+(?:\.\d+)?")

# ヘッダ推定：依存しすぎない（補助として使う）
HDR_L = re.compile(r"^(?:L|LENGTH|長さ)\b", re.IGNORECASE)
HDR_W = re.compile(r"^(?:W|WIDTH|幅)\b", re.IGNORECASE)
HDR_T = re.compile(r"^(?:T|THK|THICK|厚|厚み)\b", re.IGNORECASE)
HDR_PART = re.compile(r"(?:品番|部品|PART\s*NO|PART\s*NUMBER)", re.IGNORECASE)


# ======================
# Request/Response Models
# ======================

class SearchRequest(BaseModel):
    pdf_path: str = Field(..., description="サーバ上のPDFパス（ローカルパス/マウントパス）")
    # ページ指定（Noneなら全部）
    pages: Optional[str] = Field(None, description='例: "1,2,3" or "1-3"')
    # 左右分割（比率）
    split_ratio: float = Field(0.5, ge=0.2, le=0.8, description="ページ幅に対する左右境界の比率")
    # flavor: stream/lattice/auto
    flavor: str = Field("auto", description='camelot flavor: "auto"|"stream"|"lattice"')
    # フィルタ（数値比較）
    L: Optional[float] = None
    W: Optional[float] = None
    T: Optional[float] = None
    tol: float = Field(0.05, ge=0.0, le=1.0, description="数値比較の許容差（相対）")

class PartRow(BaseModel):
    part_no: str
    L: Optional[float] = None
    W: Optional[float] = None
    T: Optional[float] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    items: List[PartRow]
    debug: Dict[str, Any]


# ======================
# Core: Normalization
# ======================

def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    s = str(s)
    # 不可視/改行/タブ→スペース
    s = s.replace("\u00a0", " ").replace("\t", " ").replace("\r", " ").replace("\n", " ")
    # 全角スペース
    s = s.replace("\u3000", " ")
    # 連続スペースを潰す
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_first_number(s: Any) -> Optional[float]:
    s = normalize_text(s)
    if not s:
        return None
    m = NUM_LOOSE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None

def is_close(a: Optional[float], b: Optional[float], rel_tol: float) -> bool:
    if a is None or b is None:
        return False
    # 0付近だけは絶対誤差っぽく
    if abs(b) < 1e-9:
        return abs(a - b) <= rel_tol
    return abs(a - b) <= abs(b) * rel_tol

def score_part_candidate(cell: str) -> float:
    """
    部品番号セル候補のスコア
    - 形がそれっぽい
    - 長すぎ/短すぎを抑制
    - 数値だけより英数混在を少し優遇（現実寄り）
    """
    t = normalize_text(cell)
    if not t:
        return 0.0
    if not PART_NO_LOOSE.search(t):
        return 0.0

    length = len(t)
    score = 1.0
    # 長さペナルティ
    if length < 4:
        score *= 0.4
    elif length > 30:
        score *= 0.5

    # 英字含むなら少し加点
    if re.search(r"[A-Z]", t, re.IGNORECASE):
        score *= 1.2

    # 数値だけだと少し減点（ただしゼロにはしない）
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        score *= 0.8

    # 余計な記号が多すぎたら減点
    if re.search(r"[=,:;]", t):
        score *= 0.7

    return float(score)

def score_dim_candidate(cell: str) -> float:
    """
    L/W/Tセル候補のスコア（数値が取れるほど高い）
    """
    n = extract_first_number(cell)
    if n is None:
        return 0.0
    # 現実的な寸法レンジを軽く優遇（雑でOK）
    if 0 < n < 100000:
        return 1.0
    return 0.6


# ======================
# Core: Camelot wrapper (flavor auto)
# ======================

def camelot_read(pdf_path: str, pages: str, flavor: str):
    # 🚀 高速モード（あなたのPDF前提）
    return list(
        camelot.read_pdf(
            pdf_path,
            pages="1",          # 1ページ固定
            flavor="lattice",   # 罫線あり固定
            line_scale=40,
            strip_text="\n",
        )
    )


# ======================
# Core: Table -> page split (左右分割は座標/比率で決める)
# ======================

@dataclass
class TableBlock:
    side: str  # "L" or "R"
    df: pd.DataFrame
    meta: Dict[str, Any]

def split_table_left_right(df: pd.DataFrame, split_ratio: float, debug: Dict[str, Any], table_idx: int) -> List[TableBlock]:
    """
    Camelotのdfは「見た目の列」が既に入ってくるが、それがズレることがある。
    Tkinter寄せとして「左右」を列インデックスの比率で分ける（最小限の不変条件）。
    ※本気で座標を使うなら、Camelotの_tableやparsing_reportに依存しやすいのでここでは堅牢さ優先で簡易。
    """
    df2 = df.copy()
    df2 = df2.applymap(normalize_text)

    ncols = df2.shape[1]
    cut = max(1, min(ncols - 1, int(math.floor(ncols * split_ratio))))

    left = df2.iloc[:, :cut]
    right = df2.iloc[:, cut:]

    debug["tables"][table_idx]["split"] = {
        "ncols": ncols,
        "cut_col_index": cut,
        "left_cols": left.shape[1],
        "right_cols": right.shape[1],
    }

    blocks = []
    if left.shape[1] > 0 and left.shape[0] > 0:
        blocks.append(TableBlock("L", left, {"table_idx": table_idx}))
    if right.shape[1] > 0 and right.shape[0] > 0:
        blocks.append(TableBlock("R", right, {"table_idx": table_idx}))
    return blocks


# ======================
# Core: Column inference (ヘッダに依存しすぎない)
# ======================

@dataclass
class InferredColumns:
    part_col: int
    l_col: Optional[int] = None
    w_col: Optional[int] = None
    t_col: Optional[int] = None
    confidence: Dict[str, Any] = None

def infer_columns(df: pd.DataFrame) -> Optional[InferredColumns]:
    """
    1) 部品番号列：全セルをスコアして列合計が最大の列を採用
    2) L/W/T列：ヘッダがあれば強く、なければ数値密度で推定
    """
    if df.empty:
        return None

    # ヘッダ行候補：先頭1〜2行を見て「ヘッダっぽさ」を拾う（依存は弱め）
    header_rows = [0]
    if df.shape[0] >= 2:
        header_rows.append(1)

    col_scores_part = []
    col_scores_dim = []

    for c in range(df.shape[1]):
        col = df.iloc[:, c].astype(str).map(normalize_text)

        # PART列スコア：全行から
        s_part = col.map(score_part_candidate).sum()

        # DIM列スコア：全行から（数値取れる密度）
        s_dim = col.map(score_dim_candidate).sum()

        # ヘッダ加点
        hdr_text = " ".join([normalize_text(df.iat[r, c]) for r in header_rows if r < df.shape[0]])
        if HDR_PART.search(hdr_text):
            s_part *= 1.5
        if HDR_L.search(hdr_text) or HDR_W.search(hdr_text) or HDR_T.search(hdr_text):
            s_dim *= 1.2

        col_scores_part.append(float(s_part))
        col_scores_dim.append(float(s_dim))

    part_col = int(np.argmax(col_scores_part))
    # 部品番号列が弱すぎるなら None（ただし閾値は低め＝候補保持）
    if col_scores_part[part_col] < 1.0:
        return None

    # L/W/Tは「ヘッダ優先、無ければdimスコア上位から割当」
    l_col = w_col = t_col = None

    # ヘッダで明確に指せるなら採用
    for c in range(df.shape[1]):
        hdr_text = " ".join([normalize_text(df.iat[r, c]) for r in header_rows if r < df.shape[0]])
        if l_col is None and HDR_L.search(hdr_text):
            l_col = c
        if w_col is None and HDR_W.search(hdr_text):
            w_col = c
        if t_col is None and HDR_T.search(hdr_text):
            t_col = c

    # 未確定は dimスコアの順位で埋める（part_colは除外）
    order = np.argsort(col_scores_dim)[::-1].tolist()
    order = [c for c in order if c != part_col]

    def pick_next(exclude: set) -> Optional[int]:
        for c in order:
            if c not in exclude and col_scores_dim[c] >= 1.0:
                return int(c)
        return None

    used = {part_col}
    if l_col is None:
        l_col = pick_next(used)
        if l_col is not None:
            used.add(l_col)
    if w_col is None:
        w_col = pick_next(used)
        if w_col is not None:
            used.add(w_col)
    if t_col is None:
        t_col = pick_next(used)
        if t_col is not None:
            used.add(t_col)

    return InferredColumns(
        part_col=part_col,
        l_col=l_col,
        w_col=w_col,
        t_col=t_col,
        confidence={
            "part_scores": col_scores_part,
            "dim_scores": col_scores_dim,
            "chosen": {"part": part_col, "L": l_col, "W": w_col, "T": t_col},
        },
    )


# ======================
# Core: Row extraction (即死しない、候補保持→正規化)
# ======================

def extract_rows(df: pd.DataFrame, cols: InferredColumns) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if df.empty:
        return rows

    for r in range(df.shape[0]):
        part_raw = normalize_text(df.iat[r, cols.part_col])

        # 候補条件：PARTっぽい“何か”が含まれてれば拾う（fullmatch禁止）
        if not PART_NO_LOOSE.search(part_raw):
            continue

        # 正規化：余計なスペース削除、連続記号整理など（必要ならここを厚く）
        part_no = part_raw.replace(" ", "")
        part_no = part_no.strip()

        L = extract_first_number(df.iat[r, cols.l_col]) if cols.l_col is not None else None
        W = extract_first_number(df.iat[r, cols.w_col]) if cols.w_col is not None else None
        T = extract_first_number(df.iat[r, cols.t_col]) if cols.t_col is not None else None

        rows.append(
            {
                "part_no": part_no,
                "L": L,
                "W": W,
                "T": T,
                "row_index": r,
                "raw": {
                    "part_cell": normalize_text(df.iat[r, cols.part_col]),
                    "L_cell": normalize_text(df.iat[r, cols.l_col]) if cols.l_col is not None else "",
                    "W_cell": normalize_text(df.iat[r, cols.w_col]) if cols.w_col is not None else "",
                    "T_cell": normalize_text(df.iat[r, cols.t_col]) if cols.t_col is not None else "",
                },
            }
        )

    return rows


def apply_numeric_filters(items: List[Dict[str, Any]], L: Optional[float], W: Optional[float], T: Optional[float], tol: float) -> List[Dict[str, Any]]:
    if L is None and W is None and T is None:
        return items

    out = []
    for it in items:
        ok = True
        if L is not None:
            ok = ok and is_close(it.get("L"), L, tol)
        if W is not None:
            ok = ok and is_close(it.get("W"), W, tol)
        if T is not None:
            ok = ok and is_close(it.get("T"), T, tol)
        if ok:
            out.append(it)
    return out


# ======================
# Public API: extract
# ======================

def normalize_pages(pages: Optional[str]) -> str:
    return "1"


def extract_parts_from_pdf(
    pdf_path: str,
    pages: Optional[str],
    split_ratio: float,
    flavor: str,
    flt_L: Optional[float],
    flt_W: Optional[float],
    flt_T: Optional[float],
    tol: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages_s = normalize_pages(pages)

    debug: Dict[str, Any] = {
        "pdf_path": pdf_path,
        "pages": pages_s,
        "flavor": flavor,
        "split_ratio": split_ratio,
        "filters": {"L": flt_L, "W": flt_W, "T": flt_T, "tol": tol},
        "tables": [],
        "notes": [],
    }

    # Camelot read
    try:
        tables = camelot_read(pdf_path, pages_s, flavor)
    except Exception as e:
        debug["notes"].append(f"camelot_read failed: {repr(e)}")
        return [], debug

    debug["tables_count"] = len(tables)

    all_items: List[Dict[str, Any]] = []

    for i, t in enumerate(tables):
        try:
            df = t.df
        except Exception as e:
            debug["tables"].append({"table_idx": i, "error": repr(e)})
            continue

        tbl_dbg = {
            "table_idx": i,
            "shape": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
            "parsing_report": getattr(t, "parsing_report", None),
        }
        debug["tables"].append(tbl_dbg)

        # 左右分割（不変条件）
        blocks = split_table_left_right(df, split_ratio, debug, i)

        for b in blocks:
            cols = infer_columns(b.df)
            if cols is None:
                tbl_dbg.setdefault("blocks", []).append({"side": b.side, "status": "no_part_col"})
                continue

            tbl_dbg.setdefault("blocks", []).append(
                {
                    "side": b.side,
                    "status": "ok",
                    "inferred": cols.confidence,
                }
            )

            items = extract_rows(b.df, cols)

            # フィルタ（数値比較）
            items2 = apply_numeric_filters(items, flt_L, flt_W, flt_T, tol)

            # 0件でも原因が見えるようにカウント
            tbl_dbg["blocks"][-1]["extracted_rows"] = len(items)
            tbl_dbg["blocks"][-1]["after_filter_rows"] = len(items2)

            # side/table_idx を付加して追跡可能に
            for it in items2:
                it["source"] = {"table_idx": i, "side": b.side}
                all_items.append(it)

    return all_items, debug


# ======================
# Endpoint
# ======================

@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    try:
        items, debug = extract_parts_from_pdf(
            pdf_path=req.pdf_path,
            pages=req.pages,
            split_ratio=req.split_ratio,
            flavor=req.flavor,
            flt_L=req.L,
            flt_W=req.W,
            flt_T=req.T,
            tol=req.tol,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {repr(e)}")

    # 返却整形
    out = [
        {
            "part_no": it["part_no"],
            "L": it.get("L"),
            "W": it.get("W"),
            "T": it.get("T"),
            "raw": {"source": it.get("source"), **it.get("raw", {})},
        }
        for it in items
    ]

    return {"items": out, "debug": debug}

import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

@app.post("/api/extract_part_numbers_from_table")
async def extract_part_numbers_from_table(
    files: List[UploadFile] = File(...),
    split_ratio: float = Form(0.5),
    L: Optional[float] = Form(None),
    W: Optional[float] = Form(None),
    T: Optional[float] = Form(None),
    tol: float = Form(0.05),
):
    tmp_paths = []
    try:
        # ① 一時保存
        for f in files:
            data = await f.read()
            fd, path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            with open(path, "wb") as w:
                w.write(data)
            tmp_paths.append((path, f.filename))

        # ② 並列処理（ここが肝）
        max_workers = min(4, os.cpu_count() or 2, len(tmp_paths))
        results = {}

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _worker_extract_one,
                    path,
                    split_ratio,
                    L,
                    W,
                    T,
                    tol
                ): filename
                for path, filename in tmp_paths
            }

            for future in as_completed(futures):
                filename = futures[future]
                items, _debug = future.result()

                part_numbers = sorted({it["part_no"] for it in items})
                results[filename] = part_numbers

        # ③ フロント互換レスポンス
        return [
            {
                "file_name": filename,
                "count": len(results.get(filename, [])),
                "part_numbers": results.get(filename, []),
            }
            for _, filename in tmp_paths
        ]

    finally:
        for p, _ in tmp_paths:
            try:
                os.remove(p)
            except Exception:
                pass

