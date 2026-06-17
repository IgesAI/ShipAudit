"""Mapper for FedEx billing invoice PDFs (scanned or digital).

FedEx invoice PDFs use a fixed layout: header tables with invoice metadata, a
shipment summary, then a per-tracking detail block with charge labels in one
column and amounts in another. Docling OCR preserves this structure well enough
to map without guessing.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.models import AccessorialType
from app.services.mappers.base import MappedInvoice, to_decimal
from app.services.mappers.charge_codes import charge_code_for
from app.services.mappers.fedex import _iso_date
from app.services.pdf_extraction import ExtractedTable, PdfExtraction

_TRACKING_RE = re.compile(r"\b(\d{12})\b")
_MONEY_RE = re.compile(r"-?\$?\s*(\d+(?:\.\d{2})?)")
_DIM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*Ibs.*?(\d+)\s*inx\s*(\d+)\s*inx\s*(\d+)\s*in", re.I)
_CHARGE_LABELS: dict[str, str] = {
    "transportation charge": AccessorialType.BASE_RATE.value,
    "discount": AccessorialType.CONTRACT_DISCOUNT.value,
    "fuelsurcharge": AccessorialType.FUEL.value,
    "fuel surcharge": AccessorialType.FUEL.value,
    "dasresidential": AccessorialType.DELIVERY_AREA.value,
    "das residential": AccessorialType.DELIVERY_AREA.value,
    "residential delivery": AccessorialType.RESIDENTIAL.value,
}


def map_fedex_pdf(extraction: PdfExtraction) -> list[MappedInvoice]:
    if "fedex" not in extraction.text.lower():
        return []

    invoice_number, invoice_date, account_number, declared_subtotal = _parse_invoice_header(
        extraction.tables
    )
    if not invoice_number or declared_subtotal is None:
        return []

    shipments = _parse_shipments(extraction.tables)
    if not shipments:
        return []

    rows: list[dict[str, Any]] = []
    for shipment in shipments:
        base = {
            "carrier": "FEDEX",
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "account_number": account_number,
            "tracking_number": shipment["tracking_number"],
            "service_code": shipment["service_code"],
            "ship_date": shipment["ship_date"],
            "zone": shipment.get("zone"),
            "billed_weight_lbs": shipment.get("billed_weight_lbs"),
            "billed_length_in": shipment.get("billed_length_in"),
            "billed_width_in": shipment.get("billed_width_in"),
            "billed_height_in": shipment.get("billed_height_in"),
            "currency": "USD",
        }
        for charge in shipment["charges"]:
            rows.append(
                {
                    **base,
                    "charge_code": charge["charge_code"],
                    "description": charge["description"],
                    "amount": str(charge["amount"]),
                }
            )

    return [
        MappedInvoice(
            carrier="FEDEX",
            invoice_number=invoice_number,
            declared_subtotal=declared_subtotal,
            rows=rows,
        )
    ]


def _parse_invoice_header(
    tables: list[ExtractedTable],
) -> tuple[str, str, str, Decimal | None]:
    invoice_number = ""
    invoice_date = ""
    account_number = ""
    declared_subtotal: Decimal | None = None

    for table in tables:
        if "Invoice Number" in table.headers and "Invoice Amount" in table.headers:
            row = table.rows[0] if table.rows else {}
            invoice_number = _cell(row, "Invoice Number")
            account_number = _cell(row, "Account Number")
            declared_subtotal = _parse_money(_cell(row, "Invoice Amount"))
            continue

        # Label row then value row (OCR uses numeric column names).
        if table.rows and _row_has_labels(table.rows[0], ("Invoice Number", "Invoice Date")):
            values = table.rows[1] if len(table.rows) > 1 else {}
            invoice_number = invoice_number or _first_value(values, 0)
            invoice_date = invoice_date or _iso_date(_first_value(values, 1))
            account_number = account_number or _first_value(values, 2)
            continue

        if "Invoice Number" in table.headers and "InvoiceDate" in table.headers:
            row = table.rows[0] if table.rows else {}
            invoice_number = invoice_number or _cell(row, "Invoice Number")
            invoice_date = invoice_date or _iso_date(_cell(row, "InvoiceDate"))
            account_number = account_number or _cell(row, "Account Number")

    if declared_subtotal is None:
        for table in tables:
            for row in table.rows:
                total_cell = " ".join(str(v) for v in row.values())
                if "TOTALTHISINVOICE" in total_cell.replace(" ", "").upper():
                    for match in _MONEY_RE.finditer(total_cell):
                        declared_subtotal = to_decimal(match.group(1))
                    break

    return invoice_number, invoice_date, account_number, declared_subtotal


def _parse_shipments(tables: list[ExtractedTable]) -> list[dict[str, Any]]:
    for table in tables:
        shipment = _parse_shipment_table(table)
        if shipment:
            return [shipment]
    return []


def _parse_shipment_table(table: ExtractedTable) -> dict[str, Any] | None:
    tracking_row_index = None
    tracking_number = ""
    service_code = "GROUND"

    for index, row in enumerate(table.rows):
        blob = " ".join(str(v) for v in row.values())
        match = _TRACKING_RE.search(blob)
        if not match:
            continue
        compact = blob.replace(" ", "")
        if "TrackingID" in compact or "HomeDelivery" in compact or index >= 2:
            tracking_row_index = index
            tracking_number = match.group(1)
            service_code = _extract_service(blob)
            break

    if tracking_row_index is None:
        return None

    ship_date = ""
    dims: dict[str, str] = {}
    zone = ""
    billed_weight = ""
    charges: list[dict[str, Any]] = []

    for row in table.rows[:tracking_row_index]:
        for value in row.values():
            text = str(value)
            if "Ship Date" in text and not ship_date:
                ship_date = _iso_date(_after_label(text, "Ship Date"))
                break
        blob = " ".join(str(v) for v in row.values())
        dim_match = _DIM_RE.search(blob)
        if dim_match:
            dims = {
                "billed_weight_lbs": dim_match.group(1),
                "billed_length_in": dim_match.group(2),
                "billed_width_in": dim_match.group(3),
                "billed_height_in": dim_match.group(4),
            }

    # OCR often merges the first few charge amounts into column 6 on the tracking row.
    tracking_row = table.rows[tracking_row_index]
    merged_amounts = _cell(tracking_row, "6")
    if merged_amounts:
        parts = [_parse_decimal_token(m.group(1), merged_amounts, m.start()) for m in _MONEY_RE.finditer(merged_amounts)]
        parts = [p for p in parts if p is not None]
        if len(parts) >= 2:
            charges.extend(
                [
                    {
                        "charge_code": AccessorialType.BASE_RATE.value,
                        "description": "Transportation Charge",
                        "amount": parts[0],
                    },
                    {
                        "charge_code": AccessorialType.CONTRACT_DISCOUNT.value,
                        "description": "Discount",
                        "amount": -abs(parts[1]),
                    },
                ]
            )
            extras = [
                (AccessorialType.FUEL.value, "Fuel Surcharge"),
                (AccessorialType.DELIVERY_AREA.value, "DAS Residential"),
            ]
            for offset, (code, desc) in enumerate(extras, start=2):
                if offset < len(parts):
                    charges.append({"charge_code": code, "description": desc, "amount": parts[offset]})

    # Additional charge rows (e.g. Residential Delivery) use column 6 only.
    for row in table.rows[tracking_row_index + 1 :]:
        label = _charge_label(row)
        amount_text = _cell(row, "6")
        if not label or "total" in label.lower():
            continue
        amount = _parse_decimal_amount(amount_text)
        if amount is None:
            continue
        normalized = re.sub(r"[^a-z]", "", label.lower())
        charge_code = _CHARGE_LABELS.get(normalized) or charge_code_for(label)
        if any(c["charge_code"] == charge_code for c in charges):
            continue
        charges.append({"charge_code": charge_code, "description": label, "amount": amount})

    # Zone often appears alone in column 1 one row below tracking.
    if tracking_row_index + 2 < len(table.rows):
        zone_candidate = _cell(table.rows[tracking_row_index + 2], "1")
        if zone_candidate.isdigit():
            zone = zone_candidate

    for row in table.rows:
        if "RatedWeight" in "".join(str(v) for v in row.values()):
            weight_match = re.search(r"(\d+(?:\.\d+)?)\s*lbs", " ".join(row.values()), re.I)
            if weight_match:
                billed_weight = weight_match.group(1)

    if not charges:
        return None

    return {
        "tracking_number": tracking_number,
        "service_code": service_code,
        "ship_date": ship_date,
        "zone": zone or None,
        "billed_weight_lbs": billed_weight or dims.get("billed_weight_lbs"),
        "billed_length_in": dims.get("billed_length_in"),
        "billed_width_in": dims.get("billed_width_in"),
        "billed_height_in": dims.get("billed_height_in"),
        "charges": charges,
    }


def _row_has_labels(row: dict[str, Any], labels: tuple[str, ...]) -> bool:
    values = {str(v).strip() for v in row.values()}
    return all(label in values for label in labels)


def _cell(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _first_value(row: dict[str, Any], index: int) -> str:
    key = str(index)
    return str(row.get(key) or "").strip()


def _parse_money(value: str) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    match = _MONEY_RE.search(raw.replace(",", ""))
    if not match:
        return None
    return _parse_decimal_token(match.group(1), raw, match.start())


def _parse_decimal_amount(value: str) -> Decimal | None:
    """Parse a charge cell; require cents to avoid matching zip codes."""
    raw = (value or "").strip()
    if not re.search(r"\d+\.\d{2}", raw):
        return None
    return _parse_money(raw)


def _parse_decimal_token(number: str, context: str, index: int) -> Decimal | None:
    if "." not in number:
        return None
    amount = to_decimal(number)
    window = context[max(0, index - 3) : index + len(number) + 1]
    if "-" in window or context.strip().startswith("-"):
        return -abs(amount)
    return amount


def _extract_service(blob: str) -> str:
    cleaned = blob.replace("HomeDelivery", "HOME_DELIVERY").replace("Home Delivery", "HOME_DELIVERY")
    for token in ("HOME_DELIVERY", "GROUND", "EXPRESS", "PRIORITY"):
        if token.replace("_", " ") in cleaned.upper() or token in cleaned.upper():
            return token
    return "GROUND"


def _after_label(blob: str, label: str) -> str:
    _, _, tail = blob.partition(label)
    return tail.strip(" :")


def _charge_label(row: dict[str, Any]) -> str:
    for key in ("4", "5"):
        text = re.sub(r"\s+", " ", _cell(row, key))
        if not text or text.isdigit() or "USD" in text:
            continue
        lowered = text.lower()
        if any(
            token in lowered
            for token in ("charge", "discount", "surcharge", "residential", "das", "fuel")
        ):
            return text
    return ""


