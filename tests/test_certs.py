from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.certs import cert_status, load_certificate_from_pem, pem_filename, remaining_days


def make_cert(days: int = 90) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Bank"),
            x509.NameAttribute(NameOID.COMMON_NAME, "bank.example.com"),
        ]
    )
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("bank.example.com")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def test_load_certificate_from_pem_parses_core_fields():
    info = load_certificate_from_pem(make_cert())

    assert "commonName=bank.example.com" in info.subject
    assert "organizationName=Test Bank" in info.issuer
    assert info.sha256_fingerprint
    assert info.sans == ["bank.example.com"]
    assert info.pem.startswith("-----BEGIN CERTIFICATE-----")


def test_remaining_days_and_status():
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert remaining_days(now + timedelta(days=45), now=now) == 45
    assert cert_status(45, 30) == "healthy"
    assert cert_status(30, 30) == "warning"
    assert cert_status(-1, 30) == "expired"


def test_pem_filename_is_stable_and_safe():
    filename = pem_filename("qdccb", "corp/bank.example.com", "2026-07-17T07:59:59+00:00", "ABCDEF1234567890")

    assert filename == "qdccb_corp-bank.example.com_20260717_ABCDEF123456.crt"
