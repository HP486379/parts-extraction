from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
