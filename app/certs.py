import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtensionOID


@dataclass(frozen=True)
class CertificateInfo:
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    sans: list[str]
    sha256_fingerprint: str
    pem: str

    @property
    def not_before_iso(self) -> str:
        return self.not_before.astimezone(UTC).replace(microsecond=0).isoformat()

    @property
    def not_after_iso(self) -> str:
        return self.not_after.astimezone(UTC).replace(microsecond=0).isoformat()


def _name_to_text(name: x509.Name) -> str:
    return ", ".join([f"{attr.oid._name}={attr.value}" for attr in name])


def load_certificate_from_pem(pem: str | bytes) -> CertificateInfo:
    raw = pem.encode("utf-8") if isinstance(pem, str) else pem
    cert = x509.load_pem_x509_certificate(raw)
    sans: list[str] = []
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        sans = []

    pem_text = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return CertificateInfo(
        subject=_name_to_text(cert.subject),
        issuer=_name_to_text(cert.issuer),
        serial_number=format(cert.serial_number, "X"),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        sans=sans,
        sha256_fingerprint=cert.fingerprint(hashes.SHA256()).hex().upper(),
        pem=pem_text,
    )


def fetch_server_certificate(host: str, port: int = 443, timeout: float = 8.0) -> CertificateInfo:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    cert = x509.load_der_x509_certificate(der)
    pem = cert.public_bytes(serialization.Encoding.PEM)
    return load_certificate_from_pem(pem)


def remaining_days(not_after_iso: str | datetime, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    if isinstance(not_after_iso, str):
        not_after = datetime.fromisoformat(not_after_iso.replace("Z", "+00:00"))
    else:
        not_after = not_after_iso
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    seconds = (not_after - now).total_seconds()
    return int(seconds // 86400)


def cert_status(days_left: int, threshold_days: int) -> str:
    if days_left < 0:
        return "expired"
    if days_left <= threshold_days:
        return "warning"
    return "healthy"


def pem_filename(bank_code: str, host: str, not_after_iso: str, fingerprint: str) -> str:
    date = datetime.fromisoformat(not_after_iso.replace("Z", "+00:00")).strftime("%Y%m%d")
    safe_host = "".join(ch if ch.isalnum() or ch in ".-" else "-" for ch in host)
    return f"{bank_code}_{safe_host}_{date}_{fingerprint[:12]}.crt"


def write_pem(path: Path, pem: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pem, encoding="ascii")
