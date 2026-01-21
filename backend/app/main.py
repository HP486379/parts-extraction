from __future__ import annotations

import csv
import io
import re
import tempfile
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import camelot
import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys

from PyPDF2 import PdfReader


@dataclass
class SearchResult:
    part_number: str
    matched_line: str
    file_name: str


app = FastAPI(title="Parts Extraction API")


# --------------------------------------------------------------------
# Frontend dist auto detect (for packaged app or dev)
# --------------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

FRONTEND_DIST = BASE_DIR / "frontend_dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(FRONTEND_DIST / "index.html")


# --------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------
# PDF parsing patterns
# --------------------------------------------------------------------
PART_NUMBER_PATTERN = re.compile(r"(?=.*\d)[A-Za-z0-9\-_/]{3,}")
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
TABLE_PART_NUMBER_PATTERN = re.compile(r"^[A-Z]{2,}\d{3,}$")

def _read_pdf_lines(upload_file: UploadFile) -> Iterable[str]:
    """Yield the text lines contained in ``upload_file``."""
    data = upload_file.file.read()
    upload_file.file.seek(0)

    reader = PdfReader(io.BytesIO(data))
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            yield line.strip()


def _iter_pdf_text_lines(data: bytes) -> Iterable[tuple[int, int, str]]:
    """
    yield (page_number_1based, line_no_1based, text)
    """
    reader = PdfReader(io.BytesIO(data))
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines()]
        line_no = 0
        for line in lines:
            if not line:
                continue
            line_no += 1
            yield (page_index, line_no, line)


def _match_part_number(line: str) -> str:
    tokens = re.split(r"\s+", line.strip())
    for raw_token in tokens:
        token = raw_token.strip(".,;:()[]{}")
        if PART_NUMBER_PATTERN.fullmatch(token):
            return token

    match = PART_NUMBER_PATTERN.search(line)
    return match.group(0) if match else ""


def _find_nearby_part_number(lines: List[str], index: int) -> str:
    """Locate a part number around ``index``."""
    candidate = _match_part_number(lines[index])
    if candidate:
        return candidate

    # Look backward
    for offset in range(1, 4):
        prev_index = index - offset
        if prev_index < 0:
            break
        prev_line = lines[prev_index]
        if not prev_line.strip():
            break
        candidate = _match_part_number(prev_line)
        if candidate:
            return candidate

    # Look forward
    for offset in range(1, 3):
        next_index = index + offset
        if next_index >= len(lines):
            break
        next_line = lines[next_index]
        if not next_line.strip():
            break
        candidate = _match_part_number(next_line)
        if candidate:
            return candidate

    return ""


def _value_in_line(line: str, raw_value: str) -> bool:
    """Return True when ``raw_value`` can be considered present in line."""
    value = raw_value.strip()
    if not value:
        return False

    boundary_pattern = re.compile(rf"(?<![\d.]){re.escape(value)}(?![\d.])")
    if boundary_pattern.search(line):
        return True

    try:
        target = float(value)
    except ValueError:
        return False

    for match in NUMBER_PATTERN.findall(line):
        try:
            if float(match) == target:
                return True
        except ValueError:
            continue

    return False


def _normalize_cell(value: str) -> str:
    normalized = value.strip()
    if normalized.upper() in {"<NA>", "NA", "N/A"}:
        return ""
    return normalized


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())


def _is_dim_header(header: str, token: str) -> bool:
    if not header:
        return False
    if header == token:
        return True
    if header in {f"{token}MM", f"{token}(MM)", f"{token}寸法", f"{token}寸"}:
        return True
    return header.startswith(f"{token}(") or header.startswith(f"{token}寸")


def _split_dimension(value: str) -> tuple[str, str]:
    normalized = _normalize_cell(value)
    if not normalized:
        return "", ""
    match = re.match(r"^\s*([0-9.]+)\s*±\s*([0-9.]+)\s*$", normalized)
    if match:
        return match.group(1), match.group(2)
    return normalized, ""


def _extract_main_table(pdf_path: str) -> pd.DataFrame:
    tables = camelot.read_pdf(
        pdf_path,
        pages="1",
        flavor="lattice",
        strip_text="\n",
    )
    if not tables:
        raise ValueError("No tables found in PDF.")

    best_table = max(
        tables,
        key=lambda table: table.df.shape[0] * table.df.shape[1],
    )
    df = best_table.df.copy()
    return df.applymap(lambda value: value.strip() if isinstance(value, str) else value)


def _column_match_counts(df: pd.DataFrame) -> list[int]:
    counts: list[int] = []
    for column in df.columns:
        values = df[column].astype(str).fillna("")
        counts.append(
            sum(
                1
                for value in values
                if TABLE_PART_NUMBER_PATTERN.fullmatch(value.strip())
            )
        )
    return counts


def _split_left_right_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = _column_match_counts(df)
    if not counts or max(counts) == 0:
        return df, pd.DataFrame()

    ranked = sorted(
        [(index, count) for index, count in enumerate(counts)],
        key=lambda item: (-item[1], item[0]),
    )
    part_columns = [ranked[0][0]]
    if len(ranked) > 1 and ranked[1][1] > 0:
        part_columns.append(ranked[1][0])

    part_columns = sorted(part_columns)
    if len(part_columns) < 2:
        return df, pd.DataFrame()

    split_index = part_columns[1]
    left = df.iloc[:, :split_index]
    right = df.iloc[:, split_index:]
    return left, right


def _find_header_row_index(df: pd.DataFrame) -> int:
    for idx, row in df.iterrows():
        for cell in row:
            if isinstance(cell, str) and re.search(r"part", cell, re.IGNORECASE):
                return idx
    return 0


def _find_part_column_index(df: pd.DataFrame) -> int:
    counts = _column_match_counts(df)
    if not counts:
        return 0
    return max(range(len(counts)), key=lambda index: counts[index])


def _find_column_by_keywords(headers: list[str], keywords: list[str]) -> Optional[int]:
    for idx, header in enumerate(headers):
        normalized = _normalize_header(header)
        if any(keyword in normalized for keyword in keywords):
            return idx
    return None


def _cleanup_and_correct_fields(
    manufacturer: str,
    catalog_name: str,
    other: str,
) -> tuple[str, str, str]:
    manufacturer = _normalize_cell(manufacturer)
    catalog_name = _normalize_cell(catalog_name)
    other = _normalize_cell(other)

    def looks_like_manufacturer(value: str) -> bool:
        if not value:
            return False
        if re.search(r"\d", value):
            return False
        return bool(re.match(r"^[A-Z0-9 &./()-]+$", value, re.IGNORECASE))

    def looks_like_spec(value: str) -> bool:
        return bool(re.search(r"\d", value)) or any(token in value.upper() for token in ["SPEC", "UL", "ROHS"])

    if not manufacturer and looks_like_manufacturer(catalog_name):
        manufacturer, catalog_name = catalog_name, ""
    if not manufacturer and looks_like_manufacturer(other):
        manufacturer, other = other, ""

    if not catalog_name and other:
        if looks_like_spec(other) and not looks_like_manufacturer(other):
            catalog_name, other = other, ""

    return manufacturer, catalog_name, other


def _build_rows_from_side(side_df: pd.DataFrame, side_label: str) -> list[dict[str, str]]:
    if side_df.empty:
        return []

    header_index = _find_header_row_index(side_df)
    headers = [str(value) if value is not None else "" for value in side_df.iloc[header_index].tolist()]
    data_df = side_df.iloc[header_index + 1 :].reset_index(drop=True)
    if data_df.empty:
        return []

    part_col_index = _find_part_column_index(data_df)

    total_columns = len(headers)
    item_col = _find_column_by_keywords(headers, ["ITEM", "品名"])
    manufacturer_col = _find_column_by_keywords(headers, ["MANUFACTURER", "MAKER", "メーカー"])
    catalog_col = _find_column_by_keywords(headers, ["CATALOG", "CATALOGNAME", "CATNO", "型番"])
    color_col = _find_column_by_keywords(headers, ["COLOR", "色"])
    adhesion_col = _find_column_by_keywords(headers, ["ADHESION", "ADHESIONTYPE", "粘着"])
    other_col = _find_column_by_keywords(headers, ["OTHER", "備考", "REMARK"])

    l_col = None
    w_col = None
    t_col = None
    for idx, header in enumerate(headers):
        normalized = _normalize_header(header)
        if l_col is None and _is_dim_header(normalized, "L"):
            l_col = idx
        if w_col is None and _is_dim_header(normalized, "W"):
            w_col = idx
        if t_col is None and _is_dim_header(normalized, "T"):
            t_col = idx

    column_map = {
        "item_col": item_col,
        "l_col": l_col,
        "w_col": w_col,
        "t_col": t_col,
        "manufacturer_col": manufacturer_col,
        "catalog_col": catalog_col,
        "color_col": color_col,
        "adhesion_col": adhesion_col,
        "other_col": other_col,
    }
    next_index = part_col_index + 1
    for key, value in column_map.items():
        if value is None and next_index < total_columns:
            column_map[key] = next_index
            next_index += 1

    item_col = column_map["item_col"]
    l_col = column_map["l_col"]
    w_col = column_map["w_col"]
    t_col = column_map["t_col"]
    manufacturer_col = column_map["manufacturer_col"]
    catalog_col = column_map["catalog_col"]
    color_col = column_map["color_col"]
    adhesion_col = column_map["adhesion_col"]
    other_col = column_map["other_col"]

    rows: list[dict[str, str]] = []
    for _, row in data_df.iterrows():
        part_number = _normalize_cell(str(row.iloc[part_col_index]) if part_col_index < len(row) else "")
        if not TABLE_PART_NUMBER_PATTERN.fullmatch(part_number):
            continue

        item = _normalize_cell(str(row.iloc[item_col]) if item_col is not None and item_col < len(row) else "")
        l_raw = _normalize_cell(str(row.iloc[l_col]) if l_col is not None and l_col < len(row) else "")
        w_raw = _normalize_cell(str(row.iloc[w_col]) if w_col is not None and w_col < len(row) else "")
        t_value = _normalize_cell(str(row.iloc[t_col]) if t_col is not None and t_col < len(row) else "")
        manufacturer = _normalize_cell(str(row.iloc[manufacturer_col]) if manufacturer_col is not None and manufacturer_col < len(row) else "")
        catalog_name = _normalize_cell(str(row.iloc[catalog_col]) if catalog_col is not None and catalog_col < len(row) else "")
        color = _normalize_cell(str(row.iloc[color_col]) if color_col is not None and color_col < len(row) else "")
        adhesion_type = _normalize_cell(str(row.iloc[adhesion_col]) if adhesion_col is not None and adhesion_col < len(row) else "")
        other = _normalize_cell(str(row.iloc[other_col]) if other_col is not None and other_col < len(row) else "")

        manufacturer, catalog_name, other = _cleanup_and_correct_fields(
            manufacturer,
            catalog_name,
            other,
        )

        l_base, l_tol = _split_dimension(l_raw)
        w_base, w_tol = _split_dimension(w_raw)

        rows.append(
            {
                "Side": side_label,
                "PART No.": part_number,
                "Item": item,
                "L_base": l_base,
                "L_tol": l_tol,
                "W_base": w_base,
                "W_tol": w_tol,
                "T": t_value,
                "MANUFACTURER": manufacturer,
                "CATALOG NAME": catalog_name,
                "Color": color,
                "Adhesion TYPE": adhesion_type,
                "Other": other,
            }
        )
    return rows


def _to_float(value: Optional[str]) -> Optional[float]:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if text == "":
            return None
        return float(text)
    except Exception:
        return None


def _match_number(cell: str, target: Optional[float]) -> bool:
    if target is None:
        return True
    value = _to_float(cell)
    if value is None:
        return False
    return abs(value - target) < 1e-6


def _match_text(cell: str, target: Optional[str]) -> bool:
    if target is None:
        return True
    text = str(target).strip()
    if text == "":
        return True
    return str(cell).strip() == text


def _filter_rows(
    rows: list[dict[str, str]],
    l_value: Optional[str],
    w_value: Optional[str],
    t_value: Optional[str],
) -> list[dict[str, str]]:
    l_target = _to_float(l_value)
    w_target = _to_float(w_value)
    t_text = str(t_value).strip() if t_value is not None else ""
    t_target = t_text if t_text != "" else None

    filtered: list[dict[str, str]] = []
    for row in rows:
        if not _match_number(row.get("L_base", ""), l_target):
            continue
        if not _match_number(row.get("W_base", ""), w_target):
            continue
        if t_target is not None and not _match_text(row.get("T", ""), t_target):
            continue
        filtered.append(row)
    return filtered


def _filter_results(
    lines: List[str],
    l_value: str,
    w_value: str,
    t_value: Optional[str],
    file_name: str,
) -> List[SearchResult]:

    results: List[SearchResult] = []
    t_value_normalized = (t_value or "").strip()
    t_required = bool(t_value_normalized)

    for index, line in enumerate(lines):
        if (
            _value_in_line(line, l_value)
            and _value_in_line(line, w_value)
            and (not t_required or _value_in_line(line, t_value_normalized))
        ):
            part_number = _find_nearby_part_number(lines, index)
            results.append(
                SearchResult(
                    part_number=part_number or "(not found)",
                    matched_line=line,
                    file_name=file_name,
                )
            )
    return results


# --------------------------------------------------------------------
# API endpoints
# --------------------------------------------------------------------
@app.post("/search")
async def search_parts(
    files: List[UploadFile] = File(..., description="PDF files to search"),
    l_value: str = Form(..., description="Target L value"),
    w_value: str = Form(..., description="Target W value"),
    t_value: Optional[str] = Form(None, description="Target T value"),
    return_csv: bool = Form(False, description="If true, return a CSV file"),
):
    all_results: List[SearchResult] = []

    for upload in files:
        lines = list(_read_pdf_lines(upload))
        matches = _filter_results(
            lines,
            l_value,
            w_value,
            t_value,
            upload.filename or "unknown.pdf",
        )
        all_results.extend(matches)

    if return_csv:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["part_number", "matched_line", "file_name"])
        for result in all_results:
            writer.writerow([result.part_number, result.matched_line, result.file_name])
        buffer.seek(0)

        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=search_results.csv",
            },
        )

    return JSONResponse([asdict(result) for result in all_results])


@app.post("/extract_lines_csv")
async def extract_lines_csv(
    files: List[UploadFile] = File(...),
):
    """PDF全文抽出（行単位）をCSVで返す"""
    async def generate():
        yield "\ufeff".encode("utf-8")

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["file_name", "page", "line_no", "text"])
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)

        for upload in files:
            pdf_bytes = await upload.read()
            for page_no, line_no, text in _iter_pdf_text_lines(pdf_bytes):
                writer.writerow(
                    [upload.filename or "unknown.pdf", page_no, line_no, text]
                )
                yield buffer.getvalue().encode("utf-8")
                buffer.seek(0)
                buffer.truncate(0)

    filename = f"pdf_lines_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


async def _extract_table_from_upload(upload: UploadFile) -> pd.DataFrame:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            tmp.write(await upload.read())

        return _extract_main_table(temp_path)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.post("/extract_part_numbers_from_table")
async def extract_part_numbers_from_table(
    files: List[UploadFile] = File(..., description="PDF files to extract part numbers"),
    l_value: Optional[str] = Form(None),
    w_value: Optional[str] = Form(None),
    t_value: Optional[str] = Form(None),
):
    try:
        results: list[dict[str, object]] = []
        for upload in files:
            df = await _extract_table_from_upload(upload)
            left_df, right_df = _split_left_right_tables(df)

            rows: list[dict[str, str]] = []
            rows.extend(_build_rows_from_side(left_df, "Left"))
            rows.extend(_build_rows_from_side(right_df, "Right"))
            rows = _filter_rows(rows, l_value, w_value, t_value)

            part_numbers: set[str] = {row["PART No."] for row in rows if row.get("PART No.")}

            result = {
                "file_name": upload.filename or "unknown.pdf",
                "count": len(part_numbers),
                "part_numbers": sorted(part_numbers),
            }
            results.append(result)

        return JSONResponse(results)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/extract_parts_list_csv")
async def extract_parts_list_csv(
    files: List[UploadFile] = File(..., description="PDF files to extract parts list"),
    l_value: Optional[str] = Form(None),
    w_value: Optional[str] = Form(None),
    t_value: Optional[str] = Form(None),
):
    try:
        all_rows: list[dict[str, str]] = []
        for upload in files:
            df = await _extract_table_from_upload(upload)
            left_df, right_df = _split_left_right_tables(df)

            all_rows.extend(_build_rows_from_side(left_df, "Left"))
            all_rows.extend(_build_rows_from_side(right_df, "Right"))

        all_rows = _filter_rows(all_rows, l_value, w_value, t_value)

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        headers = [
            "Side",
            "PART No.",
            "Item",
            "L_base",
            "L_tol",
            "W_base",
            "W_tol",
            "T",
            "MANUFACTURER",
            "CATALOG NAME",
            "Color",
            "Adhesion TYPE",
            "Other",
        ]
        writer.writerow(headers)
        for row in all_rows:
            writer.writerow([row.get(header, "") for header in headers])

        filename = "parts_list.csv"
        if len(files) > 1:
            filename = f"parts_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        csv_bytes = output.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            iter([csv_bytes]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
