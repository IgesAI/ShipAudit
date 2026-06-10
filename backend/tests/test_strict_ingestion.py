import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Invoice, RejectedRow
from app.services.ingestion import IngestionService, synthetic_manifest_csv
from app.services.security import AuthService

BASE_ROW = {
    "carrier": "FEDEX",
    "invoice_number": "INV-900",
    "invoice_date": "2026-03-31",
    "billing_period": "2026-03",
    "account_number": "ACCT-001",
    "currency": "USD",
    "tracking_number": "794612345671",
    "service_code": "GROUND",
    "ship_date": "2026-03-02",
    "zone": "5",
    "charge_code": "FRT",
    "description": "Freight",
    "amount": "15.00",
    "origin_zip": "80202",
    "destination_zip": "59068",
    "billed_weight_lbs": "5",
    "billed_length_in": "12",
    "billed_width_in": "8",
    "billed_height_in": "6",
    "invoice_subtotal": "15.00",
}


def _csv(rows: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


@pytest.fixture()
def tenant(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Strict Co", "strict@example.com", "secret-pass")
    return tenant


def test_missing_tracking_number_rejects_row(db, tenant):
    row = {**BASE_ROW, "tracking_number": ""}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is None
    assert result.accepted_rows == 0
    rejected = db.scalars(select(RejectedRow)).all()
    assert len(rejected) == 1
    assert any("tracking_number" in reason for reason in rejected[0].failure_reasons)


def test_invalid_tracking_format_rejects_row(db, tenant):
    row = {**BASE_ROW, "tracking_number": "NOT-A-TRACKING"}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is None
    assert any(
        "does not match FEDEX format" in reason
        for r in result.rejected_rows
        for reason in r.failure_reasons
    )


def test_unmapped_charge_code_rejects_instead_of_defaulting(db, tenant):
    row = {**BASE_ROW, "charge_code": "MYSTERY_FEE"}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is None
    assert any(
        "unmapped charge code" in reason
        for r in result.rejected_rows
        for reason in r.failure_reasons
    )


def test_missing_subtotal_rejects_whole_file(db, tenant):
    row = {**BASE_ROW, "invoice_subtotal": ""}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is None
    assert any(
        "invoice_subtotal" in reason for r in result.rejected_rows for reason in r.failure_reasons
    )


def test_subtotal_mismatch_rejects_whole_invoice(db, tenant):
    row = {**BASE_ROW, "invoice_subtotal": "20.00"}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is None
    assert db.scalar(select(Invoice)) is None
    assert any(
        "subtotal reconciliation" in reason
        for r in result.rejected_rows
        for reason in r.failure_reasons
    )


def test_subtotal_within_tolerance_is_accepted(db, tenant):
    # $0.04 off is inside the +/-$0.05 invoice tolerance.
    row = {**BASE_ROW, "invoice_subtotal": "15.04"}
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([row]))

    assert result.invoice is not None
    assert result.accepted_rows == 1
    assert result.invoice.total_amount == Decimal("15.00")


def test_accepted_line_carries_provenance_and_hash(db, tenant):
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", _csv([BASE_ROW]))

    assert result.invoice is not None
    line = result.invoice.lines[0]
    assert line.provenance["row_index"] == 0
    assert line.provenance["source_sha256"] == result.invoice.source_file_hash
    assert line.charge_code == "FRT"


def test_manifest_row_missing_dimensions_rejected(db, tenant):
    rows = list(csv.DictReader(io.StringIO(synthetic_manifest_csv().decode("utf-8"))))
    rows[0]["manifest_length_in"] = ""
    result = IngestionService(db).ingest_manifest_csv(tenant, "manifest.csv", _csv(rows))

    assert result.accepted_rows == 2
    assert result.rejected_count == 1
    assert any(
        "manifest_length_in" in reason
        for r in result.rejected_rows
        for reason in r.failure_reasons
    )


def test_pdf_below_ocr_confidence_fails_closed(db, tenant):
    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, "scan.pdf", b"%PDF-1.4 fake", ocr_confidence=0.80
    )

    assert artifact.metadata_json["status"] == "rejected_low_confidence"
    assert rejection is not None
    assert any("OCR confidence" in reason for reason in rejection.failure_reasons)
