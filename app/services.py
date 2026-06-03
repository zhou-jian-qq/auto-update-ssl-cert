from __future__ import annotations

from datetime import UTC, datetime

from .certs import cert_status, fetch_server_certificate, load_certificate_from_pem, pem_filename, remaining_days, write_pem
from .config import settings
from .db import get_db, utc_now_iso
from .notifications import notify


def create_bank(data: dict) -> int:
    now = utc_now_iso()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO banks(name, code, host, port, threshold_days, website_url, notes, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"].strip(),
                data["code"].strip(),
                data["host"].strip(),
                int(data.get("port") or 443),
                int(data.get("threshold_days") or 30),
                data.get("website_url", "").strip(),
                data.get("notes", "").strip(),
                1 if data.get("enabled", True) else 0,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def update_bank(bank_id: int, data: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE banks
            SET name = ?, code = ?, host = ?, port = ?, threshold_days = ?, website_url = ?, notes = ?,
                enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"].strip(),
                data["code"].strip(),
                data["host"].strip(),
                int(data.get("port") or 443),
                int(data.get("threshold_days") or 30),
                data.get("website_url", "").strip(),
                data.get("notes", "").strip(),
                1 if data.get("enabled", False) else 0,
                utc_now_iso(),
                bank_id,
            ),
        )


def _store_certificate(conn, bank, info, source: str, status: str = "candidate") -> int:
    existing = conn.execute(
        "SELECT id FROM certificates WHERE bank_id = ? AND sha256_fingerprint = ?",
        (bank["id"], info.sha256_fingerprint),
    ).fetchone()
    if existing:
        return int(existing["id"])

    filename = pem_filename(bank["code"], bank["host"], info.not_after_iso, info.sha256_fingerprint)
    pem_path = settings.cert_dir / filename
    write_pem(pem_path, info.pem)
    cursor = conn.execute(
        """
        INSERT INTO certificates(
            bank_id, status, subject, issuer, serial_number, not_before, not_after, sans,
            sha256_fingerprint, pem_path, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bank["id"],
            status,
            info.subject,
            info.issuer,
            info.serial_number,
            info.not_before_iso,
            info.not_after_iso,
            "\n".join(info.sans),
            info.sha256_fingerprint,
            str(pem_path),
            source,
            utc_now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def check_bank(bank_id: int) -> dict:
    with get_db() as conn:
        bank = conn.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone()
        if not bank:
            raise ValueError("银行配置不存在")
        try:
            info = fetch_server_certificate(bank["host"], int(bank["port"]))
            cert_id = _store_certificate(conn, bank, info, source="tls")
            current = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
            days_left = remaining_days(current["not_after"])
            state = cert_status(days_left, int(bank["threshold_days"]))

            known_current = bank["current_cert_id"]
            message = f"检查成功，证书剩余 {days_left} 天"
            if not known_current:
                conn.execute("UPDATE banks SET current_cert_id = ?, updated_at = ? WHERE id = ?", (cert_id, utc_now_iso(), bank_id))
            elif known_current != cert_id:
                message = "发现新的远端证书，已保存为候选证书"
                notify(bank_id, "发现新证书", message, info.sha256_fingerprint)

            if state == "expired":
                notify(bank_id, "证书已过期", message, info.sha256_fingerprint)
            elif state == "warning":
                notify(bank_id, "证书即将到期", message, info.sha256_fingerprint)

            conn.execute(
                "INSERT INTO check_logs(bank_id, status, message, certificate_id, checked_at) VALUES (?, ?, ?, ?, ?)",
                (bank_id, state, message, cert_id, utc_now_iso()),
            )
            return {"status": state, "message": message, "certificate_id": cert_id, "days_left": days_left}
        except Exception as exc:
            message = f"检查失败：{exc}"
            conn.execute(
                "INSERT INTO check_logs(bank_id, status, message, checked_at) VALUES (?, ?, ?, ?)",
                (bank_id, "failed", message, utc_now_iso()),
            )
            notify(bank_id, "检查失败", message)
            return {"status": "failed", "message": message}


def check_all_enabled() -> None:
    with get_db() as conn:
        bank_ids = [row["id"] for row in conn.execute("SELECT id FROM banks WHERE enabled = 1").fetchall()]
    for bank_id in bank_ids:
        check_bank(bank_id)


def confirm_certificate(cert_id: int, username: str) -> None:
    now = utc_now_iso()
    with get_db() as conn:
        cert = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
        if not cert:
            raise ValueError("证书不存在")
        conn.execute("UPDATE certificates SET status = 'archived' WHERE bank_id = ? AND status = 'confirmed'", (cert["bank_id"],))
        conn.execute(
            "UPDATE certificates SET status = 'confirmed', confirmed_by = ?, confirmed_at = ? WHERE id = ?",
            (username, now, cert_id),
        )
        conn.execute("UPDATE banks SET current_cert_id = ?, updated_at = ? WHERE id = ?", (cert_id, now, cert["bank_id"]))


def import_uploaded_certificate(bank_id: int, pem_text: str) -> int:
    with get_db() as conn:
        bank = conn.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone()
        if not bank:
            raise ValueError("银行配置不存在")
        info = load_certificate_from_pem(pem_text)
        cert_id = _store_certificate(conn, bank, info, source="upload", status="candidate")
        conn.execute(
            "INSERT INTO check_logs(bank_id, status, message, certificate_id, checked_at) VALUES (?, ?, ?, ?, ?)",
            (bank_id, "uploaded", "人工上传候选证书", cert_id, utc_now_iso()),
        )
        return cert_id


def record_download(cert_id: int, username: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO downloads(certificate_id, username, downloaded_at) VALUES (?, ?, ?)",
            (cert_id, username, utc_now_iso()),
        )


def dashboard_stats() -> dict:
    with get_db() as conn:
        banks = conn.execute(
            """
            SELECT b.*, c.not_after, c.status AS cert_state, c.sha256_fingerprint
            FROM banks b
            LEFT JOIN certificates c ON c.id = b.current_cert_id
            ORDER BY b.updated_at DESC
            """
        ).fetchall()
        total_certs = conn.execute("SELECT COUNT(*) AS n FROM certificates").fetchone()["n"]
        candidates = conn.execute("SELECT COUNT(*) AS n FROM certificates WHERE status = 'candidate'").fetchone()["n"]

    rows = []
    warning = 0
    expired = 0
    for bank in banks:
        days_left = None
        state = "unknown"
        if bank["not_after"]:
            days_left = remaining_days(bank["not_after"])
            state = cert_status(days_left, bank["threshold_days"])
            warning += 1 if state == "warning" else 0
            expired += 1 if state == "expired" else 0
        rows.append(dict(bank) | {"days_left": days_left, "status": state})
    return {"banks": rows, "total_certs": total_certs, "warning": warning, "expired": expired, "candidates": candidates}
