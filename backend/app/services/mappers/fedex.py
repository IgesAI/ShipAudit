"""Mapper for the FedEx Selectable CSV billing export.

FedEx Billing Online emits a *wide* file: one row per tracking number, with each
charge component in its own column ("Fuel Surcharge Amount", "Residential Charge
Amount", ...). The set and order of columns is customer-configurable, so we
match columns by documented aliases rather than fixed positions.

For each shipment we emit one canonical charge row per recognised charge column,
then a single balancing ``OTHER`` row for the difference between the shipment's
stated net charge and the sum of recognised charges. That guarantees every
shipment reconciles to its net while capturing charges we do not model (signature,
additional handling, peak surcharges, ...) without ever inventing a dispute.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models import AccessorialType
from app.services.mappers.base import (
    MappedInvoice,
    MapperError,
    build_header_index,
    find_column,
    get_value,
    to_decimal,
)

# Recognised charge-amount columns -> canonical charge code. Order is cosmetic.
_CHARGE_COLUMNS: list[tuple[tuple[str, ...], str]] = [
    (
        ("transportation charge amount", "net freight amount", "freight charge amount", "base charge amount"),
        AccessorialType.BASE_RATE.value,
    ),
    (("fuel surcharge amount", "fuel amount"), AccessorialType.FUEL.value),
    (
        ("residential charge amount", "residential delivery amount", "residential surcharge amount"),
        AccessorialType.RESIDENTIAL.value,
    ),
    (
        ("delivery area surcharge amount", "das amount", "delivery area surcharge extended amount"),
        AccessorialType.DELIVERY_AREA.value,
    ),
    (
        ("address correction charge amount", "address correction amount"),
        AccessorialType.ADDRESS_CORRECTION.value,
    ),
    (
        ("earned discount amount", "grace discount amount", "performance pricing amount"),
        AccessorialType.CONTRACT_DISCOUNT.value,
    ),
]

_RECONCILE_TOLERANCE = Decimal("0.01")


class FedExSelectableCsvMapper:
    name = "fedex_selectable_csv"

    def detect(self, headers: list[str]) -> bool:
        idx = build_header_index(headers)
        has_invoice = find_column(idx, "invoice number") is not None
        has_tracking = (
            find_column(idx, "tracking id", "express or ground tracking id", "ground tracking id") is not None
        )
        has_net = find_column(idx, "net charge amount", "net charges") is not None
        return has_invoice and has_tracking and has_net

    def map(self, rows: list[dict[str, Any]]) -> list[MappedInvoice]:
        if not rows:
            return []
        headers = list(rows[0].keys())
        idx = build_header_index(headers)

        col_invoice = find_column(idx, "invoice number")
        col_invoice_date = find_column(idx, "invoice date")
        col_account = find_column(idx, "account number", "bill to account number", "shipper number")
        col_tracking = find_column(idx, "tracking id", "express or ground tracking id", "ground tracking id")
        col_service = find_column(idx, "service type", "ground service", "service")
        col_ship_date = find_column(idx, "shipment date", "ship date", "pickup date")
        col_net = find_column(idx, "net charge amount", "net charges")
        col_zone = find_column(idx, "rated zone", "zone")
        col_dest_zip = find_column(idx, "recipient zip code", "recipient postal", "destination zip")
        col_origin_zip = find_column(idx, "shipper zip code", "origin zip")
        col_weight = find_column(idx, "rated weight amount", "billed weight", "actual weight amount")

        missing = [
            label
            for label, col in (
                ("invoice number", col_invoice),
                ("invoice date", col_invoice_date),
                ("account number", col_account),
                ("tracking id", col_tracking),
                ("service type", col_service),
                ("ship date", col_ship_date),
                ("net charge amount", col_net),
            )
            if col is None
        ]
        if missing:
            raise MapperError(f"FedEx export is missing required columns: {', '.join(missing)}")

        charge_columns = [
            (col, code)
            for aliases, code in _CHARGE_COLUMNS
            if (col := find_column(idx, *aliases)) is not None
        ]

        invoices: dict[str, MappedInvoice] = {}
        for row in rows:
            invoice_number = get_value(row, col_invoice)
            if not invoice_number:
                continue
            net_amount = to_decimal(get_value(row, col_net))
            base = {
                "carrier": "FEDEX",
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
            }

            charge_rows: list[dict[str, Any]] = []
            recognised_total = Decimal("0.00")
            for col, code in charge_columns:
                amount = to_decimal(get_value(row, col))
                if amount == 0:
                    continue
                recognised_total += amount
                charge_rows.append({**base, "charge_code": code, "description": code, "amount": str(amount)})

            leftover = net_amount - recognised_total
            if abs(leftover) > _RECONCILE_TOLERANCE or not charge_rows:
                charge_rows.append(
                    {
                        **base,
                        "charge_code": AccessorialType.OTHER.value,
                        "description": "Unclassified FedEx charges (captured, not claimed)",
                        "amount": str(leftover if charge_rows else net_amount),
                    }
                )

            invoice = invoices.setdefault(
                invoice_number,
                MappedInvoice(carrier="FEDEX", invoice_number=invoice_number, declared_subtotal=Decimal("0.00")),
            )
            invoice.rows.extend(charge_rows)
            invoice.declared_subtotal += net_amount

        return list(invoices.values())


def _iso_date(value: str) -> str:
    """Best-effort normalise common carrier date formats to ISO ``YYYY-MM-DD``.

    Leaves the value untouched if it is already ISO or unrecognised; the
    downstream ingester performs strict validation and will reject bad dates.
    """
    raw = (value or "").strip()
    if not raw:
        return raw
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y%m%d", "%d-%b-%Y", "%d-%b-%y", "%b %d, %Y", "%b%d,%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw
