"""Shared E2E test helpers."""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def get_password() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("PW_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("PW_TOKEN not in .env")


def login(page, base_url: str) -> None:
    """Navigate to base_url, login if needed, leave at project list."""
    page.goto(base_url, wait_until="networkidle", timeout=20000)
    # detect login screen
    if page.locator("[data-testid='login-form']").count():
        page.locator("[data-testid='login-input']").fill(get_password())
        page.locator("[data-testid='login-btn']").click()
        page.wait_for_selector("[data-testid='project-list']", timeout=10000)
