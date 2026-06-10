import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessorialType,
    AuditVerdict,
    ConfidenceClass,
    Finding,
    FindingStatus,
    Invoice,
    InvoiceLine,
    RuleAuditResult,
    Shipment,
    StandardizationStatus,
)
from app.services.rate_cards import RateCardCompiler
from app.services.rule_repository import RuleRepository

ROUND_CENTS = Decimal("0.01")
LINE_TOLERANCE = Decimal("0.01")

AREA_TYPES = {
    AccessorialType.DELIVERY_AREA,
    AccessorialType.PICKUP_AREA,
    AccessorialType.REMOTE_AREA,
}


class DeterministicAuditEngine:
    """Fail-closed audit engine.

    Every check resolves to an explicit verdict. A claim (DISCREPANCY) is only
    emitted when the over-billing is mathematically proven against an
    effective-dated carrier rule version or compiled rate card. Anything the
    engine cannot prove fails closed to FAIL_MISSING_SOURCE, REVIEW, or
    NO_CLAIM — never a guess.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.rules = RuleRepository(db)
        self.rate_cards = RateCardCompiler(db)

    def audit_invoice(self, invoice_id: str) -> list[Finding]:
        invoice = self.db.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError(f"invoice not found: {invoice_id}")
        findings: list[Finding] = []
        seen_charges: set[tuple[str, str]] = set()
        for line in invoice.lines:
            for result in self.audit_line(invoice, line, seen_charges):
                existing = self.db.scalar(
                    select(Finding).where(
                        Finding.invoice_line_id == line.id,
                        Finding.finding_type == result.finding_type,
                        Finding.explanation == result.explanation,
                    )
                )
                if existing:
                    continue
                finding = Finding(
                    tenant_id=invoice.tenant_id,
                    invoice_line_id=line.id,
                    shipment_id=line.shipment_id,
                    rule_version_id=result.rule_version_id,
                    finding_type=result.finding_type,
                    verdict=result.verdict,
                    confidence_class=result.confidence_class,
                    status=FindingStatus.OPEN,
                    severity=result.severity,
                    confidence=result.confidence,
                    billed_amount=result.billed_amount,
                    expected_amount=result.expected_amount,
                    recoverable_amount=result.recoverable_amount,
                    explanation=result.explanation,
                    evidence=result.evidence,
                )
                self.db.add(finding)
                findings.append(finding)
        self.db.commit()
        return findings

    def audit_line(
        self,
        invoice: Invoice,
        line: InvoiceLine,
        seen_charges: set[tuple[str, str]] | None = None,
    ) -> list[RuleAuditResult]:
        results: list[RuleAuditResult] = []

        duplicate = self._check_duplicate(invoice, line, seen_charges)
        if duplicate:
            # A duplicate line is claimed in full; running further checks on it
            # would double-count the same dollars.
            return [duplicate]

        shipment = line.shipment
        if not shipment:
            results.append(
                self._fail_missing(
                    line,
                    AccessorialType.OTHER,
                    "No manifest shipment record matches this invoice line. The line cannot be "
                    "audited until the shipment manifest is ingested.",
                    missing="shipment_manifest",
                )
            )
            return results

        checks = [
            self._check_area_surcharge(line, shipment),
            self._check_residential(line, shipment),
            self._check_fuel(invoice, line),
            self._check_dimensional_weight(line, shipment),
            self._check_service_mismatch(invoice, line, shipment),
            self._check_address_correction(line, shipment),
            self._check_contract_rate(invoice, line),
        ]
        results.extend(result for result in checks if result is not None)
        return results

    # ------------------------------------------------------------------ checks

    def _check_duplicate(
        self,
        invoice: Invoice,
        line: InvoiceLine,
        seen_charges: set[tuple[str, str]] | None,
    ) -> RuleAuditResult | None:
        """Same tracking number + charge code billed more than once."""
        key = (line.tracking_number, line.charge_code or line.charge_type.value)
        duplicate_in_invoice = seen_charges is not None and key in seen_charges
        if seen_charges is not None:
            seen_charges.add(key)
        prior_line = self.db.scalar(
            select(InvoiceLine)
            .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
            .where(
                Invoice.tenant_id == invoice.tenant_id,
                Invoice.id != invoice.id,
                InvoiceLine.tracking_number == line.tracking_number,
                InvoiceLine.charge_code == line.charge_code,
            )
        )
        if not duplicate_in_invoice and prior_line is None:
            return None
        evidence = self._base_evidence(invoice, line, line.shipment)
        evidence["duplicate_scope"] = "same_invoice" if duplicate_in_invoice else "prior_invoice"
        if prior_line is not None:
            evidence["prior_invoice_line_id"] = prior_line.id
            evidence["prior_invoice_id"] = prior_line.invoice_id
        return RuleAuditResult(
            finding_type=AccessorialType.DUPLICATE_CHARGE,
            verdict=AuditVerdict.DISCREPANCY,
            explanation=(
                f"Charge code {line.charge_code} for tracking {line.tracking_number} was billed "
                "more than once. Duplicate billing is proven by exact tracking + charge-code match."
            ),
            billed_amount=line.amount,
            expected_amount=Decimal("0.00"),
            recoverable_amount=line.amount,
            confidence=Decimal("0.99000"),
            confidence_class=ConfidenceClass.PROVEN,
            severity="HIGH",
            evidence=evidence,
        )

    def _check_area_surcharge(self, line: InvoiceLine, shipment: Shipment) -> RuleAuditResult | None:
        if line.charge_type not in AREA_TYPES:
            return None
        address = shipment.destination_address
        if not address:
            return self._fail_missing(
                line,
                line.charge_type,
                "Area surcharge cannot be audited: shipment has no destination address record.",
                missing="destination_address",
            )
        postal = address.normalized_postal_code or address.postal_code
        rule = self.rules.get_effective_rule(shipment.carrier, "AREA_SURCHARGE_ZIPS", line.ship_date)
        if not rule:
            return self._fail_missing(
                line,
                line.charge_type,
                f"No {shipment.carrier.value} area-surcharge ZIP list is loaded with an effective "
                f"date covering {line.ship_date}. Fail closed: no claim without the carrier table.",
                missing="carrier_zip_table",
            )
        area = self.rules.area_rule_for_zip(
            shipment.carrier,
            postal,
            line.ship_date,
            pickup=line.charge_type == AccessorialType.PICKUP_AREA,
        )
        evidence = self._base_evidence(line.invoice, line, shipment)
        evidence.update(
            {
                "destination_zip": postal[:5],
                "rule_version_id": rule.id,
                "rule_name": rule.name,
                "rule_source_uri": rule.source_uri,
                "rule_source_hash": rule.source_hash,
                "rule_effective_start": str(rule.effective_start),
            }
        )
        if not area:
            return RuleAuditResult(
                finding_type=line.charge_type,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    f"{line.charge_type.value} billed but destination ZIP {postal[:5]} is not "
                    f"present in the {shipment.carrier.value} area-surcharge ZIP list effective "
                    f"{rule.effective_start}. Exact ZIP membership is zero-tolerance."
                ),
                billed_amount=line.amount,
                expected_amount=Decimal("0.00"),
                recoverable_amount=line.amount,
                confidence=Decimal("0.99000"),
                confidence_class=ConfidenceClass.PROVEN,
                rule_version_id=rule.id,
                severity="HIGH",
                evidence=evidence,
            )
        evidence["matched_tier"] = area["tier"]
        evidence["table_amount"] = str(area.get("expected_amount"))
        expected = to_money(area.get("expected_amount"))
        if expected is not None and line.amount > expected + LINE_TOLERANCE:
            return RuleAuditResult(
                finding_type=line.charge_type,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    f"{line.charge_type.value} applies to ZIP {postal[:5]} but was billed "
                    f"{line.amount} against the effective table amount {expected}."
                ),
                billed_amount=line.amount,
                expected_amount=expected,
                recoverable_amount=(line.amount - expected).quantize(ROUND_CENTS),
                confidence=Decimal("0.97000"),
                confidence_class=ConfidenceClass.PROVEN,
                rule_version_id=rule.id,
                severity="MEDIUM",
                evidence=evidence,
            )
        return RuleAuditResult(
            finding_type=line.charge_type,
            verdict=AuditVerdict.NO_CLAIM,
            explanation=(
                f"ZIP {postal[:5]} is listed in the effective {shipment.carrier.value} "
                f"area-surcharge table (tier {area['tier']}); the carrier rule supports this "
                "charge regardless of how the location appears on a map."
            ),
            billed_amount=line.amount,
            expected_amount=expected,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.99000"),
            confidence_class=ConfidenceClass.PROVEN,
            rule_version_id=rule.id,
            severity="LOW",
            evidence=evidence,
        )

    def _check_residential(self, line: InvoiceLine, shipment: Shipment) -> RuleAuditResult | None:
        if line.charge_type != AccessorialType.RESIDENTIAL:
            return None
        address = shipment.destination_address
        if not address:
            return self._fail_missing(
                line,
                AccessorialType.RESIDENTIAL,
                "Residential surcharge cannot be audited: shipment has no destination address.",
                missing="destination_address",
            )
        evidence = self._base_evidence(line.invoice, line, shipment)
        evidence.update(
            {
                "standardization_status": address.standardization_status.value
                if address.standardization_status
                else None,
                "dpv_confirmed": address.dpv_confirmed,
                "validator_results": address.validator_results,
                "normalized_address": {
                    "line1": address.normalized_line1,
                    "city": address.normalized_city,
                    "state": address.normalized_state,
                    "postal_code": address.normalized_postal_code,
                },
            }
        )
        if address.standardization_status is None or not address.validator_results:
            return self._fail_missing(
                line,
                AccessorialType.RESIDENTIAL,
                "Residential surcharge cannot be audited: no address validation evidence exists.",
                missing="address_validation",
            )
        if address.standardization_status != StandardizationStatus.STANDARDIZED or not address.dpv_confirmed:
            return RuleAuditResult(
                finding_type=AccessorialType.RESIDENTIAL,
                verdict=AuditVerdict.REVIEW,
                explanation=(
                    "Residential surcharge requires manual review: destination address is not "
                    f"cleanly standardized (status={address.standardization_status.value}, "
                    f"dpv_confirmed={address.dpv_confirmed})."
                ),
                billed_amount=line.amount,
                expected_amount=None,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.50000"),
                confidence_class=ConfidenceClass.CONFLICTED,
                severity="MEDIUM",
                evidence=evidence,
            )
        business_votes = [r for r in address.validator_results if r.get("is_residential") is False]
        residential_votes = [r for r in address.validator_results if r.get("is_residential") is True]
        if business_votes and residential_votes:
            return RuleAuditResult(
                finding_type=AccessorialType.RESIDENTIAL,
                verdict=AuditVerdict.REVIEW,
                explanation=(
                    "Address validators disagree on residential vs business classification; "
                    "failing closed to manual review."
                ),
                billed_amount=line.amount,
                expected_amount=None,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.50000"),
                confidence_class=ConfidenceClass.CONFLICTED,
                severity="MEDIUM",
                evidence=evidence,
            )
        if len(business_votes) >= 2 and not residential_votes:
            return RuleAuditResult(
                finding_type=AccessorialType.RESIDENTIAL,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    "Residential surcharge billed on a DPV-confirmed, standardized address that "
                    f"{len(business_votes)} independent validators classify as business/non-residential."
                ),
                billed_amount=line.amount,
                expected_amount=Decimal("0.00"),
                recoverable_amount=line.amount,
                confidence=Decimal("0.93000"),
                confidence_class=ConfidenceClass.STRONG,
                severity="MEDIUM",
                evidence=evidence,
            )
        if residential_votes and not business_votes:
            return RuleAuditResult(
                finding_type=AccessorialType.RESIDENTIAL,
                verdict=AuditVerdict.NO_CLAIM,
                explanation="Validators agree the destination is residential; the charge is supported.",
                billed_amount=line.amount,
                expected_amount=line.amount,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.93000"),
                confidence_class=ConfidenceClass.STRONG,
                severity="LOW",
                evidence=evidence,
            )
        return RuleAuditResult(
            finding_type=AccessorialType.RESIDENTIAL,
            verdict=AuditVerdict.REVIEW,
            explanation=(
                "Fewer than two independent validators agree on a business classification; "
                "insufficient consensus for an automatic residential dispute."
            ),
            billed_amount=line.amount,
            expected_amount=None,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.55000"),
            confidence_class=ConfidenceClass.INSUFFICIENT,
            severity="MEDIUM",
            evidence=evidence,
        )

    def _check_fuel(self, invoice: Invoice, line: InvoiceLine) -> RuleAuditResult | None:
        if line.charge_type != AccessorialType.FUEL:
            return None
        fuel = self.rules.fuel_percent(invoice.carrier, line.ship_date)
        if not fuel:
            return self._fail_missing(
                line,
                AccessorialType.FUEL,
                f"No {invoice.carrier.value} fuel schedule covers ship date {line.ship_date}; "
                "fuel cannot be recomputed.",
                missing="fuel_schedule",
            )
        rule, percent = fuel
        base_line = self.db.scalar(
            select(InvoiceLine).where(
                InvoiceLine.invoice_id == invoice.id,
                InvoiceLine.tracking_number == line.tracking_number,
                InvoiceLine.charge_type == AccessorialType.BASE_RATE,
            )
        )
        if base_line is None:
            return self._fail_missing(
                line,
                AccessorialType.FUEL,
                "Fuel surcharge cannot be recomputed: the invoice has no base freight line for "
                "this tracking number. A quote is not an acceptable base.",
                missing="base_rate_line",
            )
        expected = (base_line.amount * Decimal(str(percent))).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
        evidence = self._base_evidence(invoice, line, line.shipment)
        evidence.update(
            {
                "fuel_percent": percent,
                "base_line_id": base_line.id,
                "base_amount": str(base_line.amount),
                "expected_fuel": str(expected),
                "rule_version_id": rule.id,
                "rule_source_uri": rule.source_uri,
                "rule_source_hash": rule.source_hash,
                "tolerance": str(LINE_TOLERANCE),
            }
        )
        delta = line.amount - expected
        if delta > LINE_TOLERANCE:
            return RuleAuditResult(
                finding_type=AccessorialType.FUEL,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    f"Fuel surcharge {line.amount} exceeds the exact schedule value {expected} "
                    f"({percent:.2%} of base {base_line.amount}) beyond the {LINE_TOLERANCE} "
                    "rounding tolerance."
                ),
                billed_amount=line.amount,
                expected_amount=expected,
                recoverable_amount=delta.quantize(ROUND_CENTS),
                confidence=Decimal("0.97000"),
                confidence_class=ConfidenceClass.PROVEN,
                rule_version_id=rule.id,
                severity="MEDIUM",
                evidence=evidence,
            )
        if delta < -LINE_TOLERANCE:
            return RuleAuditResult(
                finding_type=AccessorialType.FUEL,
                verdict=AuditVerdict.NO_CLAIM,
                explanation="Fuel surcharge is below the schedule value; no recoverable claim exists.",
                billed_amount=line.amount,
                expected_amount=expected,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.97000"),
                confidence_class=ConfidenceClass.PROVEN,
                rule_version_id=rule.id,
                severity="LOW",
                evidence=evidence,
            )
        return RuleAuditResult(
            finding_type=AccessorialType.FUEL,
            verdict=AuditVerdict.PASS,
            explanation="Fuel surcharge matches the effective fuel schedule within rounding tolerance.",
            billed_amount=line.amount,
            expected_amount=expected,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.99000"),
            confidence_class=ConfidenceClass.PROVEN,
            rule_version_id=rule.id,
            severity="LOW",
            evidence=evidence,
        )

    def _check_dimensional_weight(self, line: InvoiceLine, shipment: Shipment) -> RuleAuditResult | None:
        """Dim-weight and reweigh disputes are never auto-disputed: manual review only."""
        if not all(
            [line.billed_length_in, line.billed_width_in, line.billed_height_in, line.billed_weight_lbs]
        ):
            return None
        dim_rule = self.rules.dim_weight_divisor(shipment.carrier, line.ship_date)
        if not dim_rule:
            return None
        rule, divisor = dim_rule
        dim_weight = Decimal(
            math.ceil(float(line.billed_length_in * line.billed_width_in * line.billed_height_in) / divisor)
        )
        manifest_weight = shipment.manifest_weight_lbs or Decimal("0")
        expected_weight = max(dim_weight, manifest_weight)
        if line.billed_weight_lbs <= expected_weight:
            return None
        evidence = self._base_evidence(line.invoice, line, shipment)
        evidence.update(
            {
                "divisor": divisor,
                "computed_dim_weight": str(dim_weight),
                "manifest_weight": str(manifest_weight),
                "billed_weight": str(line.billed_weight_lbs),
                "rule_version_id": rule.id,
                "rule_source_hash": rule.source_hash,
            }
        )
        return RuleAuditResult(
            finding_type=AccessorialType.DIMENSIONAL_WEIGHT,
            verdict=AuditVerdict.REVIEW,
            explanation=(
                f"Billed weight {line.billed_weight_lbs} lbs exceeds the recomputed "
                f"dimensional/manifest weight {expected_weight} lbs. Carriers may re-measure in "
                "transit, so this is a manual-review case, not an automatic dispute."
            ),
            billed_amount=line.amount,
            expected_amount=None,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.70000"),
            confidence_class=ConfidenceClass.CONFLICTED,
            rule_version_id=rule.id,
            severity="MEDIUM",
            evidence=evidence,
        )

    def _check_service_mismatch(
        self, invoice: Invoice, line: InvoiceLine, shipment: Shipment
    ) -> RuleAuditResult | None:
        if line.service_code == shipment.service_code:
            return None
        evidence = self._base_evidence(invoice, line, shipment)
        evidence.update(
            {
                "invoice_service_code": line.service_code,
                "manifest_service_code": shipment.service_code,
            }
        )
        card_entry = self.rate_cards.effective_entry(
            invoice.tenant_id, invoice.carrier, invoice.account_number, shipment.service_code, line.ship_date
        )
        if (
            card_entry
            and line.charge_type == AccessorialType.BASE_RATE
            and line.zone
            and line.billed_weight_lbs
        ):
            card, entry = card_entry
            list_rate = RateCardCompiler.list_rate(entry, line.zone, line.billed_weight_lbs)
            if list_rate is not None:
                expected = max(
                    (list_rate * (Decimal("1") - entry.discount_percent)).quantize(ROUND_CENTS),
                    entry.minimum_charge,
                )
                evidence.update(
                    {
                        "rate_card_id": card.id,
                        "rate_card_hash": card.source_file_hash,
                        "expected_for_manifest_service": str(expected),
                    }
                )
                if line.amount > expected + LINE_TOLERANCE:
                    return RuleAuditResult(
                        finding_type=AccessorialType.SERVICE_MISMATCH,
                        verdict=AuditVerdict.DISCREPANCY,
                        explanation=(
                            f"Invoice billed service {line.service_code} but the manifest requested "
                            f"{shipment.service_code}; re-rating at the contracted manifest-service "
                            f"price {expected} proves an over-billing."
                        ),
                        billed_amount=line.amount,
                        expected_amount=expected,
                        recoverable_amount=(line.amount - expected).quantize(ROUND_CENTS),
                        confidence=Decimal("0.95000"),
                        confidence_class=ConfidenceClass.PROVEN,
                        severity="HIGH",
                        evidence=evidence,
                    )
        return RuleAuditResult(
            finding_type=AccessorialType.SERVICE_MISMATCH,
            verdict=AuditVerdict.REVIEW,
            explanation=(
                f"Invoice service {line.service_code} differs from manifest service "
                f"{shipment.service_code}, but the claim cannot be quantified without a contracted "
                "rate for the manifest service; manual review required."
            ),
            billed_amount=line.amount,
            expected_amount=None,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.70000"),
            confidence_class=ConfidenceClass.CONFLICTED,
            severity="HIGH",
            evidence=evidence,
        )

    def _check_address_correction(self, line: InvoiceLine, shipment: Shipment) -> RuleAuditResult | None:
        if line.charge_type != AccessorialType.ADDRESS_CORRECTION:
            return None
        address = shipment.destination_address
        if not address:
            return self._fail_missing(
                line,
                AccessorialType.ADDRESS_CORRECTION,
                "Address correction fee cannot be audited: no destination address record exists.",
                missing="destination_address",
            )
        if address.standardization_status is None:
            return self._fail_missing(
                line,
                AccessorialType.ADDRESS_CORRECTION,
                "Address correction fee cannot be audited: the original address was never validated.",
                missing="address_validation",
            )
        evidence = self._base_evidence(line.invoice, line, shipment)
        evidence.update(
            {
                "original_line1": address.raw_line1,
                "normalized_line1": address.normalized_line1,
                "standardization_status": address.standardization_status.value,
                "dpv_confirmed": address.dpv_confirmed,
            }
        )
        material_change = (address.raw_line1 or "").strip().upper() != (
            address.normalized_line1 or ""
        ).strip().upper()
        if material_change:
            return RuleAuditResult(
                finding_type=AccessorialType.ADDRESS_CORRECTION,
                verdict=AuditVerdict.NO_CLAIM,
                explanation=(
                    "The submitted address materially differs from its standardized form; the "
                    "correction fee is supported."
                ),
                billed_amount=line.amount,
                expected_amount=line.amount,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.90000"),
                confidence_class=ConfidenceClass.STRONG,
                severity="LOW",
                evidence=evidence,
            )
        if (
            address.standardization_status == StandardizationStatus.STANDARDIZED
            and address.dpv_confirmed
        ):
            return RuleAuditResult(
                finding_type=AccessorialType.ADDRESS_CORRECTION,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    "Address correction fee billed but the originally submitted address already "
                    "standardizes cleanly (DPV-confirmed) with no material field change."
                ),
                billed_amount=line.amount,
                expected_amount=Decimal("0.00"),
                recoverable_amount=line.amount,
                confidence=Decimal("0.92000"),
                confidence_class=ConfidenceClass.STRONG,
                severity="MEDIUM",
                evidence=evidence,
            )
        return RuleAuditResult(
            finding_type=AccessorialType.ADDRESS_CORRECTION,
            verdict=AuditVerdict.REVIEW,
            explanation=(
                "Address correction fee with ambiguous standardization evidence; manual review required."
            ),
            billed_amount=line.amount,
            expected_amount=None,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.55000"),
            confidence_class=ConfidenceClass.CONFLICTED,
            severity="MEDIUM",
            evidence=evidence,
        )

    def _check_contract_rate(self, invoice: Invoice, line: InvoiceLine) -> RuleAuditResult | None:
        """Contracted discount and minimum-charge validation for base freight lines."""
        if line.charge_type != AccessorialType.BASE_RATE:
            return None
        card_entry = self.rate_cards.effective_entry(
            invoice.tenant_id, invoice.carrier, invoice.account_number, line.service_code, line.ship_date
        )
        if card_entry is None:
            return self._fail_missing(
                line,
                AccessorialType.CONTRACT_DISCOUNT,
                f"No compiled rate card covers {invoice.carrier.value} account "
                f"{invoice.account_number} service {line.service_code} on {line.ship_date}; "
                "rate audit is impossible without the contract.",
                missing="rate_card",
            )
        card, entry = card_entry
        if not line.zone or not line.billed_weight_lbs:
            return self._fail_missing(
                line,
                AccessorialType.CONTRACT_DISCOUNT,
                "Base rate line lacks zone or billed weight; the contracted rate cannot be looked up.",
                missing="zone_or_weight",
            )
        list_rate = RateCardCompiler.list_rate(entry, line.zone, line.billed_weight_lbs)
        if list_rate is None:
            return self._fail_missing(
                line,
                AccessorialType.CONTRACT_DISCOUNT,
                f"Rate card {card.name} does not cover zone {line.zone} at "
                f"{line.billed_weight_lbs} lbs; the expected rate cannot be proven.",
                missing="rate_table_cell",
            )
        discounted = (list_rate * (Decimal("1") - entry.discount_percent)).quantize(ROUND_CENTS)
        expected = max(discounted, entry.minimum_charge)
        minimum_governed = discounted < entry.minimum_charge
        evidence = self._base_evidence(invoice, line, line.shipment)
        evidence.update(
            {
                "rate_card_id": card.id,
                "rate_card_name": card.name,
                "rate_card_hash": card.source_file_hash,
                "rate_card_effective_start": str(card.effective_start),
                "list_rate": str(list_rate),
                "discount_percent": str(entry.discount_percent),
                "discount_tier": entry.discount_tier,
                "minimum_charge": str(entry.minimum_charge),
                "expected_net": str(expected),
                "minimum_governed": minimum_governed,
                "tolerance": str(LINE_TOLERANCE),
            }
        )
        delta = line.amount - expected
        finding_type = (
            AccessorialType.MINIMUM_CHARGE if minimum_governed else AccessorialType.CONTRACT_DISCOUNT
        )
        if delta > LINE_TOLERANCE:
            return RuleAuditResult(
                finding_type=finding_type,
                verdict=AuditVerdict.DISCREPANCY,
                explanation=(
                    f"Base charge {line.amount} exceeds the contracted expectation {expected} "
                    f"(list {list_rate}, discount {entry.discount_percent}, minimum "
                    f"{entry.minimum_charge}) from rate card '{card.name}'."
                ),
                billed_amount=line.amount,
                expected_amount=expected,
                recoverable_amount=delta.quantize(ROUND_CENTS),
                confidence=Decimal("0.97000"),
                confidence_class=ConfidenceClass.PROVEN,
                severity="HIGH",
                evidence=evidence,
            )
        if delta < -LINE_TOLERANCE:
            return RuleAuditResult(
                finding_type=finding_type,
                verdict=AuditVerdict.NO_CLAIM,
                explanation="Base charge is below the contracted expectation; no recoverable claim.",
                billed_amount=line.amount,
                expected_amount=expected,
                recoverable_amount=Decimal("0.00"),
                confidence=Decimal("0.97000"),
                confidence_class=ConfidenceClass.PROVEN,
                severity="LOW",
                evidence=evidence,
            )
        return RuleAuditResult(
            finding_type=finding_type,
            verdict=AuditVerdict.PASS,
            explanation="Base charge matches the contracted rate within rounding tolerance.",
            billed_amount=line.amount,
            expected_amount=expected,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.99000"),
            confidence_class=ConfidenceClass.PROVEN,
            severity="LOW",
            evidence=evidence,
        )

    # ----------------------------------------------------------------- helpers

    def _fail_missing(
        self,
        line: InvoiceLine,
        finding_type: AccessorialType,
        explanation: str,
        missing: str,
    ) -> RuleAuditResult:
        evidence = self._base_evidence(line.invoice, line, line.shipment)
        evidence["missing_source"] = missing
        return RuleAuditResult(
            finding_type=finding_type,
            verdict=AuditVerdict.FAIL_MISSING_SOURCE,
            explanation=explanation,
            billed_amount=line.amount,
            expected_amount=None,
            recoverable_amount=Decimal("0.00"),
            confidence=Decimal("0.00000"),
            confidence_class=ConfidenceClass.INSUFFICIENT,
            severity="HIGH",
            evidence=evidence,
        )

    @staticmethod
    def _base_evidence(
        invoice: Invoice, line: InvoiceLine, shipment: Shipment | None
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "invoice_number": invoice.invoice_number,
            "invoice_date": str(invoice.invoice_date),
            "invoice_source_hash": invoice.source_file_hash,
            "tracking_number": line.tracking_number,
            "charge_code": line.charge_code,
            "ship_date": str(line.ship_date),
            "line_provenance": line.provenance,
        }
        if shipment:
            evidence["manifest"] = {
                "shipment_id": shipment.id,
                "service_code": shipment.service_code,
                "ship_date": str(shipment.ship_date),
                "weight_lbs": str(shipment.manifest_weight_lbs) if shipment.manifest_weight_lbs else None,
            }
        return evidence


def to_money(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(ROUND_CENTS)
