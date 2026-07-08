import datetime
import os

from fastapi.templating import Jinja2Templates

from app.core.config import settings


KST = datetime.timezone(datetime.timedelta(hours=9))
UTC = datetime.timezone.utc


def format_kst_time(value: datetime.datetime | None) -> str:
    if value is None:
        return "--:--"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST).strftime("%H:%M")


def make_templates() -> Jinja2Templates:
    templates = Jinja2Templates(
        directory=os.path.join(settings.BASE_DIR, "app", "templates")
    )
    templates.env.filters["kst_time"] = format_kst_time
    return templates
