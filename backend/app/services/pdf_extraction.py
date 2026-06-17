"""PDF invoice extraction via Docling, behind a fail-closed confidence gate.

PDF/OCR extraction is inherently probabilistic, which conflicts with ShipAudit's
"never guess" rule. We reconcile the two by treating extraction as *best effort
evidence gathering*, gated two ways:

1. **Confidence gate** — Docling reports an OCR confidence score. Below the
   configured threshold (or unreported), the document is stored as evidence but
   never compiled into canonical invoice tables.
2. **Human confirmation** — even above threshold, extracted rows are surfaced for
   a person to confirm before they enter the audit. Nothing is disputed off an
   unconfirmed OCR read.

Docling pulls in heavy ML models, so it is imported lazily and treated as an
optional dependency: if it is not installed the PDF path degrades to "extraction
unavailable" rather than breaking the app.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class PdfExtractionUnavailable(RuntimeError):
    """Raised when no PDF extraction backend is installed/usable."""


@dataclass
class ExtractedTable:
    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PdfExtraction:
    """Result of extracting a PDF.

    ``confidence`` is ``None`` when the backend could not produce a trustworthy
    score (treated as a failure by the gate).
    """

    confidence: float | None
    tables: list[ExtractedTable] = field(default_factory=list)
    text: str = ""


@runtime_checkable
class PdfExtractor(Protocol):
    def extract(self, content: bytes) -> PdfExtraction: ...


class DoclingPdfExtractor:
    """Docling-backed extractor. Imports Docling lazily on first use."""

    def __init__(self, accurate_tables: bool = True) -> None:
        self.accurate_tables = accurate_tables
        self._converter = None

    def _build_converter(self):  # pragma: no cover - exercised only with docling installed
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions,
                TableFormerMode,
                TableStructureOptions,
            )
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise PdfExtractionUnavailable(
                "Docling is not installed. Install the optional 'pdf' extra to enable PDF ingestion."
            ) from exc

        pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
        pipeline_options.table_structure_options = TableStructureOptions(
            do_cell_matching=True,
            mode=TableFormerMode.ACCURATE if self.accurate_tables else TableFormerMode.FAST,
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )

    def extract(self, content: bytes) -> PdfExtraction:  # pragma: no cover - needs docling + models
        try:
            from docling.datamodel.base_models import DocumentStream
        except ImportError as exc:
            raise PdfExtractionUnavailable("Docling is not installed.") from exc

        if self._converter is None:
            self._converter = self._build_converter()

        stream = DocumentStream(name="invoice.pdf", stream=io.BytesIO(content))
        result = self._converter.convert(stream)

        confidence = _coerce_confidence(getattr(result, "confidence", None))
        tables: list[ExtractedTable] = []
        document = getattr(result, "document", None)
        for table in getattr(document, "tables", []) or []:
            tables.append(_table_to_extracted(table, document))
        text = document.export_to_markdown() if document is not None else ""
        return PdfExtraction(confidence=confidence, tables=tables, text=text)


def _coerce_confidence(report: object) -> float | None:
    if report is None:
        return None
    raw = getattr(report, "ocr_score", None)
    try:
        score = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    # NaN/inf (e.g. a digital PDF where OCR never ran) is ambiguous -> fail closed.
    if math.isnan(score) or math.isinf(score):
        return None
    return score


def _table_to_extracted(table: object, document: object) -> ExtractedTable:  # pragma: no cover
    try:
        import pandas as pd

        df = table.export_to_dataframe(doc=document)  # type: ignore[attr-defined]
        headers = _dedupe_headers([str(c) for c in df.columns])
        rows = [
            {headers[i]: ("" if pd.isna(v) else str(v)) for i, v in enumerate(record.values())}
            for record in df.to_dict("records")
        ]
        return ExtractedTable(headers=headers, rows=rows)
    except Exception:
        return ExtractedTable()


def _dedupe_headers(headers: list[str]) -> list[str]:
    """Keep duplicate OCR column labels distinct so row values are not dropped."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for header in headers:
        count = seen.get(header, 0)
        seen[header] = count + 1
        out.append(header if count == 0 else f"{header}_{count + 1}")
    return out


def default_pdf_extractor() -> PdfExtractor | None:
    """Return a Docling extractor, or ``None`` if Docling cannot be loaded."""
    extractor = DoclingPdfExtractor()
    try:
        extractor._build_converter()
    except PdfExtractionUnavailable:
        return None
    return extractor
