import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import CarrierCode, RuleVersion

RULE_PACK_PATH = Path(__file__).resolve().parents[2] / "data" / "carrier_rules" / "rule_pack.json"


class RuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load_seed_rules(self, path: Path = RULE_PACK_PATH) -> int:
        data = json.loads(path.read_text(encoding="utf-8"))
        inserted = 0
        for rule in data["rules"]:
            carrier = CarrierCode(rule["carrier"])
            effective_start = date.fromisoformat(rule["effective_start"])
            effective_end = date.fromisoformat(rule["effective_end"]) if rule["effective_end"] else None
            payload = rule["payload"]
            source_hash = hashlib.sha256(
                json.dumps(rule, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            existing = self.db.scalar(
                select(RuleVersion).where(
                    RuleVersion.carrier == carrier,
                    RuleVersion.rule_type == rule["rule_type"],
                    RuleVersion.effective_start == effective_start,
                    RuleVersion.source_hash == source_hash,
                )
            )
            if existing:
                continue
            self.db.add(
                RuleVersion(
                    carrier=carrier,
                    rule_type=rule["rule_type"],
                    name=rule["name"],
                    effective_start=effective_start,
                    effective_end=effective_end,
                    source_uri=rule.get("source_uri"),
                    source_hash=source_hash,
                    payload=payload,
                )
            )
            inserted += 1
        self.db.commit()
        return inserted

    def get_effective_rule(
        self, carrier: CarrierCode, rule_type: str, on_date: date
    ) -> RuleVersion | None:
        return self.db.scalar(
            select(RuleVersion)
            .where(
                RuleVersion.carrier == carrier,
                RuleVersion.rule_type == rule_type,
                RuleVersion.effective_start <= on_date,
                or_(RuleVersion.effective_end.is_(None), RuleVersion.effective_end >= on_date),
            )
            .order_by(RuleVersion.effective_start.desc(), RuleVersion.created_at.desc())
            .limit(1)
        )

    def area_rule_for_zip(
        self, carrier: CarrierCode, postal_code: str, on_date: date, pickup: bool = False
    ) -> dict[str, Any] | None:
        rule = self.get_effective_rule(carrier, "AREA_SURCHARGE_ZIPS", on_date)
        if not rule:
            return None
        zip5 = postal_code[:5]
        section = "pickup_area" if pickup else "delivery_area"
        payload = rule.payload
        for tier, zips in payload.get(section, {}).items():
            if zip5 in {str(z)[:5] for z in zips}:
                finding_type = "PICKUP_AREA" if pickup else "DELIVERY_AREA"
                if tier == "remote":
                    finding_type = "REMOTE_AREA"
                amount_key = f"{finding_type}.{tier}"
                return {
                    "rule": rule,
                    "zip5": zip5,
                    "section": section,
                    "tier": tier,
                    "finding_type": finding_type,
                    "expected_amount": payload.get("amounts", {}).get(amount_key),
                    "source_uri": rule.source_uri,
                }
        return None

    def fuel_percent(self, carrier: CarrierCode, on_date: date) -> tuple[RuleVersion, float] | None:
        rule = self.get_effective_rule(carrier, "FUEL_SCHEDULE", on_date)
        if not rule:
            return None
        for row in rule.payload.get("weekly_percentages", []):
            start = date.fromisoformat(row["start"])
            end = date.fromisoformat(row["end"])
            if start <= on_date <= end:
                return rule, float(row["percent"])
        return None

    def dim_weight_divisor(self, carrier: CarrierCode, on_date: date) -> tuple[RuleVersion, int] | None:
        rule = self.get_effective_rule(carrier, "DIM_WEIGHT", on_date)
        if not rule:
            return None
        return rule, int(rule.payload.get("divisor", 139))

    def dispute_policy(self, carrier: CarrierCode, on_date: date) -> RuleVersion | None:
        return self.get_effective_rule(carrier, "DISPUTE_POLICY", on_date)

    def list_rules(self) -> list[RuleVersion]:
        return list(self.db.scalars(select(RuleVersion).order_by(RuleVersion.carrier, RuleVersion.name)))

    def has_rules(self) -> bool:
        return self.db.scalar(select(RuleVersion).limit(1)) is not None

    def rules_for_carrier(self, carrier: CarrierCode) -> list[RuleVersion]:
        return list(
            self.db.scalars(
                select(RuleVersion)
                .where(and_(RuleVersion.carrier == carrier))
                .order_by(RuleVersion.rule_type, RuleVersion.effective_start.desc())
            )
        )
