import csv
import io
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AccessorialType, Invoice, InvoiceLine
from app.services.ingestion import IngestionService
from app.services.mappers import detect_mapper, mapper_for_hint
from app.services.mappers.ups_billing_250 import is_headerless_ups_billing, parse_headerless_ups_billing
from app.services.mappers.charge_codes import classify_charge
from app.services.security import AuthService

FEDEX_TRACKING = "794612345671"
UPS_TRACKING = "1Z999AA10123456784"


def _csv(rows: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


@pytest.fixture()
def tenant(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Mapper Co", "mapper@example.com", "secret-pass")
    return tenant


# --- charge classification -------------------------------------------------


def test_delivery_area_outranks_residential():
    # "DAS Resi." is a delivery-area surcharge, not a residential fee.
    assert classify_charge("DAS Resi.") == AccessorialType.DELIVERY_AREA
    assert classify_charge("Residential Delivery Charge") == AccessorialType.RESIDENTIAL


def test_unknown_charge_is_other():
    assert classify_charge("Saturday Delivery Premium") == AccessorialType.OTHER
    assert classify_charge("") == AccessorialType.OTHER


# --- format detection ------------------------------------------------------


def test_detection_distinguishes_ups_and_fedex():
    ups_headers = ["Invoice Number", "Tracking Number", "Charge Description", "Net Amount"]
    fedex_headers = ["Invoice Number", "Tracking ID", "Net Charge Amount", "Fuel Surcharge Amount"]
    assert detect_mapper(ups_headers).name == "ups_billing_csv"
    assert detect_mapper(fedex_headers).name == "fedex_selectable_csv"
    assert detect_mapper(["random", "columns"]) is None


def test_carrier_hint_selects_mapper():
    assert mapper_for_hint("UPS").name == "ups_billing_csv"
    assert mapper_for_hint("fedex").name == "fedex_selectable_csv"
    assert mapper_for_hint("dhl") is None


# --- FedEx (wide) ----------------------------------------------------------


def _fedex_rows() -> list[dict]:
    common = {
        "Invoice Number": "FDX-5001",
        "Invoice Date": "03/31/2026",
        "Account Number": "ACCT-1",
        "Service Type": "GROUND",
        "Shipment Date": "03/02/2026",
        "Recipient Zip Code": "59068",
        "Rated Zone": "5",
        "Rated Weight Amount": "5",
    }
    return [
        {
            **common,
            "Tracking ID": FEDEX_TRACKING,
            "Net Charge Amount": "20.00",
            "Transportation Charge Amount": "15.00",
            "Fuel Surcharge Amount": "2.00",
            "Residential Charge Amount": "3.00",
        },
        {
            **common,
            "Tracking ID": FEDEX_TRACKING,
            "Net Charge Amount": "10.00",
            "Transportation Charge Amount": "8.00",
            "Fuel Surcharge Amount": "1.00",
            "Residential Charge Amount": "0.00",
        },
    ]


def test_fedex_export_ingests_and_balances_with_other(db, tenant):
    results = IngestionService(db).ingest_carrier_export(tenant, "fedex.csv", _csv(_fedex_rows()))

    assert len(results) == 1
    invoice = results[0].invoice
    assert invoice is not None
    assert invoice.total_amount == Decimal("30.00")

    lines = db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)).all()
    by_type: dict[AccessorialType, Decimal] = {}
    for line in lines:
        by_type[line.charge_type] = by_type.get(line.charge_type, Decimal("0.00")) + line.amount

    assert by_type[AccessorialType.BASE_RATE] == Decimal("23.00")
    assert by_type[AccessorialType.FUEL] == Decimal("3.00")
    assert by_type[AccessorialType.RESIDENTIAL] == Decimal("3.00")
    # Second shipment's $1.00 gap (net 10 - known 9) is captured, not claimed.
    assert by_type[AccessorialType.OTHER] == Decimal("1.00")


# --- UPS (long) ------------------------------------------------------------


def _ups_rows() -> list[dict]:
    common = {
        "Invoice Number": "UPS-7001",
        "Invoice Date": "2026-03-31",
        "Account Number": "ACCT-9",
        "Tracking Number": UPS_TRACKING,
        "Service Level": "GROUND",
        "Pickup Date": "2026-03-02",
        "Zone": "5",
        "Receiver Postal": "99501",
        "Billed Weight": "12",
    }
    return [
        {**common, "Charge Description": "Freight", "Net Amount": "15.00"},
        {**common, "Charge Description": "Fuel Surcharge", "Net Amount": "2.50"},
        {**common, "Charge Description": "Residential Surcharge", "Net Amount": "3.00"},
        {**common, "Charge Description": "Premier Silver Handling", "Net Amount": "1.00"},
    ]


def test_ups_export_ingests_with_other_capture(db, tenant):
    results = IngestionService(db).ingest_carrier_export(tenant, "ups.csv", _csv(_ups_rows()))

    assert len(results) == 1
    invoice = results[0].invoice
    assert invoice is not None
    assert invoice.total_amount == Decimal("21.50")
    assert results[0].accepted_rows == 4

    lines = db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)).all()
    types = {line.charge_type for line in lines}
    assert AccessorialType.BASE_RATE in types
    assert AccessorialType.FUEL in types
    assert AccessorialType.RESIDENTIAL in types
    assert AccessorialType.OTHER in types  # unmodelled "Premier" fee captured


def test_multiple_invoices_in_one_export_split(db, tenant):
    rows = _ups_rows()
    extra = dict(rows[0])
    extra["Invoice Number"] = "UPS-7002"
    extra["Net Amount"] = "5.00"
    results = IngestionService(db).ingest_carrier_export(tenant, "ups.csv", _csv([*rows, extra]))

    assert len(results) == 2
    invoices = db.scalars(select(Invoice)).all()
    assert {inv.invoice_number for inv in invoices} == {"UPS-7001", "UPS-7002"}


UPS_HEADERLESS_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "ups_headerless_invoice.csv"


def test_headerless_ups_250_column_export_detected():
    raw = UPS_HEADERLESS_SAMPLE.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert is_headerless_ups_billing(rows)
    parsed = parse_headerless_ups_billing(rows)
    assert len(parsed) == 8
    assert parsed[0]["Tracking Number"] == "1Z2A418X0498176640"
    assert parsed[0]["Net Amount"] == "326.69"


def test_headerless_ups_invoice_ingests(db, tenant):
    content = UPS_HEADERLESS_SAMPLE.read_bytes()
    results = IngestionService(db).ingest_carrier_export(tenant, "ups_raw.csv", content)

    assert len(results) == 1
    invoice = results[0].invoice
    assert invoice is not None
    assert invoice.invoice_number == "00002F9511"
    assert invoice.carrier.value == "UPS"
    assert invoice.total_amount == Decimal("1332.97")
    assert results[0].accepted_rows == 8


def test_headerless_ups_reupload_is_idempotent(db, tenant):
    content = UPS_HEADERLESS_SAMPLE.read_bytes()
    service = IngestionService(db)
    first = service.ingest_carrier_export(tenant, "ups_raw.csv", content)
    second = service.ingest_carrier_export(tenant, "ups_raw.csv", content)

    assert first[0].invoice is not None
    assert second[0].invoice is not None
    assert first[0].invoice.id == second[0].invoice.id
    assert second[0].accepted_rows == 8
    assert second[0].rejected_count == 0


def test_unrecognised_export_rejects_whole_file(db, tenant):
    rows = [{"foo": "1", "bar": "2"}]
    results = IngestionService(db).ingest_carrier_export(tenant, "weird.csv", _csv(rows))

    assert len(results) == 1
    assert results[0].invoice is None
    assert any(
        "could not recognise" in reason
        for r in results[0].rejected_rows
        for reason in r.failure_reasons
    )
