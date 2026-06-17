"""PDF ingestion flow tests using a fake extractor (no Docling/ML required)."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Invoice, RawArtifact
from app.services.ingestion import IngestionService
from app.services.pdf_extraction import ExtractedTable, PdfExtraction, PdfExtractor
from app.services.security import AuthService

FEDEX_TRACKING = "794612345671"


class FakeExtractor(PdfExtractor):
    def __init__(self, extraction: PdfExtraction) -> None:
        self._extraction = extraction

    def extract(self, content: bytes) -> PdfExtraction:
        return self._extraction


@pytest.fixture()
def tenant(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("PDF Co", "pdf@example.com", "secret-pass")
    return tenant


def _fedex_table() -> ExtractedTable:
    headers = [
        "Invoice Number",
        "Invoice Date",
        "Account Number",
        "Tracking ID",
        "Service Type",
        "Shipment Date",
        "Net Charge Amount",
        "Transportation Charge Amount",
        "Fuel Surcharge Amount",
    ]
    rows = [
        {
            "Invoice Number": "PDF-9001",
            "Invoice Date": "03/31/2026",
            "Account Number": "ACCT-1",
            "Tracking ID": FEDEX_TRACKING,
            "Service Type": "GROUND",
            "Shipment Date": "03/02/2026",
            "Net Charge Amount": "18.00",
            "Transportation Charge Amount": "15.00",
            "Fuel Surcharge Amount": "3.00",
        }
    ]
    return ExtractedTable(headers=headers, rows=rows)


def test_low_confidence_pdf_is_rejected(db, tenant):
    extractor = FakeExtractor(PdfExtraction(confidence=0.80, tables=[_fedex_table()]))
    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, "scan.pdf", b"%PDF-1.4 fake", extractor=extractor
    )

    assert artifact.metadata_json["status"] == "rejected_low_confidence"
    assert rejection is not None
    assert db.scalar(select(Invoice)) is None


def test_unreported_confidence_fails_closed(db, tenant):
    extractor = FakeExtractor(PdfExtraction(confidence=None, tables=[_fedex_table()]))
    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, "scan.pdf", b"%PDF-1.4 fake", extractor=extractor
    )

    assert artifact.metadata_json["status"] == "rejected_low_confidence"
    assert rejection is not None


def test_high_confidence_awaits_confirmation_not_audited(db, tenant):
    extractor = FakeExtractor(PdfExtraction(confidence=0.97, tables=[_fedex_table()]))
    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, "scan.pdf", b"%PDF-1.4 fake", extractor=extractor
    )

    assert rejection is None
    assert artifact.metadata_json["status"] == "awaiting_confirmation"
    assert artifact.metadata_json["candidate_invoice_count"] == 1
    assert len(artifact.metadata_json["candidate_rows"]) >= 1
    # Nothing is audited until a human confirms.
    assert db.scalar(select(Invoice)) is None


def test_confirm_pdf_ingests_invoice(db, tenant):
    extractor = FakeExtractor(PdfExtraction(confidence=0.97, tables=[_fedex_table()]))
    service = IngestionService(db)
    artifact, _ = service.ingest_pdf(tenant, "scan.pdf", b"%PDF-1.4 fake", extractor=extractor)

    results = service.confirm_pdf_extraction(tenant, artifact.id)

    assert len(results) == 1
    invoice = results[0].invoice
    assert invoice is not None
    assert invoice.invoice_number == "PDF-9001"
    assert invoice.total_amount == Decimal("18.00")

    stored = db.get(RawArtifact, artifact.id)
    assert stored.metadata_json["status"] == "confirmed"


def test_confirm_unknown_artifact_raises(db, tenant):
    with pytest.raises(ValueError):
        IngestionService(db).confirm_pdf_extraction(tenant, "does-not-exist")


def test_runtime_extraction_failure_fails_closed(db, tenant):
    class BrokenExtractor(PdfExtractor):
        def extract(self, content: bytes) -> PdfExtraction:
            raise OSError("libGL.so.1: cannot open shared object file")

    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, "scan.pdf", b"%PDF-1.4 fake", extractor=BrokenExtractor()
    )

    assert rejection is not None
    assert "libGL.so.1" in rejection.failure_reasons[0]
    assert artifact.metadata_json["extraction_error"] is not None
