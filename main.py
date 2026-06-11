"""
main.py — application entry point.

Run directly:
    python main.py

Or with gunicorn (single worker keeps one browser process):
    gunicorn "main:app" --workers 1 --bind 0.0.0.0:5000
"""

import logging
import signal
import sys

from app import create_app
from app.config import Config

log = logging.getLogger(__name__)

cfg = Config.from_env()
app = create_app(cfg)


def _shutdown(signum=None, frame=None) -> None:
    """Gracefully stop Playwright before the process exits."""
    scraper = getattr(app, "scraper", None)
    if scraper:
        log.info("Shutdown signal received — closing scraper …")
        scraper.close()
    sys.exit(0)


# Handle both normal exit and Docker/systemd SIGTERM
import atexit
atexit.register(_shutdown)
signal.signal(signal.SIGTERM, _shutdown)


if __name__ == "__main__":
    # use_reloader=False: Flask's reloader forks the process,
    # which would spawn a second Playwright thread / Chromium instance.
    app.run(
        host=cfg.HOST,
        port=cfg.PORT,
        debug=False,
        use_reloader=False,
    )
