from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .services import check_all_enabled


scheduler = BackgroundScheduler(timezone="UTC")


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        check_all_enabled,
        "interval",
        minutes=settings.check_interval_minutes,
        id="check_all_enabled",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
