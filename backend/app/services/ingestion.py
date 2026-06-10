import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessorialType,
    Address,
    CarrierCode,
    Invoice,
    InvoiceLine,
    RawArtifact,
    RejectedRow,
    Shipment,
    Tenant,
)
from app.services.storage import InMemoryEvidenceStorage

LINE_TOLERANCE = Decimal("0.01")
INVOICE_TOLERANCE = Decimal("0.05")
MIN_OCR_CONFIDENCE = 0.95

# Carrier tracking number formats. Exact-match anchors; an invoice line whose
# tracking number does not match its carrier's pattern is rejected.
TRACKING_PATTERNS: dict[CarrierCode, re.Pattern[str]] = {
    CarrierCode.FEDEX: re.compile(r"^\d{12}(\d{3})?(\d{5,7})?$"),
    CarrierCode.UPS: re.compile(r"^1Z[0-9A-Z]{16}$"),
    CarrierCode.USPS: re.compile(r"^(9\d{19,21}|\d{20,22})$"),
    CarrierCode.ONTRAC: re.compile(r"^[CD]\d{14}$"),
    CarrierCode.GLS_US: re.compile(r"^\d{11,14}$"),
    CarrierCode.SPEE_DEE: re.compile(r"^\d{10,14}$"),
    CarrierCode.LSO: re.compile(r"^[A-Z0-9]{8,20}$"),
}

# Explicit charge-code mapping. Unmapped codes are a hard rejection, never a
# silent fallback to OTHER.
CHARGE_CODE_MAP: dict[str, AccessorialType] = {
    "FRT": AccessorialType.BASE_RATE,
    "BASE": AccessorialType.BASE_RATE,
    "FUEL": AccessorialType.FUEL,
    "RES": AccessorialType.RESIDENTIAL,
    "RESI": AccessorialType.RESIDENTIAL,
    "DAS": AccessorialType.DELIVERY_AREA,
    "DAS_EXT": AccessorialType.DELIVERY_AREA,
    "PAS": AccessorialType.PICKUP_AREA,
    "RAS": AccessorialType.REMOTE_AREA,
    "ADC": AccessorialType.ADDRESS_CORRECTION,
    "DIM": AccessorialType.DIMENSIONAL_WEIGHT,
}
# Enum names are accepted as their own charge codes.
CHARGE_CODE_MAP.update({member.value: member for member in AccessorialType if member != AccessorialType.OTHER})

INVOICE_REQUIRED_FIELDS = (
    "carrier",
    "invoice_number",
    "invoice_date",
    "account_number",
    "tracking_number",
    "service_code",
    "ship_date",
    "charge_code",
    "amount",
)

MANIFEST_REQUIRED_FIELDS = (
    "carrier",
    "tracking_number",
    "service_code",
    "ship_date",
    "origin_line1",
    "origin_city",
    "origin_state",
    "origin_postal_code",
    "dest_line1",
    "dest_city",
    "dest_state",
    "dest_postal_code",
    "manifest_weight_lbs",
    "manifest_length_in",
    "manifest_width_in",
    "manifest_height_in",
)


@dataclass
class IngestResult:
    invoice: Invoice | None = None
    accepted_rows: int = 0
    rejected_rows: list[RejectedRow] = field(default_factory=list)
    artifact: RawArtifact | None = None

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_rows)


def money(value: str | float | Decimal | None) -> Decimal:
    if value in (None, ""):
        raise ValueError("amount is required")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def optional_decimal(value: str | float | Decimal | None) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value.strip())


def validate_invoice_row(row: dict[str, Any]) -> list[str]:
    """Return all hard-fail reasons for one invoice line row."""
    reasons: list[str] = []
    for fieldname in INVOICE_REQUIRED_FIELDS:
        if not str(row.get(fieldname) or "").strip():
            reasons.append(f"missing required field: {fieldname}")
    carrier: CarrierCode | None = None
    if str(row.get("carrier") or "").strip():
        try:
            carrier = CarrierCode(row["carrier"].strip())
        except ValueError:
            reasons.append(f"unknown carrier: {row['carrier']}")
    tracking = str(row.get("tracking_number") or "").strip()
    if carrier and tracking:
        pattern = TRACKING_PATTERNS.get(carrier)
        if pattern and not pattern.match(tracking):
            reasons.append(f"tracking number does not match {carrier.value} format: {tracking}")
    charge_code = str(row.get("charge_code") or "").strip().upper()
    if charge_code and charge_code not in CHARGE_CODE_MAP:
        reasons.append(f"unmapped charge code: {charge_code}")
    for date_field in ("invoice_date", "ship_date"):
        raw = str(row.get(date_field) or "").strip()
        if raw:
            try:
                parse_date(raw)
            except ValueError:
                reasons.append(f"unparseable date in {date_field}: {raw}")
    raw_amount = str(row.get("amount") or "").strip()
    if raw_amount:
        try:
            money(raw_amount)
        except (InvalidOperation, ValueError):
            reasons.append(f"unparseable amount: {raw_amount}")
    return reasons


def validate_manifest_row(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for fieldname in MANIFEST_REQUIRED_FIELDS:
        if not str(row.get(fieldname) or "").strip():
            reasons.append(f"missing required field: {fieldname}")
    if str(row.get("carrier") or "").strip():
        try:
            CarrierCode(row["carrier"].strip())
        except ValueError:
            reasons.append(f"unknown carrier: {row['carrier']}")
    raw_ship_date = str(row.get("ship_date") or "").strip()
    if raw_ship_date:
        try:
            parse_date(raw_ship_date)
        except ValueError:
            reasons.append(f"unparseable date in ship_date: {raw_ship_date}")
    return reasons


class IngestionService:
    """Strict fail-closed compiler from raw carrier files to canonical records.

    Rows that cannot be fully verified are written to ``rejected_rows`` with
    explicit reasons. An invoice whose accepted lines do not reconcile with the
    declared subtotal is rejected entirely.
    """

    def __init__(self, db: Session, storage: InMemoryEvidenceStorage | None = None) -> None:
        self.db = db
        self.storage = storage or InMemoryEvidenceStorage()

    def store_artifact(
        self,
        tenant_id: str,
        artifact_type: str,
        filename: str,
        content: bytes,
        content_type: str = "text/csv",
    ) -> RawArtifact:
        stored = self.storage.put_bytes(f"{tenant_id}/{artifact_type}/{filename}", content, content_type)
        artifact = RawArtifact(
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            original_filename=filename,
            storage_uri=stored.storage_uri,
            content_type=content_type,
            sha256=stored.sha256,
            metadata_json={"size_bytes": stored.size_bytes},
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def _reject(
        self,
        tenant_id: str,
        artifact: RawArtifact | None,
        stage: str,
        row_index: int | None,
        payload: dict[str, Any],
        reasons: list[str],
    ) -> RejectedRow:
        rejected = RejectedRow(
            tenant_id=tenant_id,
            raw_artifact_id=artifact.id if artifact else None,
            ingest_stage=stage,
            row_index=row_index,
            row_payload=payload,
            failure_reasons=reasons,
        )
        self.db.add(rejected)
        return rejected

    def ingest_invoice_csv(
        self, tenant: Tenant, filename: str, content: bytes, content_type: str = "text/csv"
    ) -> IngestResult:
        artifact = self.store_artifact(tenant.id, "invoice", filename, content, content_type)
        result = IngestResult(artifact=artifact)
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        if not rows:
            result.rejected_rows.append(
                self._reject(tenant.id, artifact, "invoice", None, {}, ["file contained no data rows"])
            )
            self.db.commit()
            return result

        header_row = rows[0]
        declared_subtotal = str(header_row.get("invoice_subtotal") or "").strip()
        if not declared_subtotal:
            result.rejected_rows.append(
                self._reject(
                    tenant.id,
                    artifact,
                    "invoice",
                    None,
                    {"invoice_number": header_row.get("invoice_number")},
                    ["missing invoice_subtotal; cannot reconcile line totals against invoice total"],
                )
            )
            self.db.commit()
            return result

        invoice_number = str(header_row.get("invoice_number") or "").strip()
        valid_rows: list[tuple[int, dict[str, Any]]] = []
        for index, row in enumerate(rows):
            reasons = validate_invoice_row(row)
            if str(row.get("invoice_number") or "").strip() != invoice_number:
                reasons.append(
                    "invoice_number differs from file header invoice; one invoice per file is required"
                )
            if reasons:
                result.rejected_rows.append(
                    self._reject(tenant.id, artifact, "invoice", index, dict(row), reasons)
                )
            else:
                valid_rows.append((index, row))

        if not valid_rows:
            self.db.commit()
            return result

        # Reconciliation gate: accepted lines must equal the declared subtotal
        # within tolerance, otherwise the whole invoice fails closed.
        line_sum = sum((money(row["amount"]) for _, row in valid_rows), Decimal("0.00"))
        subtotal = money(declared_subtotal)
        if abs(line_sum - subtotal) > INVOICE_TOLERANCE:
            for index, row in valid_rows:
                result.rejected_rows.append(
                    self._reject(
                        tenant.id,
                        artifact,
                        "invoice",
                        index,
                        dict(row),
                        [
                            "invoice failed subtotal reconciliation: "
                            f"lines sum to {line_sum} but declared subtotal is {subtotal} "
                            f"(tolerance {INVOICE_TOLERANCE})"
                        ],
                    )
                )
            self.db.commit()
            return result

        first = valid_rows[0][1]
        invoice = Invoice(
            tenant_id=tenant.id,
            raw_artifact_id=artifact.id,
            carrier=CarrierCode(first["carrier"].strip()),
            invoice_number=invoice_number,
            invoice_date=parse_date(first["invoice_date"]),
            account_number=first["account_number"].strip(),
            billing_period=str(first.get("billing_period") or "").strip() or None,
            currency=str(first.get("currency") or "USD").strip(),
            total_amount=line_sum,
            source_file_hash=artifact.sha256,
        )
        self.db.add(invoice)
        self.db.flush()

        for index, row in valid_rows:
            shipment = self.db.scalar(
                select(Shipment).where(
                    Shipment.tenant_id == tenant.id,
                    Shipment.tracking_number == row["tracking_number"].strip(),
                )
            )
            charge_code = row["charge_code"].strip().upper()
            line = InvoiceLine(
                invoice_id=invoice.id,
                shipment_id=shipment.id if shipment else None,
                tracking_number=row["tracking_number"].strip(),
                service_code=row["service_code"].strip(),
                ship_date=parse_date(row["ship_date"]),
                delivery_date=(
                    parse_date(row["delivery_date"]) if str(row.get("delivery_date") or "").strip() else None
                ),
                zone=str(row.get("zone") or "").strip() or None,
                charge_code=charge_code,
                charge_type=CHARGE_CODE_MAP[charge_code],
                description=str(row.get("description") or charge_code),
                amount=money(row["amount"]),
                origin_zip=str(row.get("origin_zip") or "").strip() or None,
                destination_zip=str(row.get("destination_zip") or "").strip() or None,
                billed_weight_lbs=optional_decimal(row.get("billed_weight_lbs")),
                billed_length_in=optional_decimal(row.get("billed_length_in")),
                billed_width_in=optional_decimal(row.get("billed_width_in")),
                billed_height_in=optional_decimal(row.get("billed_height_in")),
                provenance={
                    "source_filename": filename,
                    "source_sha256": artifact.sha256,
                    "row_index": index,
                    "format": "csv",
                },
                raw_data=row,
            )
            self.db.add(line)
            result.accepted_rows += 1

        result.invoice = invoice
        self.db.commit()
        self.db.refresh(invoice)
        return result

    def ingest_manifest_csv(self, tenant: Tenant, filename: str, content: bytes) -> IngestResult:
        artifact = self.store_artifact(tenant.id, "manifest", filename, content, "text/csv")
        result = IngestResult(artifact=artifact)
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        for index, row in enumerate(rows):
            reasons = validate_manifest_row(row)
            if reasons:
                result.rejected_rows.append(
                    self._reject(tenant.id, artifact, "manifest", index, dict(row), reasons)
                )
                continue
            destination = Address(
                tenant_id=tenant.id,
                raw_line1=row["dest_line1"],
                raw_line2=row.get("dest_line2") or None,
                city=row["dest_city"],
                state=row["dest_state"],
                postal_code=row["dest_postal_code"],
                country=row.get("dest_country") or "US",
            )
            origin = Address(
                tenant_id=tenant.id,
                raw_line1=row["origin_line1"],
                raw_line2=row.get("origin_line2") or None,
                city=row["origin_city"],
                state=row["origin_state"],
                postal_code=row["origin_postal_code"],
                country=row.get("origin_country") or "US",
            )
            self.db.add_all([destination, origin])
            self.db.flush()
            existing = self.db.scalar(
                select(Shipment).where(
                    Shipment.tenant_id == tenant.id,
                    Shipment.tracking_number == row["tracking_number"].strip(),
                )
            )
            shipment = existing or Shipment(
                tenant_id=tenant.id,
                carrier=CarrierCode(row["carrier"].strip()),
                tracking_number=row["tracking_number"].strip(),
            )
            shipment.service_code = row["service_code"].strip()
            shipment.ship_date = parse_date(row["ship_date"])
            shipment.origin_address_id = origin.id
            shipment.destination_address_id = destination.id
            shipment.manifest_weight_lbs = optional_decimal(row["manifest_weight_lbs"])
            shipment.manifest_length_in = optional_decimal(row["manifest_length_in"])
            shipment.manifest_width_in = optional_decimal(row["manifest_width_in"])
            shipment.manifest_height_in = optional_decimal(row["manifest_height_in"])
            shipment.declared_residential_flag = _parse_bool(row.get("declared_residential"))
            shipment.quoted_amount = optional_decimal(row.get("quoted_amount"))
            shipment.rate_response = {"source": "manifest", "quote_is_evidence_not_truth": True}
            shipment.label_request = row
            self.db.add(shipment)
            result.accepted_rows += 1
        self.db.commit()
        return result

    def ingest_pdf(
        self,
        tenant: Tenant,
        filename: str,
        content: bytes,
        ocr_confidence: float | None = None,
    ) -> tuple[RawArtifact, RejectedRow | None]:
        """Store a PDF invoice for OCR extraction with a fail-closed gate.

        The OCR adapter must report extraction confidence. Below-threshold or
        unreported confidence rejects the document: it is preserved as evidence
        but never enters the canonical invoice tables.
        """
        artifact = self.store_artifact(tenant.id, "invoice_pdf", filename, content, "application/pdf")
        artifact.metadata_json = {
            **artifact.metadata_json,
            "ocr_pipeline": ["ocrmypdf", "tesseract", "invoice2data"],
            "ocr_confidence": ocr_confidence,
            "min_confidence_required": MIN_OCR_CONFIDENCE,
        }
        rejection: RejectedRow | None = None
        if ocr_confidence is None or ocr_confidence < MIN_OCR_CONFIDENCE:
            artifact.metadata_json["status"] = "rejected_low_confidence"
            rejection = self._reject(
                tenant.id,
                artifact,
                "invoice_pdf",
                None,
                {"filename": filename},
                [
                    "OCR confidence "
                    f"{'unreported' if ocr_confidence is None else ocr_confidence} is below the "
                    f"required threshold {MIN_OCR_CONFIDENCE}; document stored but not compiled"
                ],
            )
        else:
            artifact.metadata_json["status"] = "ready_for_extraction"
        self.db.commit()
        return artifact, rejection


def _parse_bool(value: Any) -> bool | None:
    raw = str(value or "").strip().lower()
    if raw in {"true", "1", "yes", "y"}:
        return True
    if raw in {"false", "0", "no", "n"}:
        return False
    return None


DEMO_FEDEX_TRACKING_1 = "794612345671"
DEMO_FEDEX_TRACKING_2 = "794612345682"
DEMO_UPS_TRACKING = "1Z999AA10123456784"


def synthetic_manifest_csv() -> bytes:
    rows: list[dict[str, Any]] = [
        {
            "carrier": "FEDEX",
            "tracking_number": DEMO_FEDEX_TRACKING_1,
            "service_code": "GROUND",
            "ship_date": "2026-02-10",
            "origin_line1": "10 Warehouse Way",
            "origin_city": "Denver",
            "origin_state": "CO",
            "origin_postal_code": "80202",
            "dest_line1": "200 Main St",
            "dest_city": "Red Lodge",
            "dest_state": "MT",
            "dest_postal_code": "59068",
            "manifest_weight_lbs": "5",
            "manifest_length_in": "12",
            "manifest_width_in": "8",
            "manifest_height_in": "6",
            "declared_residential": "false",
            "quoted_amount": "18.20",
        },
        {
            "carrier": "UPS",
            "tracking_number": DEMO_UPS_TRACKING,
            "service_code": "GROUND",
            "ship_date": "2026-02-12",
            "origin_line1": "10 Warehouse Way",
            "origin_city": "Denver",
            "origin_state": "CO",
            "origin_postal_code": "80202",
            "dest_line1": "500 Industrial Blvd",
            "dest_city": "Anchorage",
            "dest_state": "AK",
            "dest_postal_code": "99501",
            "manifest_weight_lbs": "12",
            "manifest_length_in": "20",
            "manifest_width_in": "14",
            "manifest_height_in": "10",
            "declared_residential": "false",
            "quoted_amount": "46.00",
        },
        {
            "carrier": "FEDEX",
            "tracking_number": DEMO_FEDEX_TRACKING_2,
            "service_code": "GROUND",
            "ship_date": "2026-02-13",
            "origin_line1": "10 Warehouse Way",
            "origin_city": "Denver",
            "origin_state": "CO",
            "origin_postal_code": "80202",
            "dest_line1": "1 Hospital Dr",
            "dest_city": "Silverthorne",
            "dest_state": "CO",
            "dest_postal_code": "80435",
            "manifest_weight_lbs": "4",
            "manifest_length_in": "10",
            "manifest_width_in": "6",
            "manifest_height_in": "4",
            "declared_residential": "false",
            "quoted_amount": "14.50",
        },
    ]
    return _csv_bytes(rows)


def synthetic_invoice_csv(carrier: str | None = None) -> bytes:
    """Demo invoices exercising every fail-closed path.

    FedEx INV-100 contains: an unlisted-ZIP DAS charge, a fuel overcharge, a
    duplicate residential charge pair, an under-discounted base rate, a
    dim-weight review case, and one rejected row (missing tracking number).
    UPS INV-101 contains a correctly-listed remote-area charge (NO_CLAIM) and a
    residential charge on a business address.
    """
    fedex_rows = [
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_1, "DAS", "7.95", "5", "12", "8", "6", "59068"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_1, "FUEL", "4.00", "5", "12", "8", "6", "59068"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_1, "FRT", "16.50", "5", "12", "8", "6", "59068"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_2, "DAS", "5.95", "4", "10", "6", "4", "80435"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_2, "RES", "5.25", "4", "10", "6", "4", "80435"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_2, "RES", "5.25", "4", "10", "6", "4", "80435"),
        _invoice_row("FEDEX", "INV-100", DEMO_FEDEX_TRACKING_2, "DIM", "3.40", "9", "10", "6", "4", "80435"),
        # Rejected row: missing tracking number.
        _invoice_row("FEDEX", "INV-100", "", "FUEL", "1.10", "4", "10", "6", "4", "80435"),
    ]
    _set_subtotals(fedex_rows, exclude_indexes={7})
    ups_rows = [
        _invoice_row("UPS", "INV-101", DEMO_UPS_TRACKING, "RAS", "17.25", "12", "20", "14", "10", "99501"),
        _invoice_row("UPS", "INV-101", DEMO_UPS_TRACKING, "RES", "5.50", "12", "20", "14", "10", "99501"),
    ]
    _set_subtotals(ups_rows)
    rows = fedex_rows + ups_rows
    if carrier:
        rows = [row for row in rows if row["carrier"] == carrier]
    return _csv_bytes(rows)


def _set_subtotals(rows: list[dict[str, str]], exclude_indexes: set[int] | None = None) -> None:
    """Declared subtotal covers only the rows that will pass validation."""
    exclude = exclude_indexes or set()
    subtotal = sum(
        (Decimal(row["amount"]) for index, row in enumerate(rows) if index not in exclude),
        Decimal("0.00"),
    )
    for row in rows:
        row["invoice_subtotal"] = str(subtotal)


def _invoice_row(
    carrier: str,
    invoice_number: str,
    tracking: str,
    charge_code: str,
    amount: str,
    billed_weight: str,
    length: str,
    width: str,
    height: str,
    destination_zip: str,
) -> dict[str, str]:
    ship_date = "2026-02-12" if carrier == "UPS" else "2026-02-10"
    if tracking == DEMO_FEDEX_TRACKING_2:
        ship_date = "2026-02-13"
    return {
        "carrier": carrier,
        "invoice_number": invoice_number,
        "invoice_date": "2026-02-28",
        "billing_period": "2026-02",
        "account_number": "ACCT-001",
        "currency": "USD",
        "tracking_number": tracking,
        "service_code": "GROUND",
        "ship_date": ship_date,
        "zone": "5",
        "charge_code": charge_code,
        "description": charge_code,
        "amount": amount,
        "origin_zip": "80202",
        "destination_zip": destination_zip,
        "billed_weight_lbs": billed_weight,
        "billed_length_in": length,
        "billed_width_in": width,
        "billed_height_in": height,
        "invoice_subtotal": "",
    }


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")
