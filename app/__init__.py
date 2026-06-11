import logging
import sys

from flask import Flask

from .config import Config
from .routes import api
from .scraper import TempMailScraper


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)-32s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def create_app(cfg: Config | None = None) -> Flask:
    """
    Application factory.

    The TempMailScraper is created once here and attached to the Flask app
    object (`app.scraper`).  It owns a single Playwright / Chromium process
    for the lifetime of the Flask server process.
    """
    cfg = cfg or Config.from_env()
    _configure_logging(cfg.LOG_LEVEL)

    app = Flask(__name__)

    scraper = TempMailScraper(cfg=cfg)
    app.scraper = scraper  # type: ignore[attr-defined]

    app.register_blueprint(api)

    return app
