"""Captures demo screenshots of every workspace section (API on :8000 and web app on :3000 must be running).

    python scripts/capture_demo.py [out_dir]

Uses the app's own "Guest Demo Mode" (no account, no credentials). Writes demo_*.png to docs/screenshots (and out_dir).
"""
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import os
OUT = Path(os.environ.get("CAPTURE_OUT") or Path(__file__).resolve().parents[1] / "docs" / "screenshots")
OUT.mkdir(parents=True, exist_ok=True)
EXTRA = Path(sys.argv[1]) if len(sys.argv) > 1 else None
HIDE = "nav:not(#workspace-nav), header { visibility: hidden !important; }"
if os.environ.get("CAPTURE_LIGHT"):
    HIDE += (" html, body { background:#fff !important; } .aurora-layer, .grain { display:none !important; }"
             " main .rest .glass-card { background:#f6f6fa !important; box-shadow:0 0 0 1px #dcdce6 !important; backdrop-filter:none !important; }"
             " main .rest [class*='bg-black/'], main .rest [class*='bg-void'], main .rest [class*='bg-[#0'] { background:#fff !important; box-shadow:0 0 0 1px #e3e3ec !important; }"
             " main .rest .text-white, main .rest h2, main .rest h3, main .rest h4, main .rest strong { color:#111827 !important; }"
             " main .rest [class*='text-slate-'], main .rest [class*='text-gray'] { color:#374151 !important; }"
             " main .rest [class*='text-cyan-'] { color:#0e7490 !important; } main .rest [class*='text-emerald-'] { color:#047857 !important; }"
             " main .rest [class*='text-rose-'] { color:#be123c !important; } main .rest [class*='text-amber-'] { color:#b45309 !important; }"
             " main .rest [class*='text-blue-'], main .rest [class*='text-indigo-'], main .rest [class*='text-purple-'], main .rest [class*='text-violet-'] { color:#4338ca !important; }"
             " main .rest thead { color:#6b7280 !important; } main .rest td, main .rest th { border-color:#e5e7eb !important; }"
             " main .rest [class*='bg-emerald-950'], main .rest [class*='bg-rose-950'], main .rest [class*='bg-amber-950'] { background:#f3f4f6 !important; }")


def shot(page, locator_text, name, max_height=1500):
    """Screenshots the card containing locator_text (cropped to max_height CSS px), with the sticky menu hidden."""
    el = page.get_by_text(locator_text, exact=False).first
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(700)
    tag = page.add_style_tag(content="#workspace-nav { visibility: hidden !important; }")
    card = el.locator("xpath=ancestor::div[contains(@class,'glass-card') or contains(@class,'rounded-2xl')][1]")
    target = card if card.count() else el
    box = target.bounding_box()
    path = OUT / f"{name}.png"
    if box and box["height"] > max_height:
        page.screenshot(path=str(path), full_page=True,
                        clip={"x": box["x"], "y": box["y"] + page.evaluate("window.scrollY"), "width": box["width"], "height": max_height})
    else:
        target.screenshot(path=str(path))
    tag.evaluate("t => t.remove()")
    print("saved", name)


def section(page, label, wait_text, pause=2500):
    page.locator("#workspace-nav button", has_text=label).first.click()
    page.wait_for_selector(f"text={wait_text}", timeout=90000)
    page.wait_for_timeout(pause)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": int(os.environ.get("CAPTURE_W", 1440)), "height": 1000}, device_scale_factor=float(os.environ.get("CAPTURE_SCALE", 1.5)))
    page.goto("http://localhost:3000/workspace", wait_until="networkidle", timeout=120000)
    page.get_by_role("button", name="Guest Demo Mode").first.click()
    page.wait_for_timeout(1500)
    page.add_style_tag(content=HIDE)
    page.locator("#workspace-nav").scroll_into_view_if_needed()
    page.wait_for_timeout(3000)
    page.locator("#workspace-nav").screenshot(path=str(OUT / "demo_navigation.png"))
    print("saved demo_navigation")

    shot(page, "What this system does", "demo_1_overview_intro")
    shot(page, "The agent loop", "demo_1_overview_agent_loop")
    shot(page, "Key results (honest reading)", "demo_1_overview_results")
    shot(page, "Final test after the LLM", "demo_1_overview_post_cutoff")

    section(page, "Data", "Phase 1 Quantitative Pipeline", 4000)
    shot(page, "Phase 1 Quantitative Pipeline", "demo_2_data_pipeline")

    section(page, "News & FinBERT", "News Archive Coverage", 6000)
    shot(page, "News Archive Coverage", "demo_3_news_coverage")

    section(page, "Agent Loop", "every step of a run", 5000)
    shot(page, "every step of a run", "demo_4_agent_loop_summary")
    page.get_by_text("What the Research agent receives").first.click()
    page.wait_for_timeout(1500)
    shot(page, "What the Research agent receives", "demo_4_research_briefing", max_height=1300)
    cards = page.locator("text=Critic checks")
    if cards.count():
        cards.first.click()
        page.wait_for_timeout(800)
    try:
        page.get_by_text("Critic checks", exact=False).first.wait_for(timeout=5000)
        shot(page, "Critic checks", "demo_4_hypothesis_card", max_height=1600)
    except Exception:
        print("skipped demo_4_hypothesis_card")

    section(page, "Backtest Results", "How a formula is backtested", 4000)
    shot(page, "How a formula is backtested", "demo_5_backtest_explained")
    shot(page, "Significance after multiple-testing correction", "demo_5_significance")
    page.wait_for_selector("text=Ablation Study", timeout=90000)
    page.wait_for_timeout(2500)
    shot(page, "Ablation Study", "demo_5_ablation_equity")
    page.wait_for_selector("text=Leave-one-feature-out", timeout=90000)
    page.wait_for_timeout(2000)
    shot(page, "Leave-one-feature-out", "demo_5_attribution_panel")

    section(page, "Alpha Factor Report", "Equal-weight composite of all accepted", 4000)
    shot(page, "Equal-weight composite of all accepted", "demo_6_factor_report_summary")
    shot(page, "What the portfolio does", "demo_6_factor_report_card", max_height=1700)

    section(page, "Paper & Downloads", "Paper & downloads", 2000)
    shot(page, "Paper & downloads", "demo_6_downloads")
    b.close()

if EXTRA:
    EXTRA.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("demo_*.png"):
        shutil.copy(f, EXTRA / f.name)
    print("copied to", EXTRA)
