"""FedEx scanned PDF mapper tests (uses the repo sample when present)."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.mappers.fedex_pdf import map_fedex_pdf
from app.services.pdf_extraction import DoclingPdfExtractor

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "lexmark_invoice.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF not available")
def test_lexmark_fedex_pdf_maps_and_reconciles():
    extraction = DoclingPdfExtractor().extract(SAMPLE.read_bytes())
    mapped = map_fedex_pdf(extraction)

    assert len(mapped) == 1
    invoice = mapped[0]
    assert invoice.invoice_number == "9-323-45120"
    assert invoice.declared_subtotal == Decimal("31.17")
    assert invoice.rows[0]["tracking_number"] == "381595808925"
    assert invoice.rows[0]["ship_date"] == "2026-05-27"

    line_sum = sum(Decimal(str(row["amount"])) for row in invoice.rows)
    assert line_sum == invoice.declared_subtotal
