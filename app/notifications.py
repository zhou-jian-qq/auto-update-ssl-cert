from datetime import UTC, datetime, timedelta

import httpx

from .config import settings
from .db import get_db, utc_now_iso


def _recent_notification(conn, bank_id: int, event_type: str, fingerprint: str, channel: str) -> bool:
    cutoff = datetime.now(UTC) - timedelta(hours=settings.notify_cooldown_hours)
    row = conn.execute(
        """
        SELECT sent_at FROM notifications
        WHERE bank_id = ? AND event_type = ? AND fingerprint = ? AND channel = ? AND status = 'sent'
        ORDER BY sent_at DESC LIMIT 1
        """,
        (bank_id, event_type, fingerprint or "", channel),
    ).fetchone()
    if not row:
        return False
    sent_at = datetime.fromisoformat(row["sent_at"])
    return sent_at >= cutoff


def build_alert_text(bank, event_type: str, message: str, fingerprint: str = "") -> str:
    detail_url = f"{settings.public_base_url}/banks/{bank['id']}"
    return (
        f"【行方证书提醒】\n"
        f"银行：{bank['name']}\n"
        f"接口：{bank['host']}:{bank['port']}\n"
        f"事件：{event_type}\n"
        f"说明：{message}\n"
        f"指纹：{fingerprint or '-'}\n"
        f"详情：{detail_url}"
    )


def _send_wechat(text: str) -> tuple[str, str]:
    if not settings.wechat_webhook_url:
        return "skipped", "企业微信 Webhook 未配置"
    resp = httpx.post(settings.wechat_webhook_url, json={"msgtype": "text", "text": {"content": text}}, timeout=8)
    resp.raise_for_status()
    return "sent", resp.text[:500]


def _send_dingtalk(text: str) -> tuple[str, str]:
    if not settings.dingtalk_webhook_url:
        return "skipped", "钉钉 Webhook 未配置"
    resp = httpx.post(settings.dingtalk_webhook_url, json={"msgtype": "text", "text": {"content": text}}, timeout=8)
    resp.raise_for_status()
    return "sent", resp.text[:500]


def notify(bank_id: int, event_type: str, message: str, fingerprint: str = "") -> None:
    with get_db() as conn:
        bank = conn.execute("SELECT * FROM banks WHERE id = ?", (bank_id,)).fetchone()
        if not bank:
            return
        text = build_alert_text(bank, event_type, message, fingerprint)
        channels = [("wechat", _send_wechat), ("dingtalk", _send_dingtalk)]
        for channel, sender in channels:
            if _recent_notification(conn, bank_id, event_type, fingerprint, channel):
                continue
            try:
                status, result = sender(text)
            except Exception as exc:
                status, result = "failed", str(exc)
            conn.execute(
                """
                INSERT INTO notifications(bank_id, event_type, fingerprint, channel, status, message, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (bank_id, event_type, fingerprint or "", channel, status, result, utc_now_iso()),
            )
