#!/usr/bin/env python3
"""
Atom: web.browser.drill
Progressive Browser Drill-Down Tool

Extracts detailed content for a single element from a previously inspected page.
Uses the page_id from browser_inspect to maintain state via shared JSON file.

Usage:
  python3 browser_drill.py --page-id <page_id> --ref-id <ref_id> [--url <url>]

Input Schema:
  page_state (required): State ID from previous browser_inspect response
  ref_id (required): Element reference ID (e.g., "@e5")

Output Schema:
  {
    "page_id": "string",
    "ref_id": "string",
    "detail": "Full content/attributes of the specified element",
    "ts": "ISO 8601 timestamp"
  }
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/dev/null"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(json.dumps({"error": "Playwright not installed"}))
    sys.exit(1)

# Add tool dir to path for state_store import
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOL_DIR)

from state_store import load_page_state, lookup_selector


def get_element_detail(page, ref_id, page_id):
    """
    Extract detailed content for a specific element.
    Uses state_store to find the element on a fresh page load.
    """
    try:
        selector = lookup_selector(page, page_id, ref_id)
        if not selector:
            return {
                "html": "",
                "attributes": {},
                "style_summary": {},
                "parent_tag": None,
                "parent_text": None,
                "text_content": "",
                "tag": "",
                "id": None,
                "classes": None,
                "href": None,
                "action": None,
                "error": "Element not found on page (selector mismatch)"
            }

        el = page.query_selector(selector)
        if not el:
            return {
                "html": "",
                "attributes": {},
                "style_summary": {},
                "parent_tag": None,
                "parent_text": None,
                "text_content": "",
                "tag": "",
                "id": None,
                "classes": None,
                "href": None,
                "action": None,
                "error": "Element not found on page"
            }

        detail = page.evaluate("""
            (el) => {
                const html = el.outerHTML.substring(0, 500);
                const attrs = {};
                for (let attr of el.attributes) {
                    attrs[attr.name] = attr.value.substring(0, 200);
                }
                const computed = window.getComputedStyle(el);
                const styleSummary = {
                    display: computed.display,
                    visibility: computed.visibility,
                    opacity: computed.opacity,
                    width: computed.width,
                    height: computed.height
                };
                const parent = el.parentElement;
                const parentTag = parent ? parent.tagName.toLowerCase() : null;
                const parentText = parent ? (parent.textContent || '').trim().substring(0, 200) : null;
                return {
                    html,
                    attributes: attrs,
                    style_summary: styleSummary,
                    parent_tag: parentTag,
                    parent_text: parentText,
                    text_content: (el.textContent || '').trim().replace(/\\s+/g, ' '),
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    classes: el.className || null,
                    href: el.getAttribute('href') || null,
                    action: el.getAttribute('onclick') || el.getAttribute('onsubmit') || null
                };
            }
        """, el)

        return detail
    except Exception as e:
        return {"error": str(e)}


def drill_element(page_id, ref_id, url=None):
    """Main drill function."""
    if url is None:
        return {
            "page_id": page_id,
            "ref_id": ref_id,
            "detail": {"error": "URL is required for drill."},
            "ts": datetime.now(timezone.utc).isoformat()
        }

    if not ref_id.startswith("@e"):
        return {
            "page_id": page_id,
            "ref_id": ref_id,
            "detail": {"error": "Invalid ref_id format. Expected @e<index>."},
            "ts": datetime.now(timezone.utc).isoformat()
        }

    # Check if we have saved state for this page
    state = load_page_state(page_id)
    has_state = state is not None

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="SecuraTron/1.0 (Drill)"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)

            detail = get_element_detail(page, ref_id, page_id)

            output = {
                "page_id": page_id,
                "ref_id": ref_id,
                "detail": detail,
                "ts": datetime.now(timezone.utc).isoformat(),
                "state_used": has_state
            }
            return output, browser, context, page

        except Exception as e:
            return {
                "page_id": page_id,
                "ref_id": ref_id,
                "detail": {"error": str(e)},
                "ts": datetime.now(timezone.utc).isoformat(),
                "state_used": has_state
            }, browser, context, page


def main():
    parser = argparse.ArgumentParser(description="Progressive Browser Drill-Down")
    parser.add_argument("--page-id", required=True, help="Page state ID from browser_inspect")
    parser.add_argument("--ref-id", required=True, help="Element ref ID (e.g., @e5)")
    parser.add_argument("--url", required=True, help="Target URL")

    args = parser.parse_args()

    output, browser, context, page = drill_element(
        page_id=args.page_id,
        ref_id=args.ref_id,
        url=args.url
    )

    try:
        browser.close()
    except Exception:
        pass

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
