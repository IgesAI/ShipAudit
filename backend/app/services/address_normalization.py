import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Address, StandardizationStatus

try:
    import usaddress
except ModuleNotFoundError:  # pragma: no cover - exercised in lean local environments
    usaddress = None

PO_BOX_PATTERN = re.compile(r"\b(P\.?\s*O\.?\s*BOX|POST\s+OFFICE\s+BOX)\b", re.IGNORECASE)
RURAL_ROUTE_PATTERN = re.compile(r"\b(RR|RURAL\s+ROUTE|HC)\s*\d", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    validator: str
    normalized_line1: str
    normalized_line2: str | None
    city: str
    state: str
    postal_code: str
    is_residential: bool | None
    confidence: Decimal
    geocode_precision: str
    dpv_confirmed: bool
    flags: list[str] = field(default_factory=list)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    metadata: dict | None = None

    def as_record(self) -> dict:
        return {
            "validator": self.validator,
            "normalized_line1": self.normalized_line1,
            "postal_code": self.postal_code,
            "is_residential": self.is_residential,
            "confidence": float(self.confidence),
            "geocode_precision": self.geocode_precision,
            "dpv_confirmed": self.dpv_confirmed,
            "flags": self.flags,
        }


class AddressValidator(Protocol):
    name: str

    def validate(self, address: Address) -> ValidationResult:
        ...


def _detect_flags(line1: str, line2: str | None) -> list[str]:
    text = f"{line1} {line2 or ''}"
    flags: list[str] = []
    if PO_BOX_PATTERN.search(text):
        flags.append("po_box")
    if RURAL_ROUTE_PATTERN.search(text):
        flags.append("rural_route")
    if not re.search(r"\d", line1):
        flags.append("no_street_number")
    return flags


class MockStreetValidator:
    """Deterministic street-standardization validator (CASS-like stand-in)."""

    name = "mock_street"

    business_tokens = {
        "warehouse",
        "industrial",
        "hospital",
        "school",
        "suite",
        "ste",
        "llc",
        "inc",
        "corp",
        "blvd",
    }

    def validate(self, address: Address) -> ValidationResult:
        line1 = normalize_text(address.raw_line1)
        flags = _detect_flags(line1, address.raw_line2)
        token_text = f"{line1} {address.raw_line2 or ''}".lower()
        is_business = any(token in token_text for token in self.business_tokens)
        precision = "rooftop" if "no_street_number" not in flags else "street_range"
        dpv = precision == "rooftop" and not flags
        return ValidationResult(
            validator=self.name,
            normalized_line1=line1,
            normalized_line2=normalize_text(address.raw_line2) if address.raw_line2 else None,
            city=normalize_text(address.city),
            state=address.state.strip().upper(),
            postal_code=normalize_postal(address.postal_code),
            is_residential=not is_business,
            confidence=Decimal("0.95000") if dpv else Decimal("0.70000"),
            geocode_precision=precision,
            dpv_confirmed=dpv,
            flags=flags,
            metadata={"adapter": self.name},
        )


class MockClassifierValidator:
    """Independent residential/business classifier (FedEx-AV-like stand-in)."""

    name = "mock_classifier"

    non_residential_markers = {
        "blvd",
        "industrial",
        "warehouse",
        "hospital",
        "plaza",
        "office",
        "center",
        "dr",
        "drive",
        "pkwy",
    }
    residential_markers = {"apt", "unit", "main st", "lane", "ln", "ct", "court", "circle"}

    def validate(self, address: Address) -> ValidationResult:
        line1 = normalize_text(address.raw_line1)
        flags = _detect_flags(line1, address.raw_line2)
        text = f"{line1} {address.raw_line2 or ''}".lower()
        non_res = any(marker in text for marker in self.non_residential_markers)
        res = any(marker in text for marker in self.residential_markers)
        is_residential: bool | None
        if non_res and res:
            is_residential = None
            flags = [*flags, "mixed_use"]
        elif non_res:
            is_residential = False
        else:
            is_residential = True
        precision = "rooftop" if "no_street_number" not in flags else "street_range"
        dpv = precision == "rooftop" and "po_box" not in flags and "rural_route" not in flags
        return ValidationResult(
            validator=self.name,
            normalized_line1=line1,
            normalized_line2=normalize_text(address.raw_line2) if address.raw_line2 else None,
            city=normalize_text(address.city),
            state=address.state.strip().upper(),
            postal_code=normalize_postal(address.postal_code),
            is_residential=is_residential,
            confidence=Decimal("0.90000") if dpv else Decimal("0.60000"),
            geocode_precision=precision,
            dpv_confirmed=dpv,
            flags=flags,
            metadata={"adapter": self.name},
        )


class ExternalAddressValidator:
    """Provider interface for FedEx AV / USPS / Google CASS / Smarty / ShipEngine.

    Fails closed until credentials and provider terms are configured. Live
    adapters subclass this and return the same ValidationResult shape.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def validate(self, address: Address) -> ValidationResult:
        raise RuntimeError(f"{self.name} adapter is not configured")


class AddressNormalizationService:
    """Runs every configured validator and stores a consensus verdict.

    Policy (fail closed):
    - validators disagreeing on the standardized street line -> CONFLICT
    - any PO box / rural route / missing street number / mixed-use flag -> not
      DPV-confirmed, so downstream residential or correction checks go to review
    - DPV-confirmed STANDARDIZED requires every validator to agree and confirm
    """

    def __init__(self, db: Session, validators: list[AddressValidator] | None = None) -> None:
        self.db = db
        self.validators = validators or [MockStreetValidator(), MockClassifierValidator()]

    def normalize_all_for_tenant(self, tenant_id: str) -> int:
        addresses = list(
            self.db.scalars(
                select(Address).where(
                    Address.tenant_id == tenant_id,
                    Address.normalized_hash.is_(None),
                )
            )
        )
        for address in addresses:
            self.normalize(address)
        self.db.commit()
        return len(addresses)

    def normalize(self, address: Address) -> Address:
        results = [validator.validate(address) for validator in self.validators]
        primary = results[0]

        address.normalized_line1 = primary.normalized_line1
        address.normalized_line2 = primary.normalized_line2
        address.normalized_city = primary.city
        address.normalized_state = primary.state
        address.normalized_postal_code = primary.postal_code
        address.normalized_hash = normalized_hash(
            primary.normalized_line1,
            primary.normalized_line2,
            primary.city,
            primary.state,
            primary.postal_code,
            address.country,
        )

        line_agreement = len({result.normalized_line1 for result in results}) == 1
        zip_agreement = len({result.postal_code for result in results}) == 1
        all_dpv = all(result.dpv_confirmed for result in results)
        any_interpolated = any(result.geocode_precision != "rooftop" for result in results)

        if not line_agreement or not zip_agreement:
            status = StandardizationStatus.CONFLICT
        elif any_interpolated:
            status = StandardizationStatus.INTERPOLATED
        elif all_dpv:
            status = StandardizationStatus.STANDARDIZED
        else:
            status = StandardizationStatus.UNKNOWN

        residential_votes = {result.is_residential for result in results if result.is_residential is not None}
        consensus_residential: bool | None = None
        if len(residential_votes) == 1:
            consensus_residential = residential_votes.pop()

        address.standardization_status = status
        address.dpv_confirmed = all_dpv and status == StandardizationStatus.STANDARDIZED
        address.validator_results = [result.as_record() for result in results]
        address.is_residential = consensus_residential
        address.validator = "+".join(validator.name for validator in self.validators)
        address.validator_confidence = min(result.confidence for result in results)
        address.geocode_precision = (
            "rooftop" if not any_interpolated else "street_range"
        )
        address.latitude = primary.latitude
        address.longitude = primary.longitude
        address.metadata_json = {
            **address.metadata_json,
            "validation": {
                "status": status.value,
                "validators": [result.validator for result in results],
                "flags": sorted({flag for result in results for flag in result.flags}),
            },
        }
        self.db.add(address)
        return address


def normalize_postal(postal_code: str) -> str:
    digits = re.sub(r"[^0-9]", "", postal_code)
    if len(digits) > 5:
        return f"{digits[:5]}-{digits[5:9]}"
    return digits[:5]


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    parsed = value.strip()
    if usaddress is None:
        return re.sub(r"\s+", " ", parsed).strip().upper()
    try:
        tagged, _ = usaddress.tag(parsed)
        parts = [
            tagged.get("AddressNumber"),
            tagged.get("StreetNamePreDirectional"),
            tagged.get("StreetName"),
            tagged.get("StreetNamePostType"),
            tagged.get("OccupancyType"),
            tagged.get("OccupancyIdentifier"),
        ]
        parsed = " ".join(part for part in parts if part)
    except usaddress.RepeatedLabelError:
        pass
    return re.sub(r"\s+", " ", parsed).strip().upper()


def normalized_hash(
    line1: str,
    line2: str | None,
    city: str,
    state: str,
    postal_code: str,
    country: str,
) -> str:
    payload = "|".join(
        [line1.upper(), (line2 or "").upper(), city.upper(), state.upper(), postal_code, country.upper()]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
