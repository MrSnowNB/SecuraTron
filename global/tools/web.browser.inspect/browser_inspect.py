#!/usr/bin/env python3
"""
Atom: web.browser.inspect
Progressive Browser Inspection Tool

Returns a lightweight page summary (under 500 chars) instead of dumping
the entire accessibility tree. This avoids context bloat from full
accessibility tree dumps.

Usage:
  python3 browser_inspect.py --url <url> [--max-chars 500] [--include-interactive] [--include-images]

Input Schema:
  url (required): Target URL to inspect
  max_summary_chars (optional, default 500): Max characters for summary
  include_interactive (optional, default true): Include interactive elements
  include_images (optional, default false): Include image URLs

Output Schema:
  {
    "page_id": "string (unique state ID)",
    "url": "string",
    "title": "string",
    "structure": ["header", "nav", "main", ...],
    "interactive_count": 42,
    "summary": "Human-readable summary (under max_summary_chars)",
    "interactive_elements": [
      {"ref_id": "@e1", "tag": "a", "text": "Login", "type": "link", "position": "top-right"},
      ...
    ]
  }
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Configure Playwright to use system Chromium
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/dev/null"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(json.dumps({
        "error": "Playwright not installed",
        "solution": "pip install playwright && playwright install chromium"
    }))
    sys.exit(1)


def generate_page_id():
    """Generate a unique page state ID."""
    return "page_{}".format(uuid.uuid4().hex[:12])


def get_structure(page):
    """Extract high-level page structure (regions)."""
    structure = []
    try:
        tags = page.evaluate("""
            () => {
                const regions = [];
                const selectors = ['header', 'nav', 'main', 'aside', 'footer', 'section', 'article'];
                selectors.forEach(sel => {
                    const found = document.querySelectorAll(sel);
                    if (found.length > 0) regions.push(sel);
                });
                return regions;
            }
        """)
        return tags if tags else ["unknown"]
    except Exception:
        return ["unknown"]


def get_interactive_elements(page, include_images=False, max_elements=100):
    """Extract interactive elements, prioritizing viewport-visible ones, capped at max_elements."""
    try:
        elements = page.evaluate("""
            (maxElements) => {
                const selectors = [
                    'a', 'button', 'input', 'select', 'textarea',
                    '[onclick]', '[tabindex]', '[role="button"]',
                    '[role="link"]', '[role="input"]', 'details', 'summary'
                ];
                const allElements = document.querySelectorAll(selectors.join(', '));

                const viewportCenterY = window.innerHeight / 2;

                const scored = Array.from(allElements).map((el, index) => {
                    const rect = el.getBoundingClientRect();
                    const centerY = rect.top + rect.height / 2;
                    const distFromCenter = Math.abs(centerY - viewportCenterY);

                    let position = 'center';
                    if (rect.top < window.innerHeight / 3) position = 'top';
                    else if (rect.bottom > window.innerHeight * 2 / 3) position = 'bottom';

                    let type = el.tagName.toLowerCase();
                    if (el.getAttribute('role')) type = el.getAttribute('role');

                    let text = (el.textContent || '').trim().replace(/\\s+/g, ' ').substring(0, 40);

                    // Score: visible elements get higher score (lower number = better)
                    const isVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;
                    const score = isVisible ? distFromCenter : 99999;

                    return { ref_id: '@e' + (index + 1), tag: el.tagName.toLowerCase(), text, type, position, score };
                });

                // Sort: viewport-visible first (by proximity to center), then off-screen
                scored.sort((a, b) => a.score - b.score);

                // Slice to max_elements, then re-index ref_ids sequentially
                return scored.slice(0, maxElements).map((e, i) => ({
                    ref_id: '@e' + (i + 1),
                    tag: e.tag,
                    text: e.text,
                    type: e.type,
                    position: e.position
                }));
            }
        """, max_elements)
        return elements
    except Exception as e:
        return []


def generate_summary(title, structure, interactive_count, elements):
    """Generate a human-readable summary under max_summary_chars."""
    max_chars = 500
    
    summary_parts = [
        "Page: {}".format(title),
        "Structure: {}".format(", ".join(structure[:5])),
        "Interactive elements: {}".format(interactive_count)
    ]
    
    if elements:
        sample = elements[:3]
        summary_parts.append("Samples: " + ", ".join([
            "{} '{}'".format(e['type'], e['text'][:50]) for e in sample
        ]))
    
    summary = ". ".join(summary_parts) + "."
    
    if len(summary) > max_chars:
        summary = summary[:max_chars-3] + "..."
    
    return summary


def inspect_page(url, max_summary_chars=500, include_interactive=True, include_images=False, max_elements=100):
    """Main inspection function."""
    page_id = generate_page_id()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="SecuraTron/1.0 (Automated Inspector)"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            
            title = page.title() or "Unknown"
            structure = get_structure(page)
            elements = []
            interactive_count = 0
            
            if include_interactive:
                elements = get_interactive_elements(page, include_images, max_elements)
                interactive_count = len(elements)
            
            summary = generate_summary(title, structure, interactive_count, elements)
            
            output = {
                "page_id": page_id,
                "url": url,
                "title": title,
                "structure": structure,
                "interactive_count": interactive_count,
                "summary": summary,
                "interactive_elements": elements,
                "ts": datetime.now(timezone.utc).isoformat()
            }
            
            return output, browser, context, page
            
        except Exception as e:
            return {
                "page_id": page_id,
                "url": url,
                "title": "Error",
                "structure": [],
                "interactive_count": 0,
                "summary": "Failed to inspect page: {}".format(str(e)),
                "interactive_elements": [],
                "ts": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }, browser, context, page


def main():
    parser = argparse.ArgumentParser(description="Progressive Browser Inspector")
    parser.add_argument("--url", required=True, help="Target URL to inspect")
    parser.add_argument("--max-chars", type=int, default=500, help="Max summary chars")
    parser.add_argument("--include-interactive", action="store_true", default=True, help="Include interactive elements")
    parser.add_argument("--include-images", action="store_true", default=False, help="Include image URLs")
    parser.add_argument("--max-elements", type=int, default=100, help="Max interactive elements to return (default: 100)")
    
    args = parser.parse_args()
    
    output, browser, context, page = inspect_page(
        url=args.url,
        max_summary_chars=args.max_chars,
        include_interactive=args.include_interactive,
        include_images=args.include_images,
        max_elements=args.max_elements
    )
    
    try:
        browser.close()
    except Exception:
        pass
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
