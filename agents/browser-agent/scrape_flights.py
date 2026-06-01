"""
Scrape multiple flight booking sites for MID-B itinerary:
  CGK ↔ MXP, depart 2026-06-03, return 2026-08-26, 1 adult economy,
  Korean Air + Air France combo via ICN + CDG.
Read-only: no clicks on Book/Buy/Select.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path("/Users/shaka-mac-mini/coding-projects/macs/agents/browser-agent/runs/mid-b-scrape")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SITES = {
    "skyscanner": "https://www.skyscanner.com/transport/flights/cgk/mxp/260603/260826/?adults=1&cabinclass=economy&rtn=1",
    "kayak": "https://www.kayak.com/flights/CGK-MXP/2026-06-03/2026-08-26?sort=price_a",
    "google_flights": "https://www.google.com/travel/flights?q=Flights%20from%20CGK%20to%20MXP%20on%202026-06-03%20returning%202026-08-26%201%20adult%20economy&hl=en&curr=IDR",
    "kiwi": "https://www.kiwi.com/en/search/results/jakarta-indonesia/milan-italy/2026-06-03/2026-08-26?adults=1&sortBy=PRICE",
    "momondo": "https://www.momondo.com/flight-search/CGK-MXP/2026-06-03/2026-08-26/economy?sort=price_a",
    "expedia": "https://www.expedia.com/Flights-Search?leg1=from:CGK,to:MXP,departure:06/03/2026TANYT&leg2=from:MXP,to:CGK,departure:08/26/2026TANYT&passengers=adults:1&trip=roundtrip&mode=search",
}

async def dismiss_popups(page):
    """Best-effort dismiss cookie/region/login popups."""
    selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Accept All")',
        'button:has-text("Agree")',
        'button:has-text("I accept")',
        'button:has-text("OK")',
        'button:has-text("Got it")',
        'button:has-text("Setuju")',
        'button[aria-label="Accept all"]',
        'button[aria-label="close" i]',
        'button[aria-label="dismiss" i]',
        '[data-testid="cookie-banner-accept"]',
        '#onetrust-accept-btn-handler',
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await page.wait_for_timeout(500)
        except Exception:
            pass

async def scrape_site(browser, name: str, url: str):
    print(f"\n=== {name} ===\nURL: {url}")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="Asia/Jakarta",
        viewport={"width": 1440, "height": 900},
    )
    page = await ctx.new_page()
    result = {"site": name, "url": url, "final_url": None, "title": None, "price_candidates": [], "snippet": None, "error": None}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
        await dismiss_popups(page)
        await page.wait_for_timeout(8000)
        await dismiss_popups(page)
        result["final_url"] = page.url
        result["title"] = await page.title()
        text = await page.evaluate("() => document.body.innerText")
        prices = re.findall(r"(?:Rp|IDR|USD|US\$|€|EUR|\$)\s?[\d.,]{3,12}", text)
        result["price_candidates"] = list(dict.fromkeys(prices))[:30]
        result["snippet"] = text[:3000]
        png = OUT_DIR / f"{name}.png"
        await page.screenshot(path=str(png), full_page=False)
        result["screenshot"] = str(png)
        print(f"  final_url: {page.url}")
        print(f"  title: {result['title']}")
        print(f"  prices: {result['price_candidates'][:10]}")
    except Exception as e:
        result["error"] = str(e)
        print(f"  ERROR: {e}")
    finally:
        await ctx.close()
    return result

async def main():
    site_filter = sys.argv[1:] if len(sys.argv) > 1 else list(SITES.keys())
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        for name in site_filter:
            if name not in SITES:
                print(f"unknown site: {name}", file=sys.stderr); continue
            r = await scrape_site(browser, name, SITES[name])
            results.append(r)
            (OUT_DIR / f"{name}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
        await browser.close()
    (OUT_DIR / "all.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(results)} results to {OUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
