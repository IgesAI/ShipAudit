import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class CarrierCode(StrEnum):
    FEDEX = "FEDEX"
    UPS = "UPS"
    USPS = "USPS"
    ONTRAC = "ONTRAC"
    GLS_US = "GLS_US"
    SPEE_DEE = "SPEE_DEE"
    LSO = "LSO"


class AccessorialType(StrEnum):
    DELIVERY_AREA = "DELIVERY_AREA"
    PICKUP_AREA = "PICKUP_AREA"
    REMOTE_AREA = "REMOTE_AREA"
    RESIDENTIAL = "RESIDENTIAL"
    ADDRESS_CORRECTION = "ADDRESS_CORRECTION"
    FUEL = "FUEL"
    DIMENSIONAL_WEIGHT = "DIMENSIONAL_WEIGHT"
    SERVICE_MISMATCH = "SERVICE_MISMATCH"
    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"
    CONTRACT_DISCOUNT = "CONTRACT_DISCOUNT"
    MINIMUM_CHARGE = "MINIMUM_CHARGE"
    BASE_RATE = "BASE_RATE"
    OTHER = "OTHER"


class AuditVerdict(StrEnum):
    PASS = "PASS"
    FAIL_MISSING_SOURCE = "FAIL_MISSING_SOURCE"
    DISCREPANCY = "DISCREPANCY"
    REVIEW = "REVIEW"
    NO_CLAIM = "NO_CLAIM"


class ConfidenceClass(StrEnum):
    PROVEN = "PROVEN"
    STRONG = "STRONG"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT = "INSUFFICIENT"


class StandardizationStatus(StrEnum):
    STANDARDIZED = "STANDARDIZED"
    INTERPOLATED = "INTERPOLATED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    CASED = "CASED"
    DISPUTED = "DISPUTED"
    CREDITED = "CREDITED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class CaseStatus(StrEnum):
    READY_FOR_AUTO_DISPUTE = "READY_FOR_AUTO_DISPUTE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    WON = "WON"
    LOST = "LOST"
    CLOSED = "CLOSED"


class DisputeStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ERROR = "ERROR"


class RefundStatus(StrEnum):
    EXPECTED = "EXPECTED"
    POSTED = "POSTED"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"
    FINANCE = "FINANCE"
    VIEWER = "VIEWER"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class Carrier(Base):
    __tablename__ = "carriers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (Index("ix_addresses_normalized_hash", "normalized_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_line1: Mapped[str] = mapped_column(String(255))
    raw_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(40))
    postal_code: Mapped[str] = mapped_column(String(20), index=True)
    country: Mapped[str] = mapped_column(String(2), default="US")
    normalized_line1: Mapped[str | None] = mapped_column(String(255))
    normalized_line2: Mapped[str | None] = mapped_column(String(255))
    normalized_city: Mapped[str | None] = mapped_column(String(120))
    normalized_state: Mapped[str | None] = mapped_column(String(40))
    normalized_postal_code: Mapped[str | None] = mapped_column(String(20), index=True)
    normalized_hash: Mapped[str | None] = mapped_column(String(64))
    is_residential: Mapped[bool | None] = mapped_column(Boolean)
    validator: Mapped[str | None] = mapped_column(String(80))
    validator_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    dpv_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    standardization_status: Mapped[StandardizationStatus | None] = mapped_column(
        Enum(StandardizationStatus)
    )
    validator_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    geocode_precision: Mapped[str | None] = mapped_column(String(40))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RawArtifact(Base):
    __tablename__ = "raw_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "carrier", "invoice_number", name="uq_invoice_tenant_carrier_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("raw_artifacts.id"))
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    invoice_number: Mapped[str] = mapped_column(String(120), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    account_number: Mapped[str] = mapped_column(String(120), index=True)
    billing_period: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    source_file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), default="INGESTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (Index("ix_invoice_lines_tracking", "tracking_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    shipment_id: Mapped[str | None] = mapped_column(ForeignKey("shipments.id"), index=True)
    tracking_number: Mapped[str] = mapped_column(String(120), index=True)
    service_code: Mapped[str] = mapped_column(String(80))
    ship_date: Mapped[date] = mapped_column(Date, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    zone: Mapped[str | None] = mapped_column(String(20))
    charge_code: Mapped[str] = mapped_column(String(80), default="", index=True)
    charge_type: Mapped[AccessorialType] = mapped_column(Enum(AccessorialType), default=AccessorialType.OTHER)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    origin_zip: Mapped[str | None] = mapped_column(String(20))
    destination_zip: Mapped[str | None] = mapped_column(String(20), index=True)
    billed_weight_lbs: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    billed_length_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    billed_width_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    billed_height_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    suspicion_score: Mapped[int | None] = mapped_column(Integer)
    suspicion_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    shipment: Mapped["Shipment | None"] = relationship(back_populates="invoice_lines")
    findings: Mapped[list["Finding"]] = relationship(back_populates="invoice_line")


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("tenant_id", "tracking_number", name="uq_shipment_tenant_tracking"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    tracking_number: Mapped[str] = mapped_column(String(120), index=True)
    service_code: Mapped[str] = mapped_column(String(80))
    ship_date: Mapped[date] = mapped_column(Date, index=True)
    origin_address_id: Mapped[str | None] = mapped_column(ForeignKey("addresses.id"))
    destination_address_id: Mapped[str | None] = mapped_column(ForeignKey("addresses.id"))
    manifest_weight_lbs: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    manifest_length_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    manifest_width_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    manifest_height_in: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    declared_residential_flag: Mapped[bool | None] = mapped_column(Boolean)
    quoted_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rate_response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    label_request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    destination_address: Mapped[Address | None] = relationship(foreign_keys=[destination_address_id])
    origin_address: Mapped[Address | None] = relationship(foreign_keys=[origin_address_id])
    invoice_lines: Mapped[list[InvoiceLine]] = relationship(back_populates="shipment")


class ShipmentLeg(Base):
    __tablename__ = "shipment_legs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(80))
    location: Mapped[str | None] = mapped_column(String(255))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Accessorial(Base):
    __tablename__ = "accessorials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_line_id: Mapped[str] = mapped_column(ForeignKey("invoice_lines.id"), index=True)
    accessorial_type: Mapped[AccessorialType] = mapped_column(Enum(AccessorialType), index=True)
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (
        Index("ix_rule_lookup", "carrier", "rule_type", "effective_start", "effective_end"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    rule_type: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    effective_start: Mapped[date] = mapped_column(Date, index=True)
    effective_end: Mapped[date | None] = mapped_column(Date, index=True)
    source_uri: Mapped[str | None] = mapped_column(String(500))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    parsed_by: Mapped[str | None] = mapped_column(String(120))
    approved_by: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RateCard(Base):
    __tablename__ = "rate_cards"
    __table_args__ = (
        Index("ix_rate_card_lookup", "tenant_id", "carrier", "account_number", "effective_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    account_number: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    effective_start: Mapped[date] = mapped_column(Date, index=True)
    effective_end: Mapped[date | None] = mapped_column(Date, index=True)
    source_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("raw_artifacts.id"))
    source_file_hash: Mapped[str] = mapped_column(String(64))
    accessorial_schedule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[list["RateCardEntry"]] = relationship(
        back_populates="rate_card", cascade="all, delete-orphan"
    )


class RateCardEntry(Base):
    __tablename__ = "rate_card_entries"
    __table_args__ = (
        UniqueConstraint("rate_card_id", "service_code", name="uq_rate_card_service"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rate_card_id: Mapped[str] = mapped_column(ForeignKey("rate_cards.id"), index=True)
    service_code: Mapped[str] = mapped_column(String(80), index=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    discount_tier: Mapped[str] = mapped_column(String(80))
    minimum_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    rate_table: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    rate_card: Mapped[RateCard] = relationship(back_populates="entries")


class RejectedRow(Base):
    __tablename__ = "rejected_rows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("raw_artifacts.id"), index=True)
    ingest_stage: Mapped[str] = mapped_column(String(80), index=True)
    row_index: Mapped[int | None] = mapped_column(Integer)
    row_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failure_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_status_type", "status", "finding_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    invoice_line_id: Mapped[str] = mapped_column(ForeignKey("invoice_lines.id"), index=True)
    shipment_id: Mapped[str | None] = mapped_column(ForeignKey("shipments.id"), index=True)
    rule_version_id: Mapped[str | None] = mapped_column(ForeignKey("rule_versions.id"))
    finding_type: Mapped[AccessorialType] = mapped_column(Enum(AccessorialType), index=True)
    verdict: Mapped[AuditVerdict] = mapped_column(
        Enum(AuditVerdict), default=AuditVerdict.REVIEW, index=True
    )
    confidence_class: Mapped[ConfidenceClass] = mapped_column(
        Enum(ConfidenceClass), default=ConfidenceClass.INSUFFICIENT
    )
    status: Mapped[FindingStatus] = mapped_column(Enum(FindingStatus), default=FindingStatus.OPEN)
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), default=Decimal("0.90000"))
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    recoverable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice_line: Mapped[InvoiceLine] = relationship(back_populates="findings")
    cases: Mapped[list["Case"]] = relationship(back_populates="finding")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), index=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.NEEDS_REVIEW)
    auto_dispute_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    dispute_deadline: Mapped[date | None] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    evidence_packet: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_document: Mapped[str | None] = mapped_column(Text)
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    finding: Mapped[Finding] = relationship(back_populates="cases")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="case")


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    status: Mapped[DisputeStatus] = mapped_column(Enum(DisputeStatus), default=DisputeStatus.DRAFT)
    submission_channel: Mapped[str] = mapped_column(String(80))
    external_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="disputes")
    refunds: Mapped[list["RefundLedger"]] = relationship(back_populates="dispute")


class RefundLedger(Base):
    __tablename__ = "refund_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    dispute_id: Mapped[str | None] = mapped_column(ForeignKey("disputes.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(120), index=True)
    tracking_number: Mapped[str] = mapped_column(String(120), index=True)
    charge_type: Mapped[AccessorialType] = mapped_column(Enum(AccessorialType))
    expected_credit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    posted_credit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[RefundStatus] = mapped_column(Enum(RefundStatus), default=RefundStatus.EXPECTED)
    credit_invoice_number: Mapped[str | None] = mapped_column(String(120))
    posted_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    dispute: Mapped[Dispute | None] = relationship(back_populates="refunds")


class CarrierCredential(Base):
    __tablename__ = "carrier_credentials"
    __table_args__ = (UniqueConstraint("tenant_id", "carrier", "name", name="uq_credential_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    carrier: Mapped[CarrierCode] = mapped_column(Enum(CarrierCode), index=True)
    name: Mapped[str] = mapped_column(String(120))
    encrypted_payload: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(120))
    resource_id: Mapped[str | None] = mapped_column(String(120), index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RuleAuditResult:
    """In-memory result of one deterministic check against one invoice line.

    Only DISCREPANCY verdicts carry a recoverable amount. FAIL_MISSING_SOURCE,
    REVIEW, NO_CLAIM, and PASS results are recorded for explainability but never
    become dispute candidates.
    """

    def __init__(
        self,
        finding_type: AccessorialType,
        verdict: AuditVerdict,
        explanation: str,
        billed_amount: Decimal,
        expected_amount: Decimal | None,
        recoverable_amount: Decimal,
        confidence: Decimal,
        evidence: dict[str, Any],
        confidence_class: ConfidenceClass = ConfidenceClass.INSUFFICIENT,
        rule_version_id: str | None = None,
        severity: str = "MEDIUM",
    ) -> None:
        self.finding_type = finding_type
        self.verdict = verdict
        self.explanation = explanation
        self.billed_amount = billed_amount
        self.expected_amount = expected_amount
        self.recoverable_amount = recoverable_amount
        self.confidence = confidence
        self.evidence = evidence
        self.confidence_class = confidence_class
        self.rule_version_id = rule_version_id
        self.severity = severity
