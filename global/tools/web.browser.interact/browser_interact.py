#!/usr/bin/env python3
"""
Atom: web.browser.interact
Interactive Element Action Tool

Performs actions on DOM elements (click, type, submit) and captures the resulting
page state including URL changes, alerts, redirects, and new DOM content.

Usage:
  python3 browser_interact.py --url <url> --selector <selector> --action <action> [--value <text>]

Input Schema:
  url (required): Target URL
  selector (required): CSS selector or ref_id
  selector_type (optional, default css): css, xpath, or ref
  action (required): click, type, or submit
  value (optional): Text to type (required for 'type' action)
  simulate (optional, default false): Actually click vs simulate click

Output Schema:
  {
    "page_id": "string",
    "url": "string",
    "action_performed": "string",
    "target_selector": "string",
    "success": boolean,
    "result": {
      "new_url": "string (if redirected)",
      "new_title": "string",
      "url_changed": boolean,
      "alert_triggered": boolean,
      "alert_message": "string",
      "new_page_summary": "string",
      "new_interactive_count": number,
      "errors": ["string"]
    }
  }
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/dev/null"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(json.dumps({
        "page_id": "error",
        "success": False,
        "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"
    }))
    sys.exit(1)


def generate_page_id():
    return "interact_{}".format(uuid.uuid4().hex[:12])


def resolve_selector(page, selector, selector_type):
    """Same resolution logic as drill — map ref_id to actual element."""
    if selector_type == "ref":
        try:
            index = int(selector.replace("@e", "")) - 1
        except ValueError:
            return None, f"Invalid ref_id: {selector}"
        
        elements = page.evaluate("""
            () => {
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
                    const isVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;
                    const score = isVisible ? distFromCenter : 99999;
                    return { el, score, index };
                });
                scored.sort((a, b) => a.score - b.score);
                if (scored.length <= """ + str(index) + """) {
                    return null;
                }
                const target = scored[""" + str(index) + """].el;
                return {
                    tag: target.tagName.toLowerCase(),
                    id: target.id || null,
                    name: target.name || null,
                    type: target.type || null,
                    text: (target.textContent || '').trim().substring(0, 100),
                    has_role: !!target.getAttribute('role'),
                    role: target.getAttribute('role') || null,
                    is_visible: target.offsetParent !== null
                };
            }
        """)
        if not elements:
            return None, f"ref_id {selector} not found"
        
        parts = [elements["tag"]]
        if elements.get("id"):
            parts[0] += "#" + elements["id"]
        elif elements.get("name") and elements.get("type"):
            parts[0] += '[name="{}"][type="{}"]'.format(
                elements["name"].replace('"', '\\"'),
                elements["type"].replace('"', '\\"')
            )
        elif elements.get("name"):
            parts[0] += '[name="{}"]'.format(elements["name"].replace('"', '\\"'))
        elif elements.get("text"):
            clean_text = elements["text"].replace('"', '\\"').replace("'", "\\'")
            parts[0] += ':has-text("{}")'.format(clean_text[:50])
        
        return ".".join(parts), None
    
    return selector, None


def get_page_summary(page, max_chars=500):
    """Generate a compact page summary."""
    try:
        info = page.evaluate("""
            () => {
                const title = document.title || 'Unknown';
                const structure = [];
                ['header', 'nav', 'main', 'aside', 'footer'].forEach(sel => {
                    if (document.querySelector(sel)) structure.push(sel);
                });
                const interactive = document.querySelectorAll(
                    'a, button, input, select, textarea, [onclick], [tabindex]'
                ).length;
                return { title, structure: structure.join(', '), interactive };
            }
        """)
        summary = "Page: {}. Structure: {}. Interactive: {}.".format(
            info.get("title", "Unknown")[:100],
            info.get("structure", "Unknown"),
            info.get("interactive", 0)
        )
        if len(summary) > max_chars:
            summary = summary[:max_chars-3] + "..."
        return summary
    except Exception:
        return "Page summary unavailable"


def interact(url, selector, action, selector_type="css", value="", simulate=False):
    """Main interact function."""
    page_id = generate_page_id()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="SecuraTron/1.0 (Browser Interactor)"
        )
        page = context.new_page()
        
        # Track alerts
        alert_message = None
        alert_triggered = False
        
        def handle_dialog(dialog):
            nonlocal alert_message, alert_triggered
            alert_triggered = True
            alert_message = dialog.message
            dialog.accept()
        
        page.on("dialog", handle_dialog)
        
        try:
            # Navigate to target
            initial_url = url
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            
            initial_title = page.title()
            
            # Resolve selector
            resolved_selector, ref_error = resolve_selector(page, selector, selector_type)
            
            if ref_error:
                browser.close()
                return {
                    "page_id": page_id,
                    "url": url,
                    "action_performed": action,
                    "target_selector": selector,
                    "success": False,
                    "result": {
                        "new_url": None,
                        "new_title": initial_title,
                        "url_changed": False,
                        "alert_triggered": False,
                        "errors": [ref_error]
                    }
                }
            
            # Find the element
            element = page.query_selector(resolved_selector)
            
            if not element:
                browser.close()
                return {
                    "page_id": page_id,
                    "url": url,
                    "action_performed": action,
                    "target_selector": selector,
                    "success": False,
                    "result": {
                        "new_url": None,
                        "new_title": initial_title,
                        "url_changed": False,
                        "alert_triggered": False,
                        "errors": [f"Selector '{resolved_selector}' not found on page"]
                    }
                }
            
            # Check visibility
            is_visible = element.is_visible()
            is_enabled = element.is_enabled()
            
            errors = []
            if not is_visible:
                errors.append("Element is not visible (hidden/overflow)")
            if not is_enabled:
                errors.append("Element is disabled")
            
            # Perform action
            success = True
            result_errors = []
            
            if action == "click":
                try:
                    if simulate:
                        element.click(force=True)
                    else:
                        element.click()
                except Exception as e:
                    success = False
                    result_errors.append(f"Click failed: {str(e)}")
                    
            elif action == "type":
                if not value:
                    return {
                        "page_id": page_id,
                        "url": url,
                        "action_performed": action,
                        "target_selector": selector,
                        "success": False,
                        "result": {
                            "new_url": None,
                            "new_title": initial_title,
                            "url_changed": False,
                            "alert_triggered": False,
                            "errors": ["No value provided for 'type' action"]
                        }
                    }
                try:
                    element.fill(value)
                except Exception as e:
                    success = False
                    result_errors.append(f"Type failed: {str(e)}")
                    
            elif action == "submit":
                try:
                    # Try to submit the form directly
                    form = element.evaluate_handle("el => el.closest('form')")
                    if form and not form.is_null():
                        form.evaluate("form => form.requestSubmit()")
                    else:
                        element.click()  # Fallback: click the element
                except Exception as e:
                    success = False
                    result_errors.append(f"Submit failed: {str(e)}")
            
            else:
                success = False
                result_errors.append(f"Unknown action: {action}. Use: click, type, submit")
            
            # Wait for any navigation or state changes
            page.wait_for_timeout(2000)
            
            # Capture post-action state
            current_url = page.url()
            current_title = page.title()
            new_summary = get_page_summary(page)
            
            # Get new interactive count
            try:
                new_interactive_count = page.evaluate("""
                    document.querySelectorAll('a, button, input, select, textarea, [onclick], [tabindex]').length
                """)
            except Exception:
                new_interactive_count = 0
            
            url_changed = (current_url != initial_url)
            
            browser.close()
            
            return {
                "page_id": page_id,
                "url": url,
                "action_performed": action,
                "target_selector": selector,
                "resolved_selector": resolved_selector,
                "success": success and (not errors or action == "type"),
                "element_state": {
                    "visible": is_visible,
                    "enabled": is_enabled
                },
                "result": {
                    "new_url": current_url if url_changed else None,
                    "url_changed": url_changed,
                    "new_title": current_title,
                    "new_page_summary": new_summary,
                    "new_interactive_count": new_interactive_count,
                    "alert_triggered": alert_triggered,
                    "alert_message": alert_message,
                    "errors": errors + result_errors if errors or result_errors else []
                },
                "ts": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            browser.close()
            return {
                "page_id": page_id,
                "url": url,
                "action_performed": action,
                "target_selector": selector,
                "success": False,
                "result": {
                    "new_url": None,
                    "new_title": None,
                    "url_changed": False,
                    "alert_triggered": False,
                    "errors": [str(e)]
                }
            }


def main():
    parser = argparse.ArgumentParser(description="Browser Element Interactor")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--selector", required=True, help="CSS selector, XPath, or ref_id")
    parser.add_argument("--selector-type", default="css", choices=["css", "xpath", "ref"],
                       help="Selector type (default: css)")
    parser.add_argument("--action", required=True, choices=["click", "type", "submit"],
                       help="Action to perform")
    parser.add_argument("--value", default="", help="Value to type (for 'type' action)")
    parser.add_argument("--simulate", action="store_true", default=False,
                       help="Force click even if hidden")
    
    args = parser.parse_args()
    
    output = interact(
        url=args.url,
        selector=args.selector,
        action=args.action,
        selector_type=args.selector_type,
        value=args.value,
        simulate=args.simulate
    )
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
