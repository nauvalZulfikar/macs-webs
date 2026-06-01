"""Visual check: project list shows all 8 real Mac Mini projects after re-seed."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS = Path(__file__).resolve().parent / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = os.environ.get("BASE", "http://100.81.47.91:8101")

EXPECTED = {"SIBEDAS","macs","macs-tools","browser-agent","projects-web","shaka-ai","research-pipeline","taf"}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle", timeout=15000)
        page.locator("[data-testid='login-username']").fill("shaka")
        page.locator("[data-testid='login-input']").fill("pisang")
        page.locator("[data-testid='login-btn']").click()
        page.wait_for_selector("[data-testid='project-list']", timeout=10000)
        items = page.locator("[data-testid^='project-item-']")
        n = items.count()
        names = set()
        for i in range(n):
            txt = items.nth(i).inner_text().split("\n")[0].strip()
            names.add(txt)
        print(f"items: {n}")
        print(f"names: {sorted(names)}")
        missing = EXPECTED - names
        extra   = names - EXPECTED
        if missing: print(f"MISSING: {missing}")
        if extra:   print(f"EXTRA  : {extra}")
        page.screenshot(path=str(ARTIFACTS / "projects-expanded.png"), full_page=True)
        browser.close()
        assert not missing, f"missing expected projects: {missing}"
        print("\n✅ All expected projects visible.")


if __name__ == "__main__":
    main()
