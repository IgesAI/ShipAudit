import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CarrierCode, RateCard, RateCardEntry, Tenant

REQUIRED_CARD_FIELDS = ("carrier", "account_number", "name", "effective_start", "services")
REQUIRED_SERVICE_FIELDS = (
    "service_code",
    "discount_percent",
    "discount_tier",
    "minimum_charge",
    "rate_table",
)


class RateCardValidationError(ValueError):
    """Raised when a rate card document is missing required contract terms."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class RateCardCompiler:
    """Compiles contract rate cards into effective-dated lookup tables.

    Hard-fails on any missing effective date, service table, discount tier,
    minimum charge, or accessorial schedule. Rate audits are impossible without
    a compiled card, by design.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest_json(
        self, tenant: Tenant, document: dict[str, Any], source_artifact_id: str | None = None
    ) -> RateCard:
        reasons = self.validate_document(document)
        if reasons:
            raise RateCardValidationError(reasons)

        source_hash = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = self.db.scalar(
            select(RateCard).where(
                RateCard.tenant_id == tenant.id,
                RateCard.source_file_hash == source_hash,
            )
        )
        if existing:
            return existing

        card = RateCard(
            tenant_id=tenant.id,
            carrier=CarrierCode(document["carrier"]),
            account_number=str(document["account_number"]),
            name=str(document["name"]),
            effective_start=date.fromisoformat(document["effective_start"]),
            effective_end=(
                date.fromisoformat(document["effective_end"]) if document.get("effective_end") else None
            ),
            source_artifact_id=source_artifact_id,
            source_file_hash=source_hash,
            accessorial_schedule=document.get("accessorial_schedule", {}),
        )
        self.db.add(card)
        self.db.flush()
        for service in document["services"]:
            self.db.add(
                RateCardEntry(
                    rate_card_id=card.id,
                    service_code=str(service["service_code"]).strip().upper(),
                    discount_percent=Decimal(str(service["discount_percent"])),
                    discount_tier=str(service["discount_tier"]),
                    minimum_charge=Decimal(str(service["minimum_charge"])).quantize(Decimal("0.01")),
                    rate_table=service["rate_table"],
                )
            )
        self.db.commit()
        self.db.refresh(card)
        return card

    @staticmethod
    def validate_document(document: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        for fieldname in REQUIRED_CARD_FIELDS:
            if fieldname not in document or document[fieldname] in (None, "", []):
                reasons.append(f"rate card missing required field: {fieldname}")
        if "accessorial_schedule" not in document:
            reasons.append("rate card missing required field: accessorial_schedule")
        if document.get("effective_start"):
            try:
                date.fromisoformat(str(document["effective_start"]))
            except ValueError:
                reasons.append(f"unparseable effective_start: {document['effective_start']}")
        if document.get("carrier"):
            try:
                CarrierCode(document["carrier"])
            except ValueError:
                reasons.append(f"unknown carrier: {document['carrier']}")
        for index, service in enumerate(document.get("services") or []):
            for fieldname in REQUIRED_SERVICE_FIELDS:
                if fieldname not in service or service[fieldname] in (None, ""):
                    reasons.append(f"service[{index}] missing required field: {fieldname}")
            if not service.get("rate_table"):
                reasons.append(f"service[{index}] has an empty rate_table")
        return reasons

    def effective_entry(
        self,
        tenant_id: str,
        carrier: CarrierCode,
        account_number: str,
        service_code: str,
        on_date: date,
    ) -> tuple[RateCard, RateCardEntry] | None:
        card = self.db.scalar(
            select(RateCard)
            .where(
                RateCard.tenant_id == tenant_id,
                RateCard.carrier == carrier,
                RateCard.account_number == account_number,
                RateCard.effective_start <= on_date,
                or_(RateCard.effective_end.is_(None), RateCard.effective_end >= on_date),
            )
            .order_by(RateCard.effective_start.desc(), RateCard.created_at.desc())
            .limit(1)
        )
        if not card:
            return None
        entry = self.db.scalar(
            select(RateCardEntry).where(
                RateCardEntry.rate_card_id == card.id,
                RateCardEntry.service_code == service_code.strip().upper(),
            )
        )
        if not entry:
            return None
        return card, entry

    @staticmethod
    def list_rate(entry: RateCardEntry, zone: str, billed_weight_lbs: Decimal) -> Decimal | None:
        """Exact list rate from the contract table; None when not covered."""
        zone_table = entry.rate_table.get(str(zone))
        if not zone_table:
            return None
        weight_key = str(int(billed_weight_lbs.to_integral_value(rounding="ROUND_CEILING")))
        raw = zone_table.get(weight_key)
        if raw is None:
            return None
        return Decimal(str(raw)).quantize(Decimal("0.01"))

    def list_cards(self, tenant_id: str) -> list[RateCard]:
        return list(
            self.db.scalars(
                select(RateCard)
                .where(RateCard.tenant_id == tenant_id)
                .order_by(RateCard.carrier, RateCard.effective_start.desc())
            )
        )


def synthetic_rate_card() -> dict[str, Any]:
    """Demo FedEx contract: 25% ground discount, $9.50 minimum.

    The demo base-rate line bills $16.50 for zone 5 / 5 lbs against a $20.00
    list rate, so the contracted expectation is $15.00 — an over-billing of
    $1.50 that the discount check proves.
    """
    return {
        "carrier": "FEDEX",
        "account_number": "ACCT-001",
        "name": "FedEx ACCT-001 2026 pricing agreement",
        "effective_start": "2026-01-01",
        "effective_end": None,
        "accessorial_schedule": {
            "RESIDENTIAL": 5.25,
            "DELIVERY_AREA": "carrier_list",
            "FUEL": "carrier_schedule",
        },
        "services": [
            {
                "service_code": "GROUND",
                "discount_percent": "0.25",
                "discount_tier": "TIER_3",
                "minimum_charge": "9.50",
                "rate_table": {
                    "5": {"1": "12.00", "2": "13.10", "3": "14.25", "4": "15.40", "5": "20.00", "9": "26.80", "12": "31.40"},
                },
            }
        ],
    }
