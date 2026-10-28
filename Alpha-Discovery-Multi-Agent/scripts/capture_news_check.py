"""Screenshot of the News & FinBERT page for one stock and period (servers on :8000 and :3000 must be running).

    python scripts/capture_news_check.py OUT.png [TICKER] [PERIOD_LABEL]
"""
import sys

from playwright.sync_api import sync_playwright

out = sys.argv[1]
ticker = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
period = sys.argv[3] if len(sys.argv) > 3 else "FNSPID 2013–2023"

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1.5)
    page.goto("http://localhost:3000/", wait_until="networkidle", timeout=120000)
    page.get_by_role("button", name="Guest Demo Mode").first.click()
    page.wait_for_timeout(1500)
    page.add_style_tag(content="nav:not(#workspace-nav), header { visibility: hidden !important; }")
    page.locator("#workspace-nav button", has_text="News & FinBERT").first.click()
    page.wait_for_selector("text=Headlines & FinBERT sentiment", timeout=90000)
    page.select_option("#news-ticker", ticker)
    page.get_by_role("button", name=period).first.click()
    page.wait_for_timeout(6000)
    card = page.get_by_text("Headlines & FinBERT sentiment").first.locator("xpath=ancestor::div[contains(@class,'glass-card')][1]")
    card.scroll_into_view_if_needed()
    page.add_style_tag(content="#workspace-nav { visibility: hidden !important; }")
    box = card.bounding_box()
    page.screenshot(path=out, full_page=True, clip={"x": box["x"], "y": box["y"] + page.evaluate("window.scrollY"),
                                                    "width": box["width"], "height": min(box["height"], 1400)})
    rows = page.locator("table tbody tr").count()
    print("saved", out, "rows visible:", rows)
    b.close()
