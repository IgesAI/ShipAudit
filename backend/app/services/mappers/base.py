"""Shared types and helpers for carrier-export mappers.

A *mapper* converts a carrier's native billing export (UPS billing data CSV,
FedEx Selectable CSV, ...) into the canonical, one-row-per-charge dictionaries
the fail-closed :class:`~app.services.ingestion.IngestionService` already
understands. Mappers do not persist anything and do not make audit decisions;
they only normalise field names, translate charge codes, and split a multi-
invoice export into per-invoice groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable


class MapperError(ValueError):
    """Raised when an export cannot be mapped (e.g. a required column is absent)."""


@dataclass
class MappedInvoice:
    """One invoice extracted from a carrier export.

    ``rows`` are canonical charge-line dictionaries. ``declared_subtotal`` is the
    carrier's stated net total for the invoice and is written onto the first row
    as ``invoice_subtotal`` so the ingester can run its reconciliation gate.
    """

    carrier: str
    invoice_number: str
    declared_subtotal: Decimal
    rows: list[dict[str, Any]] = field(default_factory=list)

    def canonical_rows(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for index, row in enumerate(self.rows):
            enriched = dict(row)
            enriched["invoice_subtotal"] = str(self.declared_subtotal) if index == 0 else ""
            out.append(enriched)
        return out


@runtime_checkable
class CarrierExportMapper(Protocol):
    """Detects and maps a single carrier export format."""

    name: str

    def detect(self, headers: list[str]) -> bool:
        """Return True if this mapper recognises the export's header row."""
        ...

    def map(self, rows: list[dict[str, Any]]) -> list[MappedInvoice]:
        """Convert raw rows into per-invoice canonical groups."""
        ...


def normalize_header(name: str) -> str:
    return " ".join((name or "").strip().lower().replace("_", " ").split())


def build_header_index(headers: list[str]) -> dict[str, str]:
    """Map normalised header names back to their original form."""
    return {normalize_header(h): h for h in headers if h is not None}


def find_column(header_index: dict[str, str], *aliases: str) -> str | None:
    """Return the original header matching any alias (exact, then substring)."""
    normalized_aliases = [normalize_header(a) for a in aliases]
    for alias in normalized_aliases:
        if alias in header_index:
            return header_index[alias]
    for norm, original in header_index.items():
        if any(alias and alias in norm for alias in normalized_aliases):
            return original
    return None


def get_value(row: dict[str, Any], column: str | None) -> str:
    if column is None:
        return ""
    return str(row.get(column) or "").strip()


def to_decimal(value: str) -> Decimal:
    """Parse a money string, tolerating ``$``, commas and parenthesised negatives."""
    raw = (value or "").strip()
    if not raw:
        return Decimal("0.00")
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.strip("()").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return Decimal("0.00")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise MapperError(f"unparseable amount: {value!r}") from exc
    return -amount if negative else amount
