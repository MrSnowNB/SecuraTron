#!/usr/bin/env python3
"""
Atom: web.browser.interact
Progressive Browser Interaction Tool

Performs actions on a previously inspected page (click, type, hover, scroll, screenshot).
Uses the page_id from browser_inspect to maintain state.

Usage:
  python3 browser_interact.py --page-id <page_id> --action <action> --ref-id <ref_id> [options]

Input Schema:
  page_state (required): State ID from previous response
  action (required): Action to perform (click, type, hover, scroll, screenshot)
  ref_id (required): Element reference ID
  text (optional): Text to type (only for "type" action)
  direction (optional): Scroll direction up/down (only for "scroll" action)

Output Schema:
  {
    "page_id": "string",
    "action": "string",
    "status": "success|failure|error",
    "message": "string",
    "new_interactive_count": integer,
    "ts": "ISO 8601 timestamp"
  }
"""

import argparse
import json
import os
import sys
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


def get_interactive_count(page):
    """Count interactive elements on current page."""
    try:
        count = page.evaluate("""
            () => {
                const selectors = [
                    'a', 'button', 'input', 'select', 'textarea',
                    '[onclick]', '[tabindex]', '[role="button"]',
                    '[role="link"]', '[role="input"]', 'details', 'summary'
                ];
                return document.querySelectorAll(selectors.join(', ')).length;
            }
        """)
        return count
    except Exception:
        return 0


def get_element_selector(page, ref_index):
    """Get the Playwright selector for an element by index."""
    try:
        selector = page.evaluate("""
            (index) => {
                const selectors = [
                    'a', 'button', 'input', 'select', 'textarea',
                    '[onclick]', '[tabindex]', '[role="button"]',
                    '[role="link"]', '[role="input"]', 'details', 'summary'
                ];
                const allElements = document.querySelectorAll(selectors.join(', '));
                const el = allElements[index];
                
                if (!el) return null;
                
                let sel = el.tagName.toLowerCase();
                if (el.id) {
                    return '#' + el.id;
                }
                if (el.className) {
                    sel += '.' + el.className.trim().split(' ').join('.');
                }
                if (el.type) {
                    sel += '[type="' + el.type + '"]';
                }
                if (el.name) {
                    sel += '[name="' + el.name + '"]';
                }
                
                const allMatches = document.querySelectorAll(sel);
                if (allMatches.length > 1) {
                    sel += ':nth-of-type(' + (Array.from(allMatches).indexOf(el) + 1) + ')';
                }
                
                return sel;
            }
        """, ref_index)
        return selector
    except Exception:
        return None


def click_element(page, ref_index):
    """Click an element."""
    try:
        selector = get_element_selector(page, ref_index)
        if not selector:
            return {"status": "failure", "message": "Could not find element selector"}
        
        elem = page.query_selector(selector)
        if not elem:
            return {"status": "failure", "message": "Element not found on page"}
        
        elem.click()
        page.wait_for_timeout(500)
        
        return {
            "status": "success",
            "message": "Clicked element",
            "new_interactive_count": get_interactive_count(page)
        }
    except Exception as e:
        return {"status": "error", "message": "Click failed: {}".format(str(e))}


def type_text(page, ref_index, text):
    """Type text into an element."""
    try:
        selector = get_element_selector(page, ref_index)
        if not selector:
            return {"status": "failure", "message": "Could not find element selector"}
        
        elem = page.query_selector(selector)
        if not elem:
            return {"status": "failure", "message": "Element not found on page"}
        
        elem.focus()
        elem.fill(text)
        
        return {
            "status": "success",
            "message": "Typed {} characters".format(len(text)),
            "new_interactive_count": get_interactive_count(page)
        }
    except Exception as e:
        return {"status": "error", "message": "Type failed: {}".format(str(e))}


def hover_element(page, ref_index):
    """Hover over an element."""
    try:
        selector = get_element_selector(page, ref_index)
        if not selector:
            return {"status": "failure", "message": "Could not find element selector"}
        
        elem = page.query_selector(selector)
        if not elem:
            return {"status": "failure", "message": "Element not found on page"}
        
        elem.hover()
        page.wait_for_timeout(200)
        
        return {
            "status": "success",
            "message": "Hovered element",
            "new_interactive_count": get_interactive_count(page)
        }
    except Exception as e:
        return {"status": "error", "message": "Hover failed: {}".format(str(e))}


def scroll_page(page, direction):
    """Scroll the page."""
    try:
        if direction == "up":
            page.mouse.wheel(0, -300)
        else:
            page.mouse.wheel(0, 300)
        
        page.wait_for_timeout(200)
        
        return {
            "status": "success",
            "message": "Scrolled {}".format(direction),
            "new_interactive_count": get_interactive_count(page)
        }
    except Exception as e:
        return {"status": "error", "message": "Scroll failed: {}".format(str(e))}


def screenshot_page(page, output_dir="/tmp"):
    """Take a screenshot."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(output_dir, "screenshot_{}.png".format(timestamp))
        page.screenshot(path=screenshot_path)
        
        return {
            "status": "success",
            "message": "Screenshot saved to {}".format(screenshot_path),
            "screenshot_path": screenshot_path
        }
    except Exception as e:
        return {"status": "error", "message": "Screenshot failed: {}".format(str(e))}


def interact(page_id, action, ref_id, url=None, text=None, direction=None):
    """Main interaction function."""
    if url is None:
        return {
            "page_id": page_id,
            "action": action,
            "status": "error",
            "message": "Error: URL is required for interaction.",
            "ts": datetime.now(timezone.utc).isoformat()
        }
    
    if ref_id.startswith("@e"):
        try:
            ref_index = int(ref_id[2:]) - 1
        except ValueError:
            ref_index = -1
    else:
        ref_index = -1
    
    if ref_index < 0:
        return {
            "page_id": page_id,
            "action": action,
            "status": "error",
            "message": "Error: Invalid ref_id format. Expected @e<index>.",
            "ts": datetime.now(timezone.utc).isoformat()
        }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="SecuraTron/1.0 (Interact)"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            
            if action == "click":
                result = click_element(page, ref_index)
            elif action == "type":
                if not text:
                    return {
                        "page_id": page_id,
                        "action": action,
                        "status": "error",
                        "message": "Error: --text is required for 'type' action.",
                        "ts": datetime.now(timezone.utc).isoformat()
                    }
                result = type_text(page, ref_index, text)
            elif action == "hover":
                result = hover_element(page, ref_index)
            elif action == "scroll":
                if not direction:
                    direction = "down"
                result = scroll_page(page, direction)
            elif action == "screenshot":
                result = screenshot_page(page)
            else:
                result = {
                    "status": "error",
                    "message": "Error: Unknown action '{}'. Valid: click, type, hover, scroll, screenshot".format(action)
                }
            
            output = {
                "page_id": page_id,
                "action": action,
                "ref_id": ref_id,
                "status": result.get("status", "error"),
                "message": result.get("message", ""),
                "ts": datetime.now(timezone.utc).isoformat()
            }
            
            if "new_interactive_count" in result:
                output["new_interactive_count"] = result["new_interactive_count"]
            if "screenshot_path" in result:
                output["screenshot_path"] = result["screenshot_path"]
            
            return output, browser, context, page
            
        except Exception as e:
            return {
                "page_id": page_id,
                "action": action,
                "ref_id": ref_id,
                "status": "error",
                "message": "Interaction failed: {}".format(str(e)),
                "ts": datetime.now(timezone.utc).isoformat()
            }, browser, context, page


def main():
    parser = argparse.ArgumentParser(description="Progressive Browser Interactor")
    parser.add_argument("--page-id", required=True, help="Page state ID")
    parser.add_argument("--action", required=True, choices=["click", "type", "hover", "scroll", "screenshot"], help="Action to perform")
    parser.add_argument("--ref-id", required=True, help="Element ref ID (e.g., @e5)")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--text", help="Text to type (for 'type' action)")
    parser.add_argument("--direction", choices=["up", "down"], help="Scroll direction (for 'scroll' action)")
    
    args = parser.parse_args()
    
    output, browser, context, page = interact(
        page_id=args.page_id,
        action=args.action,
        ref_id=args.ref_id,
        url=args.url,
        text=args.text,
        direction=args.direction
    )
    
    try:
        browser.close()
    except Exception:
        pass
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
