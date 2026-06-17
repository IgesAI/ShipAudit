"""Carrier charge-description -> canonical charge code translation.

Carrier billing files label charges with free-text descriptions or short
abbreviations that differ between UPS and FedEx (and drift over time). Rather
than maintain brittle exact-string tables, we classify each charge by scanning
its description for documented keywords, in priority order.

Charges we recognise map to an :class:`AccessorialType` the audit engine knows
how to reason about. Charges we do not recognise map to ``OTHER`` and are
captured-but-not-claimed: they are ingested so invoice totals reconcile, but the
audit engine never raises a dispute against them. This preserves the fail-closed
guarantee (we never invent a claim from an unidentified charge) while still
letting real, charge-rich invoices load.
"""

from __future__ import annotations

from app.models import AccessorialType

# Ordered (keywords, charge type). Order matters: more specific patterns must
# precede generic ones (e.g. "delivery area" before "residential", because a
# "DAS Residential" line is a delivery-area surcharge, not a residential fee).
_CHARGE_RULES: list[tuple[tuple[str, ...], AccessorialType]] = [
    (("address correction", "adr corr", "adc", "addr correct"), AccessorialType.ADDRESS_CORRECTION),
    (("remote area", "remote delivery", "ras"), AccessorialType.REMOTE_AREA),
    (("pickup area", "pickup surcharge", "pas"), AccessorialType.PICKUP_AREA),
    (("delivery area", "extended area", "das"), AccessorialType.DELIVERY_AREA),
    (("residential", "resi"), AccessorialType.RESIDENTIAL),
    (("fuel",), AccessorialType.FUEL),
    (("dimensional", "dim weight", "dim wt", "dimensional weight"), AccessorialType.DIMENSIONAL_WEIGHT),
    (("earned discount", "incentive", "discount", "incentive credit"), AccessorialType.CONTRACT_DISCOUNT),
    (("minimum", "min charge", "minimum net"), AccessorialType.MINIMUM_CHARGE),
    (
        ("transportation", "freight", "base", "net freight", "ground charge", "service charge"),
        AccessorialType.BASE_RATE,
    ),
]


def classify_charge(description: str) -> AccessorialType:
    """Return the canonical charge type for a carrier charge description.

    Unrecognised descriptions return :attr:`AccessorialType.OTHER` so the line is
    captured for reconciliation but never produces a dispute claim.
    """
    text = (description or "").strip().lower()
    if not text:
        return AccessorialType.OTHER
    for keywords, charge_type in _CHARGE_RULES:
        if any(keyword in text for keyword in keywords):
            return charge_type
    return AccessorialType.OTHER


def charge_code_for(description: str) -> str:
    """Return a canonical charge code string accepted by the ingester.

    The ingester's ``CHARGE_CODE_MAP`` accepts every ``AccessorialType`` value as
    its own code, so we emit the enum value (e.g. ``"FUEL"``, ``"OTHER"``).
    """
    return classify_charge(description).value
