"""Dump Docling extraction output for a local PDF (debugging mapper work).

Usage (from backend/):
  python scripts/inspect_pdf.py ../samples/invoice.pdf
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.mappers import detect_mapper
from app.services.pdf_extraction import DoclingPdfExtractor


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_pdf.py <path-to.pdf>")
        sys.exit(1)

    path = Path(sys.argv[1])
    content = path.read_bytes()
    extraction = DoclingPdfExtractor().extract(content)

    print(f"OCR confidence: {extraction.confidence}")
    print(f"Tables: {len(extraction.tables)}")
    for index, table in enumerate(extraction.tables):
        print(f"\n--- table {index + 1} ({len(table.rows)} rows) ---")
        print("headers:", table.headers)
        mapper = detect_mapper(table.headers)
        print("detected mapper:", mapper.name if mapper else None)
        for row_index, row in enumerate(table.rows[:5]):
            print(f"row {row_index}:", json.dumps(row, default=str)[:500])
    if extraction.text:
        print("\n--- markdown (first 2000 chars) ---")
        print(extraction.text[:2000])


if __name__ == "__main__":
    main()
