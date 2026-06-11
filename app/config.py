import os
from dataclasses import dataclass


@dataclass
class Config:
    TEMPMAIL_URL: str = "https://tempail.com/ua/"
    HEADLESS: bool = False
    PAGE_TIMEOUT: int = 30_000   # ms — full page load / navigation
    SHORT_TIMEOUT: int = 8_000   # ms — element presence waits
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 5000

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            HEADLESS=os.getenv("HEADLESS", "false").lower() not in {"false", "0", "no"},
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO").upper(),
            PORT=int(os.getenv("PORT", "5000")),
        )
