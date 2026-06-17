"""Headerless UPS Billing Data (250-column) CSV preprocessor.

UPS Billing Center's full billing data export is a fixed-width positional CSV
with up to 250 fields and **no header row**. Users can download a separate
header row and prepend it; this module handles the common case where the raw
export is uploaded as-is (e.g. ``Invoice_<account>_<date>.csv``).
"""

from __future__ import annotations

from typing import Any

from app.services.mappers.fedex import _iso_date

UPS_BILLING_VERSION = "2.1"
MIN_COLUMNS = 53

# 0-based column indices for UPS Billing Data CSV v2.1 (250 fields).
COL_VERSION = 0
COL_INVOICE_NUMBER = 1
COL_INVOICE_DATE = 4
COL_ACCOUNT_NUMBER = 5
COL_CURRENCY = 9
COL_INVOICE_TOTAL = 10
COL_TRANSACTION_DATE = 11
COL_TRACKING_NUMBER = 20
COL_BILLED_WEIGHT = 28
COL_ZONE = 31
COL_CHARGE_CLASS = 43
COL_CHARGE_DETAIL = 44
COL_CHARGE_DESCRIPTION = 45
COL_NET_AMOUNT = 52
COL_SENDER_POSTAL = 72
COL_RECEIVER_POSTAL = 80


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return (row[index] or "").strip()


def is_headerless_ups_billing(raw_rows: list[list[str]]) -> bool:
    if not raw_rows:
        return False
    first = raw_rows[0]
    if len(first) < MIN_COLUMNS:
        return False
    if _cell(first, COL_VERSION) != UPS_BILLING_VERSION:
        return False
    tracking = _cell(first, COL_TRACKING_NUMBER)
    if not tracking.upper().startswith("1Z"):
        return False
    # A prepended header row uses text like "Version" / "Invoice Number" in col 0/1.
    if _cell(first, COL_VERSION).replace(".", "").isalpha():
        return False
    return True


def parse_headerless_ups_billing(raw_rows: list[list[str]]) -> list[dict[str, Any]]:
    """Convert positional UPS billing rows into header-named dicts for :class:`UpsBillingCsvMapper`."""
    service_by_tracking: dict[str, str] = {}
    parsed: list[dict[str, Any]] = []

    for row in raw_rows:
        tracking = _cell(row, COL_TRACKING_NUMBER)
        charge_class = _cell(row, COL_CHARGE_CLASS)
        raw_description = _cell(row, COL_CHARGE_DESCRIPTION)
        net_amount = _cell(row, COL_NET_AMOUNT)

        if charge_class == "FRT" and raw_description:
            service_by_tracking[tracking] = raw_description

        # On FRT rows col 45 is the service name (e.g. "WW Saver"), not the charge label.
        if charge_class == "FRT":
            description = "Transportation Charge"
        else:
            description = raw_description or _cell(row, COL_CHARGE_DETAIL) or charge_class

        if not description and not net_amount:
            continue
        if net_amount in ("", "0", "0.0", "0.00"):
            if not description:
                continue

        parsed.append(
            {
                "Invoice Number": _cell(row, COL_INVOICE_NUMBER),
                "Invoice Date": _iso_date(_cell(row, COL_INVOICE_DATE)),
                "Account Number": _cell(row, COL_ACCOUNT_NUMBER),
                "Tracking Number": tracking,
                "Service Level": service_by_tracking.get(tracking) or _cell(row, COL_CHARGE_DETAIL) or charge_class,
                "Pickup Date": _iso_date(_cell(row, COL_TRANSACTION_DATE)),
                "Zone": _cell(row, COL_ZONE),
                "Receiver Postal": _cell(row, COL_RECEIVER_POSTAL),
                "Sender Postal": _cell(row, COL_SENDER_POSTAL),
                "Billed Weight": _cell(row, COL_BILLED_WEIGHT),
                "Charge Description": description,
                "Net Amount": net_amount or "0.00",
                "currency": _cell(row, COL_CURRENCY) or "USD",
            }
        )

    return parsed


__all__ = [
    "UPS_BILLING_VERSION",
    "is_headerless_ups_billing",
    "parse_headerless_ups_billing",
]
