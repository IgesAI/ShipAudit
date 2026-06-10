from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Address, RuleVersion


@dataclass(frozen=True)
class QualityIssue:
    suite: str
    message: str
    severity: str = "error"


class DataQualityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_rule_tables(self) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        rules = list(self.db.scalars(select(RuleVersion)))
        frame = pd.DataFrame(
            [
                {
                    "carrier": rule.carrier.value,
                    "rule_type": rule.rule_type,
                    "effective_start": rule.effective_start,
                    "payload_present": bool(rule.payload),
                    "source_hash": rule.source_hash,
                }
                for rule in rules
            ]
        )
        if frame.empty:
            return [QualityIssue("carrier_rules", "No carrier rules loaded")]
        if frame["source_hash"].isna().any():
            issues.append(QualityIssue("carrier_rules", "Every rule must have a source hash"))
        if not frame["payload_present"].all():
            issues.append(QualityIssue("carrier_rules", "Every rule must have a non-empty payload"))
        duplicates = frame.duplicated(subset=["carrier", "rule_type", "effective_start"])
        if duplicates.any():
            issues.append(QualityIssue("carrier_rules", "Duplicate carrier/rule/effective-start rows detected"))
        for rule in rules:
            if rule.rule_type == "AREA_SURCHARGE_ZIPS":
                payload = rule.payload
                if "delivery_area" not in payload or "amounts" not in payload:
                    issues.append(QualityIssue("carrier_rules", f"{rule.name} missing area surcharge keys"))
        return issues

    def validate_addresses(self, tenant_id: str) -> list[QualityIssue]:
        addresses = list(self.db.scalars(select(Address).where(Address.tenant_id == tenant_id)))
        issues: list[QualityIssue] = []
        for address in addresses:
            if not address.normalized_hash:
                issues.append(QualityIssue("addresses", f"Address {address.id} was not normalized"))
            if address.country == "US" and len((address.normalized_postal_code or address.postal_code)[:5]) != 5:
                issues.append(QualityIssue("addresses", f"Address {address.id} has invalid US ZIP"))
        return issues

    def validate_all(self, tenant_id: str) -> list[QualityIssue]:
        return [*self.validate_rule_tables(), *self.validate_addresses(tenant_id)]
