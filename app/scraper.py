"""
TempMailScraper
───────────────
Architecture fix: TempMailScraper IS a dedicated daemon Thread.

Root cause of the original error
─────────────────────────────────
Playwright sync API uses greenlets internally.  The greenlet fiber is
bound to the OS thread where sync_playwright().start() was called.
Flask's threaded server handles each HTTP request in a NEW thread —
that thread is not the fiber owner → "Cannot switch to a different thread".

Fix
───
All Playwright calls live exclusively inside one dedicated thread (self).
Flask request handlers call the public API (get_email, get_inbox, …),
which enqueue a callable and block until the Playwright thread executes
it and sends back the result.  Zero Playwright calls ever happen outside
this thread.
"""

import logging
import queue
import threading
from typing import Any, Callable, TypeVar

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PWError,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from .config import Config
from .exceptions import (
    ElementNotFoundError,
    EmailNotFoundError,
    RefreshError,
    SessionError,
    TempMailError,
)

log = logging.getLogger(__name__)
T = TypeVar("T")
_STOP = object()  # sentinel — signals the worker loop to exit

# ── Selector registry ─────────────────────────────────────────────────────────
#   Edit here when tempail.com changes its markup.  No logic changes needed.
# ─────────────────────────────────────────────────────────────────────────────
SELECTORS: dict[str, list] = {
    # (css_selector, "value"|"text")
    # ── verified against live tempail.com/ua/ HTML ─────────────────────────
    "email": [
        ("#eposta_adres", "value"),  # ✓ confirmed from live HTML
        ("input.adres-input", "value"),  # fallback by class
        ("#e_mail", "value"),
        ("#email", "value"),
        ("input.e_mail", "value"),
        ("input[id*='mail']", "value"),
        ("input[readonly]", "value"),
        (".email-address", "text"),
    ],
    "inbox_rows": [
        "li.mail",  # ✓ confirmed: <li class="mail" id="mail_XXXXX">
        "ul.mailler li:not(.baslik)",  # defensive alternative
        ".mail_row",
        "#mails .mail_item",
        "#mail_list tr:not(:first-child)",
        ".message-row",
    ],
    "row_sender": [".gonderen", ".mail_from", ".from", "td:nth-child(1)"],
    "row_subject": [".baslik", ".mail_subj", ".subject", "td:nth-child(2)"],
    "row_time": [".zaman", ".mail_time", ".time", "td:nth-child(3)"],
    # msg_* selectors target the mail detail page (/ua/mail_XXXXX/)
    "msg_body": [".mail-icerik", ".mail_body", "#mail_body", ".email-body", ".body", ".icerik"],
    "msg_sender": [".gonderen", ".mail_from_addr", ".from-address", ".sender"],
    "msg_subject": [".baslik", ".mail_subject", ".subject-line", ".subj"],
    "msg_time": [".zaman", ".mail_date", ".date", ".time"],
    "refresh_btn": [
        ".yenile-link",  # ✓ confirmed: <a class="yenile-link">
        "#refresh",
        ".change_email",
        "a.change_email",
        "[data-action='change']",
        "[data-action='refresh']",
        "button.new-email",
    ],
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class TempMailScraper(threading.Thread):
    """
    Playwright session running in a dedicated daemon thread.

    ┌─────────────────────┐        queue        ┌──────────────────────┐
    │  Flask request      │ ──── callable ────> │  Playwright thread   │
    │  thread (any)       │ <─── result ──────  │  (this class)        │
    └─────────────────────┘                     └──────────────────────┘

    Public methods:  thread-safe, called from Flask.
    Private methods: run exclusively inside the Playwright thread.
    """

    def __init__(self, cfg: Config | None = None) -> None:
        super().__init__(name="playwright", daemon=True)
        self._cfg = cfg or Config()
        self._q: queue.Queue = queue.Queue()

        # Playwright objects — touched only inside run()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

        # Shared state — written in Playwright thread, read anywhere (GIL-safe)
        self._email: str | None = None
        self._email_cache: dict[str, dict] = {}

        # Synchronous boot: block until Playwright is ready (or raises)
        self._ready = threading.Event()
        self._boot_error: Exception | None = None
        self.start()  # launches run()
        self._ready.wait(timeout=65)
        if self._boot_error:
            raise self._boot_error

    # ── Playwright thread ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Entry point of the Playwright thread.  Never call directly."""
        try:
            self._launch()
        except Exception as exc:
            self._boot_error = exc
            self._ready.set()
            return

        self._ready.set()
        log.info("Playwright thread ready — entering task loop.")

        while True:
            item = self._q.get()
            if item is _STOP:
                log.info("Playwright thread: shutdown signal received.")
                break
            func, done_event, box = item
            try:
                box["v"] = func()
            except Exception as exc:
                box["e"] = exc
            finally:
                done_event.set()

        self._teardown()

    def _launch(self) -> None:
        """Create browser + context + page and navigate.  Playwright thread only."""
        from pathlib import Path
        self._pw = sync_playwright().start()

        # Persistent context saves cookies, localStorage, and browser fingerprint to disk.
        # CAPTCHA only needs to be solved ONCE — subsequent runs reuse the trusted session.
        profile_dir = Path.home() / ".tempail-browser-profile"
        profile_dir.mkdir(exist_ok=True)
        log.info("Browser profile dir: %s", profile_dir)

        self._ctx = self._pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=self._cfg.HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
            user_agent=_UA,
            locale="uk-UA",
            extra_http_headers={"Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8"},
        )
        self._page = self._ctx.new_page()
        # Mask navigator.webdriver before any navigation — order is critical.
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['uk-UA', 'uk', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)
        self._goto()

    def _teardown(self) -> None:
        # With launch_persistent_context, _ctx IS the browser — no separate _browser to close.
        for attr, method in [("_ctx", "close"), ("_pw", "stop")]:
            obj = getattr(self, attr, None)
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self._page = self._ctx = self._browser = self._pw = None

    # ── Task dispatcher ───────────────────────────────────────────────────────

    def _dispatch(self, func: Callable[[], T]) -> T:
        """
        Submit func to the Playwright thread and block until it finishes.
        Safe to call from any Flask/other thread.
        """
        if not self.is_alive():
            raise SessionError("Playwright thread has stopped unexpectedly.")
        done = threading.Event()
        box: dict[str, Any] = {}
        self._q.put((func, done, box))
        timeout_s = self._cfg.PAGE_TIMEOUT / 1000 + 10
        if not done.wait(timeout=timeout_s):
            raise SessionError(
                f"Playwright thread did not respond within {timeout_s:.0f}s."
            )
        if "e" in box:
            raise box["e"]
        return box["v"]  # type: ignore[return-value]

    # ── Private helpers (Playwright thread only) ──────────────────────────────

    def _goto(self) -> None:
        log.info("Navigating to %s …", self._cfg.TEMPMAIL_URL)
        self._page.goto(
            self._cfg.TEMPMAIL_URL,
            wait_until="networkidle",  # was "domcontentloaded" — email is JS-rendered
            timeout=self._cfg.PAGE_TIMEOUT,
        )
        self._email = self._find_email()
        log.info("Active email: %s", self._email)

    def _find_email(self) -> str:
        for selector, attr in SELECTORS["email"]:
            try:
                el = self._page.wait_for_selector(
                    selector, timeout=self._cfg.SHORT_TIMEOUT
                )
                if el is None:
                    continue
                text = (
                    el.get_attribute("value") if attr == "value" else el.inner_text()
                )
                text = (text or "").strip()
                if "@" in text:
                    log.debug("Email via selector %r", selector)
                    return text
            except (PWTimeout, PWError):
                pass

        found: str | None = self._page.evaluate("""
                                                () => {
                                                    const pat = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/;
                                                    const tags = 'input,span,div,p,label,a,h1,h2,h3,h4,h5,b,strong';
                                                    for (const el of document.querySelectorAll(tags)) {
                                                        const raw = el.value || el.innerText || el.textContent || '';
                                                        const m = raw.trim().match(pat);
                                                        if (m) return m[0];
                                                    }
                                                    return null;
                                                }
                                                """)
        if found and "@" in found:
            log.info("Email found via JS fallback: %r — add this selector to SELECTORS['email']", found)
            return found

        raise ElementNotFoundError(
            "Email address not found on page. "
            "Update SELECTORS['email'] if the site markup changed. "
            "Tip: run `python debug_selectors.py` to inspect the live DOM."
        )

    def _first_text(self, parent, *selectors: str, default: str = "") -> str:
        """Return inner_text of the first matching selector, or default."""
        for sel in selectors:
            try:
                el = parent.query_selector(sel)
                if el:
                    return el.inner_text().strip()
            except PWError:
                pass
        return default

    def _get_rows(self) -> list:
        for sel in SELECTORS["inbox_rows"]:
            rows = self._page.query_selector_all(sel)
            if rows:
                return rows
        return []

    def _recover(self) -> None:
        """Try page reload; fall back to full browser restart.  Playwright thread."""
        log.warning("Recovery: reloading page …")
        try:
            self._page.reload(
                wait_until="networkidle", timeout=self._cfg.PAGE_TIMEOUT
            )
            self._email = self._find_email()
            log.info("Recovered. Email: %s", self._email)
        except Exception as exc:
            log.error("Reload failed (%s) — full browser restart.", exc)
            self._teardown()
            self._launch()  # safe: we are inside the Playwright thread

    def _scrape_inbox(self) -> list[dict]:
        # Click the site's built-in poll button so the DOM shows the latest emails.
        # .yenile-link triggers an AJAX call to /api/kontrol/ and updates #epostalar in-place.
        try:
            btn = self._page.query_selector("a.yenile-link")
            if btn:
                btn.click()
                self._page.wait_for_timeout(1500)  # let the AJAX response settle
        except Exception as exc:
            log.debug("Could not click yenile-link: %s", exc)

        try:
            self._page.wait_for_selector("li.mail", timeout=self._cfg.SHORT_TIMEOUT)
        except PWTimeout:
            log.debug("Inbox is empty.")
            return []

        messages: list[dict] = []
        for idx, row in enumerate(self._page.query_selector_all("li.mail")):
            try:
                msg_id = (
                        row.get_attribute("id")  # <li id="mail_3913043594"> ← confirmed
                        or row.get_attribute("data-id")
                        or str(idx)
                )
                messages.append({
                    "id": msg_id,
                    # _resolve_sender decodes Cloudflare's data-cfemail XOR obfuscation.
                    # Using _first_text here returns "[email protected]" — always wrong.
                    "sender": self._resolve_sender(row),
                    "subject": self._first_text(row, *SELECTORS["row_subject"]),
                    "timestamp": self._first_text(row, *SELECTORS["row_time"]),
                })
            except Exception as exc:
                log.warning("Row %d parse error: %s", idx, exc)
        log.info("Inbox: %d messages.", len(messages))
        return messages

    @staticmethod
    def _decode_cf_email(encoded: str) -> str:
        """Decode a Cloudflare email-obfuscated string from data-cfemail attribute."""
        try:
            r = int(encoded[:2], 16)
            return "".join(chr(int(encoded[n:n + 2], 16) ^ r) for n in range(2, len(encoded), 2))
        except Exception:
            return ""

    def _resolve_sender(self, parent) -> str:
        """
        Extract sender from parent element.
        Cloudflare obfuscates emails as <span class="__cf_email__" data-cfemail="...">.
        After networkidle the CF decode script should have run, but as a safety net
        we also decode from data-cfemail directly.
        """
        text = self._first_text(parent, *SELECTORS["msg_sender"])
        if "[email" in text or not text:
            try:
                el = parent.query_selector("[data-cfemail]")
                if el:
                    encoded = el.get_attribute("data-cfemail") or ""
                    decoded = self._decode_cf_email(encoded)
                    if decoded:
                        return decoded
            except Exception:
                pass
        return text

    def _open_email(self, email_id: str) -> dict:
        """
        Navigate to the mail detail page, scrape content, then return to inbox.
        Navigating by URL avoids the broken-state problem of clicking <a href>
        and losing the inbox page context.
        """
        inbox = self._scrape_inbox()
        metadata = next((m for m in inbox if m["id"] == email_id), None)

        if not metadata:
            metadata = {"id": email_id, "sender": "Unknown", "subject": "", "timestamp": ""}

        page = self._page
        mail_url = f"{self._cfg.TEMPMAIL_URL.rstrip('/')}/{email_id}/"
        log.info("Opening mail detail: %s", mail_url)

        try:
            page.goto(mail_url, wait_until="networkidle", timeout=self._cfg.PAGE_TIMEOUT)

            try:
                page.wait_for_selector("#iframe", timeout=self._cfg.SHORT_TIMEOUT)
                iframe = page.frame_locator("#iframe")

                body = iframe.locator("body").evaluate("""(body) => {
                    const clone = body.cloneNode(true);

                    const trash = clone.querySelectorAll('#google_translate_element, .skiptranslate, script, style, #goog-gt-tt');
                    trash.forEach(el => el.remove());

                    return (clone.innerText || clone.textContent || '').trim();
                }""")
            except Exception as e:
                log.error("Failed to extract body from iframe: %s", e)
                body = "Could not load email body."

            metadata["body"] = body.strip()
            return metadata
        finally:
            try:
                page.goto(
                    self._cfg.TEMPMAIL_URL,
                    wait_until="domcontentloaded",
                    timeout=self._cfg.PAGE_TIMEOUT,
                )
            except Exception as e:
                log.warning("Failed to restore inbox page after reading email: %s", e)

    def _do_refresh(self) -> str:
        self._email_cache.clear()
        log.info("Force-refreshing email by clearing cookies and local storage.")

        self._ctx.clear_cookies()
        try:
            self._page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
        except Exception:
            pass

        self._goto()
        return self._email  # type: ignore[return-value]

    # ── Public API (called from Flask threads) ────────────────────────────────

    def get_email(self) -> str:
        """Return the current temporary email address."""
        # Fast path: already known — no queue round-trip needed (GIL-safe read)
        if self._email:
            return self._email

        def _init():
            if not self._email:
                self._goto()
            return self._email

        return self._dispatch(_init)

    def get_inbox(self) -> list[dict]:
        """Return inbox items: [{id, sender, subject, timestamp}, …]"""
        try:
            return self._dispatch(self._scrape_inbox)
        except (TempMailError, PWTimeout, PWError) as exc:
            log.warning("Inbox error (%s) — recovering …", exc)
            try:
                self._dispatch(self._recover)
                return self._dispatch(self._scrape_inbox)
            except Exception as exc2:
                log.error("Recovery failed: %s", exc2)
                return []

    def get_email_by_id(self, email_id: str) -> dict:
        """Return full message content (sender, subject, timestamp, body)."""
        # GIL-safe dict read — skip queue if already cached
        if email_id in self._email_cache:
            return self._email_cache[email_id]
        try:
            result = self._dispatch(lambda: self._open_email(email_id))
        except EmailNotFoundError:
            raise
        except (PWTimeout, PWError) as exc:
            log.error("Open email failed (%s) — recovering …", exc)
            self._dispatch(self._recover)
            result = self._dispatch(lambda: self._open_email(email_id))
        self._email_cache[email_id] = result
        return result

    def refresh(self) -> str:
        """Generate a new temporary email address."""
        try:
            return self._dispatch(self._do_refresh)
        except TempMailError:
            raise
        except Exception as exc:
            raise RefreshError(f"Could not refresh email: {exc}") from exc

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Signal the Playwright thread to shut down and wait for it."""
        self._q.put(_STOP)
        self.join(timeout=10)
        log.info("Scraper closed.")

    def __del__(self) -> None:
        try:
            if self.is_alive():
                self.close()
        except Exception:
            pass
