"""Logging configuration shared by the API and Celery worker."""

import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import ROOT_DIR, settings


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_SAFE_SERVICE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _get_log_dir() -> Path:
    """Resolve LOG_DIR, allowing both container and project-relative paths."""
    log_dir = Path(settings.LOG_DIR)
    if not log_dir.is_absolute():
        log_dir = ROOT_DIR / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _get_log_level() -> int:
    level_name = settings.LOG_LEVEL.upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"LOG_LEVEL khong hop le: {settings.LOG_LEVEL}")
    return level


def configure_logging(service_name: str | None = None) -> Path:
    """Configure console logging plus a time-rotated file for one service.

    Each service gets its own file so the API and Celery worker do not compete
    for the same rotating file handler.
    """
    service = service_name or settings.LOG_SERVICE
    service = _SAFE_SERVICE_NAME.sub("_", service).strip("._") or "app"
    log_file = _get_log_dir() / f"{service}.log"
    level = _get_log_level()
    formatter = logging.Formatter(LOG_FORMAT)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    console_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_omnivoice_handler", None) == "console"
        ),
        None,
    )
    if console_handler is None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler._omnivoice_handler = "console"
        root_logger.addHandler(console_handler)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_omnivoice_log_file", None) == str(log_file)
        ),
        None,
    )
    if file_handler is None:
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when=settings.LOG_ROTATION_WHEN,
            interval=settings.LOG_ROTATION_INTERVAL,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
            utc=settings.LOG_UTC,
            delay=True,
        )
        file_handler._omnivoice_log_file = str(log_file)
        root_logger.addHandler(file_handler)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    return log_file
