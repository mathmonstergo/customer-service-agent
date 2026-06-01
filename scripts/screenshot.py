"""无头浏览器截图脚本，用于 UI 验证。

用法：
  python scripts/screenshot.py <url> <output.png> [--viewport 1280x900] [--wait selector] [--full]
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("output")
    ap.add_argument("--viewport", default="1440x900")
    ap.add_argument("--wait", default=None, help="CSS selector to wait for")
    ap.add_argument("--full", action="store_true", help="full page screenshot")
    ap.add_argument("--click", default=None, help="CSS selector to click before screenshot")
    args = ap.parse_args()

    w, h = (int(x) for x in args.viewport.lower().split("x"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": w, "height": h})
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle", timeout=20000)
        if args.wait:
            page.wait_for_selector(args.wait, timeout=10000)
        if args.click:
            page.click(args.click)
            page.wait_for_load_state("networkidle", timeout=10000)
        page.screenshot(path=args.output, full_page=args.full)
        browser.close()
    print(f"saved {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
