from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, asdict
from typing import Iterable, List

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from PyPDF2 import PdfReader


@dataclass
class SearchResult:
    part_number: str
    matched_line: str
    file_name: str


app = FastAPI(title="Parts Extraction API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PART_NUMBER_PATTERN = re.compile(r"(?=.*\d)[A-Za-z0-9\-_/]{3,}")
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _read_pdf_lines(upload_file: UploadFile) -> Iterable[str]:
    """Yield the text lines contained in ``upload_file``.

    The function reads the uploaded PDF into memory only once so that the
    underlying ``SpooledTemporaryFile`` can be safely reused by other parts of
    the request lifecycle.
    """

    data = upload_file.file.read()
    upload_file.file.seek(0)

    reader = PdfReader(io.BytesIO(data))
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            yield line.strip()


def _match_part_number(line: str) -> str:
    tokens = re.split(r"\s+", line.strip())
    for raw_token in tokens:
        token = raw_token.strip(".,;:()[]{}")
        if PART_NUMBER_PATTERN.fullmatch(token):
            return token

    match = PART_NUMBER_PATTERN.search(line)
    return match.group(0) if match else ""


def _find_nearby_part_number(lines: List[str], index: int) -> str:
    """Locate a part number around ``index``.

    PDF の表構造がテキスト化される際、列ごとに改行されることが多く、L/W
    値と品番が別行に分断される場合がある。そのため、現在行だけでなく周辺
    の数行も含めて部品番号を探索する。
    """

    candidate = _match_part_number(lines[index])
    if candidate:
        return candidate

    # 直前の行から最大 3 行、空行に到達したら打ち切る。
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

    # 直後の行も 2 行まで確認。こちらも空行で区切る。
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
    """Return ``True`` when ``raw_value`` can be considered present in ``line``.

    数値を単なる部分一致で探すと「20」が「120」にヒットするなど誤検出が
    起きやすいため、数値としての比較と、桁をまたがない文字列一致の両方で
    判定を行う。
    """

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


def _filter_results(lines: List[str], l_value: str, w_value: str, file_name: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    for index, line in enumerate(lines):
        if _value_in_line(line, l_value) and _value_in_line(line, w_value):
            part_number = _find_nearby_part_number(lines, index)
            results.append(
                SearchResult(
                    part_number=part_number or "(not found)",
                    matched_line=line,
                    file_name=file_name,
                )
            )
    return results


@app.post("/search")
async def search_parts(
    files: List[UploadFile] = File(..., description="PDF files to search"),
    l_value: str = Form(..., description="Target L value"),
    w_value: str = Form(..., description="Target W value"),
    return_csv: bool = Form(False, description="If true, return a CSV file"),
):
    all_results: List[SearchResult] = []

    for upload in files:
        lines = list(_read_pdf_lines(upload))
        matches = _filter_results(lines, l_value, w_value, upload.filename or "unknown.pdf")
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
