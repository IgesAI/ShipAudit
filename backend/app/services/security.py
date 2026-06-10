import base64
import json
from typing import Any

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, hash_password, verify_password
from app.models import AuditLog, CarrierCode, CarrierCredential, Tenant, User, UserRole


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def bootstrap_admin(self, tenant_name: str, email: str, password: str) -> tuple[Tenant, User, str]:
        slug = tenant_name.lower().replace(" ", "-")
        tenant = self.db.scalar(select(Tenant).where(Tenant.slug == slug))
        if not tenant:
            tenant = Tenant(name=tenant_name, slug=slug)
            self.db.add(tenant)
            self.db.flush()
        user = self.db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
            self.db.add(user)
            self.db.flush()
        token = create_access_token(user.id, scopes=[user.role.value])
        self.db.commit()
        return tenant, user, token

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not user or not verify_password(password, user.password_hash):
            return None
        return user

    def user_from_token(self, token: str) -> User | None:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        except JWTError:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return self.db.get(User, user_id)


class CredentialVault:
    """Small local envelope placeholder.

    Production should replace this with KMS/Vault. The encoded payload prevents casual
    log exposure in local development while keeping adapter plumbing testable.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def store(
        self, tenant_id: str, carrier: CarrierCode | str, name: str, payload: dict[str, str]
    ) -> CarrierCredential:
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        credential = CarrierCredential(
            tenant_id=tenant_id,
            carrier=CarrierCode(carrier),
            name=name,
            encrypted_payload=encoded,
        )
        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def reveal_for_adapter(self, credential: CarrierCredential) -> dict[str, str]:
        return json.loads(base64.urlsafe_b64decode(credential.encrypted_payload.encode("ascii")))


class AuditLogger:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None,
        tenant_id: str | None = None,
        actor_user_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        row = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            request_id=request_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
