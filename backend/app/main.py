from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional

import cv2
import numpy as np
from pdf2image import convert_from_bytes
from paddleocr import PaddleOCR
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


@dataclass
class OcrToken:
    text: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int


@dataclass
class OcrLine:
    text: str
    tokens: List[OcrToken]
    part_number: str


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
OCR_PART_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,3}\d{4,6}\b", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

OCR_ENGINE: Optional[PaddleOCR] = None


def _get_ocr_engine() -> PaddleOCR:
    global OCR_ENGINE
    if OCR_ENGINE is None:
        OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang="japan", show_log=False)
    return OCR_ENGINE


def _read_pdf_lines_from_bytes(data: bytes) -> List[str]:
    """Return text lines from a PDF byte stream."""
    reader = PdfReader(io.BytesIO(data))
    lines: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            line_value = line.strip()
            if line_value:
                lines.append(line_value)
    return lines


def _convert_pdf_to_images(data: bytes, dpi: int = 300) -> List[np.ndarray]:
    images = convert_from_bytes(data, dpi=dpi)
    return [cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR) for image in images]


def _detect_table_regions(image: np.ndarray) -> List[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        15,
        10,
    )
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    table_mask = cv2.add(horizontal, vertical)
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    height, width = image.shape[:2]
    page_area = height * width
    regions: List[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < page_area * 0.02:
            continue
        if w < width * 0.15 or h < height * 0.08:
            continue
        if area > page_area * 0.95:
            continue
        regions.append((x, y, w, h))

    if not regions:
        regions.append((0, 0, width, height))

    regions.sort(key=lambda region: (region[1], region[0]))
    return regions


def _extract_ocr_tokens(image: np.ndarray) -> List[OcrToken]:
    ocr_engine = _get_ocr_engine()
    results = ocr_engine.ocr(image, cls=True)
    tokens: List[OcrToken] = []
    if not results or not results[0]:
        return tokens
    for line in results[0]:
        box, (text, _) = line
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        tokens.append(
            OcrToken(
                text=text.strip(),
                x_min=int(min(xs)),
                y_min=int(min(ys)),
                x_max=int(max(xs)),
                y_max=int(max(ys)),
            )
        )
    return [token for token in tokens if token.text]


def _group_tokens_by_line(tokens: List[OcrToken]) -> List[List[OcrToken]]:
    if not tokens:
        return []

    heights = [token.y_max - token.y_min for token in tokens]
    median_height = float(np.median(heights)) if heights else 10.0
    threshold = max(8.0, median_height * 0.6)

    sorted_tokens = sorted(tokens, key=lambda token: (token.y_min + token.y_max) / 2)
    lines: List[List[OcrToken]] = []
    current: List[OcrToken] = []
    current_y: Optional[float] = None

    for token in sorted_tokens:
        y_center = (token.y_min + token.y_max) / 2
        if current_y is None or abs(y_center - current_y) <= threshold:
            current.append(token)
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            lines.append(current)
            current = [token]
            current_y = y_center

    if current:
        lines.append(current)
    return lines


def _is_header_text(text: str) -> bool:
    normalized = text.lower().replace(" ", "")
    return "part" in normalized or "部品" in normalized


def _extract_part_number_from_line(tokens: List[OcrToken], table_width: int) -> str:
    if not tokens:
        return ""
    tokens_sorted = sorted(tokens, key=lambda token: token.x_min)
    left_edge = tokens_sorted[0].x_min
    left_limit = left_edge + max(20, int(table_width * 0.2))
    candidates = [token for token in tokens_sorted if token.x_min <= left_limit]

    for token in candidates:
        if _is_header_text(token.text):
            continue
        match = OCR_PART_NUMBER_PATTERN.search(token.text)
        if match:
            return match.group(0)
    return ""


def _reconstruct_lines(tokens: List[OcrToken], table_width: int) -> List[OcrLine]:
    lines: List[OcrLine] = []
    for line_tokens in _group_tokens_by_line(tokens):
        ordered = sorted(line_tokens, key=lambda token: token.x_min)
        line_text = " ".join(token.text for token in ordered if token.text)
        part_number = _extract_part_number_from_line(ordered, table_width)
        lines.append(OcrLine(text=line_text, tokens=ordered, part_number=part_number))
    return lines


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


def _filter_results_from_ocr(
    lines: List[OcrLine],
    l_value: str,
    w_value: str,
    t_value: Optional[str],
    file_name: str,
) -> List[SearchResult]:
    results: List[SearchResult] = []
    t_value_normalized = (t_value or "").strip()
    t_required = bool(t_value_normalized)

    for line in lines:
        if (
            _value_in_line(line.text, l_value)
            and _value_in_line(line.text, w_value)
            and (not t_required or _value_in_line(line.text, t_value_normalized))
        ):
            results.append(
                SearchResult(
                    part_number=line.part_number or "(not found)",
                    matched_line=line.text,
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
        data = upload.file.read()
        upload.file.seek(0)
        file_name = upload.filename or "unknown.pdf"

        # Entry point: decide between text-layer parsing and OCR-based extraction.
        text_lines = _read_pdf_lines_from_bytes(data)
        if text_lines:
            matches = _filter_results(text_lines, l_value, w_value, t_value, file_name)
            all_results.extend(matches)
            continue

        ocr_lines: List[OcrLine] = []
        for image in _convert_pdf_to_images(data):
            table_regions = _detect_table_regions(image)
            tokens = _extract_ocr_tokens(image)
            for x, y, w, h in table_regions:
                tokens_in_table = [
                    token
                    for token in tokens
                    if x <= token.x_min <= x + w and y <= token.y_min <= y + h
                ]
                ocr_lines.extend(_reconstruct_lines(tokens_in_table, w))

        matches = _filter_results_from_ocr(
            ocr_lines,
            l_value,
            w_value,
            t_value,
            file_name,
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
