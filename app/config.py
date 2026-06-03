import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "行方证书管理后台")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123456")
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    check_interval_minutes: int = _int_env("CHECK_INTERVAL_MINUTES", 720)
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    wechat_webhook_url: str = os.getenv("WECHAT_WEBHOOK_URL", "")
    dingtalk_webhook_url: str = os.getenv("DINGTALK_WEBHOOK_URL", "")
    notify_cooldown_hours: int = _int_env("NOTIFY_COOLDOWN_HOURS", 24)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cert_admin.db"

    @property
    def cert_dir(self) -> Path:
        return self.data_dir / "certs"


settings = Settings()
