"""Mapper for UPS Billing Data CSV exports.

UPS billing data is already *long*: one row per charge component, each row
carrying the package-level attributes (tracking number, service, dates) plus a
charge description and net amount. This is true of both the 250-column billing
data file (once the downloadable header row is prepended) and the 32-column
summary CSV, so a single header-driven mapper covers both.

Each input row becomes one canonical charge row. The charge description is
classified into a canonical charge code; descriptions we do not recognise become
``OTHER`` (captured, never claimed).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.mappers.base import (
    MappedInvoice,
    MapperError,
    build_header_index,
    find_column,
    get_value,
    to_decimal,
)
from app.services.mappers.charge_codes import charge_code_for
from app.services.mappers.fedex import _iso_date


class UpsBillingCsvMapper:
    name = "ups_billing_csv"

    def detect(self, headers: list[str]) -> bool:
        idx = build_header_index(headers)
        has_invoice = find_column(idx, "invoice number") is not None
        has_tracking = find_column(idx, "tracking number") is not None
        has_charge = find_column(idx, "charge description", "charge category detail code") is not None
        has_amount = find_column(idx, "net amount", "net amount after incentives", "charged amount") is not None
        # FedEx exports use "Tracking ID"; require UPS-style "Tracking Number".
        return has_invoice and has_tracking and has_charge and has_amount

    def map(self, rows: list[dict[str, Any]]) -> list[MappedInvoice]:
        if not rows:
            return []
        headers = list(rows[0].keys())
        idx = build_header_index(headers)

        col_invoice = find_column(idx, "invoice number")
        col_invoice_date = find_column(idx, "invoice date")
        col_account = find_column(idx, "account number", "shipper number")
        col_tracking = find_column(idx, "tracking number")
        col_charge_desc = find_column(idx, "charge description", "charge category detail code")
        col_amount = find_column(idx, "net amount", "net amount after incentives", "charged amount")
        col_service = find_column(idx, "service level", "ups service", "service", "charge classification code")
        col_ship_date = find_column(idx, "pickup date", "shipment date", "ship date", "transaction date")
        col_zone = find_column(idx, "zone", "billed zone")
        col_dest_zip = find_column(idx, "receiver postal", "consignee postal", "destination postal", "ship to postal")
        col_origin_zip = find_column(idx, "sender postal", "shipper postal", "origin postal")
        col_weight = find_column(idx, "billed weight", "package weight", "weight")

        missing = [
            label
            for label, col in (
                ("invoice number", col_invoice),
                ("invoice date", col_invoice_date),
                ("account number", col_account),
                ("tracking number", col_tracking),
                ("charge description", col_charge_desc),
                ("net amount", col_amount),
                ("service level", col_service),
                ("pickup/ship date", col_ship_date),
            )
            if col is None
        ]
        if missing:
            raise MapperError(f"UPS export is missing required columns: {', '.join(missing)}")

        invoices: dict[str, MappedInvoice] = {}
        for row in rows:
            invoice_number = get_value(row, col_invoice)
            if not invoice_number:
                continue
            amount = to_decimal(get_value(row, col_amount))
            description = get_value(row, col_charge_desc)
            canonical = {
                "carrier": "UPS",
                "invoice_number": invoice_number,
                "invoice_date": _iso_date(get_value(row, col_invoice_date)),
                "account_number": get_value(row, col_account),
                "tracking_number": get_value(row, col_tracking),
                "service_code": get_value(row, col_service),
                "ship_date": _iso_date(get_value(row, col_ship_date)),
                "zone": get_value(row, col_zone),
                "destination_zip": get_value(row, col_dest_zip),
                "origin_zip": get_value(row, col_origin_zip),
                "billed_weight_lbs": get_value(row, col_weight),
                "currency": "USD",
                "charge_code": charge_code_for(description),
                "description": description or charge_code_for(description),
                "amount": str(amount),
            }
            invoice = invoices.setdefault(
                invoice_number,
                MappedInvoice(carrier="UPS", invoice_number=invoice_number, declared_subtotal=Decimal("0.00")),
            )
            invoice.rows.append(canonical)
            invoice.declared_subtotal += amount

        return list(invoices.values())
