from app.notifications import build_alert_text


def test_build_alert_text_contains_actionable_context():
    bank = {"id": 7, "name": "青岛银行", "host": "corporbank.qdccb.com", "port": 443}

    text = build_alert_text(bank, "证书即将到期", "剩余 20 天", "ABC123")

    assert "青岛银行" in text
    assert "corporbank.qdccb.com:443" in text
    assert "证书即将到期" in text
    assert "ABC123" in text
    assert "/banks/7" in text
