"""Carrier-export mappers.

These convert native carrier billing files into the canonical, one-row-per-charge
dictionaries the fail-closed ingester understands. Mapping is a pure translation
step: no persistence, no audit decisions.
"""

from __future__ import annotations

from app.services.mappers.base import (
    CarrierExportMapper,
    MappedInvoice,
    MapperError,
)
from app.services.mappers.fedex import FedExSelectableCsvMapper
from app.services.mappers.ups import UpsBillingCsvMapper

# Registry of available mappers. Detection is tried in order.
MAPPERS: list[CarrierExportMapper] = [
    UpsBillingCsvMapper(),
    FedExSelectableCsvMapper(),
]

_MAPPERS_BY_NAME: dict[str, CarrierExportMapper] = {m.name: m for m in MAPPERS}

# Friendly carrier hint -> mapper name, for the explicit upload dropdown.
CARRIER_HINTS: dict[str, str] = {
    "UPS": "ups_billing_csv",
    "FEDEX": "fedex_selectable_csv",
}


def get_mapper(name: str) -> CarrierExportMapper | None:
    return _MAPPERS_BY_NAME.get(name)


def mapper_for_hint(hint: str) -> CarrierExportMapper | None:
    name = CARRIER_HINTS.get((hint or "").strip().upper())
    return get_mapper(name) if name else None


def detect_mapper(headers: list[str]) -> CarrierExportMapper | None:
    for mapper in MAPPERS:
        if mapper.detect(headers):
            return mapper
    return None


__all__ = [
    "CARRIER_HINTS",
    "CarrierExportMapper",
    "FedExSelectableCsvMapper",
    "MAPPERS",
    "MappedInvoice",
    "MapperError",
    "UpsBillingCsvMapper",
    "detect_mapper",
    "get_mapper",
    "mapper_for_hint",
]
