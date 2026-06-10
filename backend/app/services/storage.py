import hashlib
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class StoredObject:
    storage_uri: str
    sha256: str
    size_bytes: int


class EvidenceStorage:
    def __init__(self) -> None:
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        self.bucket = settings.s3_bucket

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, content: bytes, content_type: str | None = None) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        self.ensure_bucket()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
            Metadata={"sha256": digest},
        )
        return StoredObject(
            storage_uri=f"s3://{self.bucket}/{key}",
            sha256=digest,
            size_bytes=len(content),
        )


class InMemoryEvidenceStorage:
    """Test/demo storage that still returns stable S3-like URIs."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, content: bytes, content_type: str | None = None) -> StoredObject:
        self.objects[key] = content
        digest = hashlib.sha256(content).hexdigest()
        return StoredObject(storage_uri=f"memory://{key}", sha256=digest, size_bytes=len(content))
