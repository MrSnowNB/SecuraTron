#!/usr/bin/env python3
"""
Atom: web.browser.drill
Progressive Element Deep-Dive Tool

Takes an element selector and extracts comprehensive details:
- All HTML attributes and properties
- Computed styles (visibility, display, opacity, pointer-events)
- Event listeners (click, change, submit, keyup, etc.)
- Parent/sibling context (2 levels up)
- Form context (if element is inside a form)
- ARIA roles and states
- Accessibility tree position

Usage:
  python3 browser_drill.py --url <url> --selector <css-or-xpath> [--selector-type css|xpath|ref]

Input Schema:
  url (required): Target URL to inspect
  selector (required): CSS selector, XPath, or ref_id (e.g., '@e1')
  selector_type (optional, default css): css, xpath, or ref
  max_depth (optional, default 2): Parent context depth levels

Output Schema:
  {
    "page_id": "string",
    "url": "string",
    "selector": "string",
    "selector_type": "string",
    "found": boolean,
    "element": {
      "tag": "string",
      "text": "string",
      "attributes": {"id": "...", "class": "...", ...},
      "computed_style": {"display": "block", "visibility": "visible", ...},
      "events": [{"type": "click", "handler": "function() {...}", ...}],
      "parent_context": [...],
      "form_context": {"action": "...", "method": "...", "inputs": [...]},
      "aria": {"role": "...", "states": {...}}
    },
    "error": "string (if not found)"
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
        "found": False,
        "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"
    }))
    sys.exit(1)


def generate_page_id():
    return "drill_{}".format(uuid.uuid4().hex[:12])


def resolve_selector(page, selector, selector_type):
    """Resolve a ref_id to an actual DOM element, or use selector directly."""
    if selector_type == "ref":
        # ref_id like "@e1" — re-scan page to find matching element
        # Extract the index from @eN
        try:
            index = int(selector.replace("@e", "")) - 1
        except ValueError:
            return None, f"Invalid ref_id: {selector}"
        
        # Re-scan interactive elements to find the Nth one
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
                // Return the resolved element's tag, id, and a simple selector
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
            return None, f"ref_id {selector} not found (only {len(page.evaluate('document.querySelectorAll(\"a, button, input, select, textarea, [onclick], [tabindex], [role=\\\"button\\\"], [role=\\\"link\\\"], details, summary\")).length}) interactive elements on page)"
        
        # Build a selector from the resolved element
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


def extract_element_details(page, selector):
    """Extract comprehensive details about a DOM element."""
    try:
        details = page.evaluate("""
            (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                
                const result = {};
                
                // Basic info
                result.tag = el.tagName.toLowerCase();
                result.text = (el.textContent || '').trim().replace(/\\s+/g, ' ').substring(0, 500);
                
                // All HTML attributes
                const attrs = {};
                for (let attr of el.attributes) {
                    attrs[attr.name] = attr.value.substring(0, 200);
                }
                result.attributes = attrs;
                
                // Computed styles (key visibility/display properties)
                const style = window.getComputedStyle(el);
                result.computed_style = {
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    'pointer-events': style.pointerEvents,
                    position: style.position,
                    width: style.width,
                    height: style.height,
                    'text-align': style.textAlign
                };
                
                // Event listeners (try to capture them)
                result.events = [];
                const eventTypes = ['click', 'change', 'submit', 'keyup', 'keydown', 'focus', 'blur', 'input', 'mousedown', 'mouseup', 'dblclick'];
                eventTypes.forEach(type => {
                    try {
                        // We can't directly read event listeners in all browsers, 
                        // but we can check for inline handlers
                        const inlineHandler = el['on' + type];
                        if (inlineHandler && typeof inlineHandler === 'function') {
                            result.events.push({
                                type: type,
                                source: 'inline',
                                handler: inlineHandler.toString().substring(0, 200)
                            });
                        }
                    } catch (e) {}
                });
                
                // Check for data-* attributes that might indicate JS bindings
                Object.keys(attrs).forEach(key => {
                    if (key.startsWith('data-') && key.endsWith('-action')) {
                        result.events.push({
                            type: 'custom:' + attrs[key],
                            source: 'data-attribute',
                            handler: attrs[key]
                        });
                    }
                    if (key === 'onclick' || key === 'onsubmit' || key === 'onchange') {
                        result.events.push({
                            type: key.replace('on', ''),
                            source: 'html-attribute',
                            handler: attrs[key].substring(0, 200)
                        });
                    }
                });
                
                // Parent context (2 levels up)
                result.parent_context = [];
                let parent = el.parentElement;
                let depth = 0;
                while (parent && depth < 2) {
                    result.parent_context.push({
                        tag: parent.tagName.toLowerCase(),
                        id: parent.id || null,
                        classes: parent.className || null,
                        text: (parent.textContent || '').trim().substring(0, 100),
                        role: parent.getAttribute('role') || null
                    });
                    parent = parent.parentElement;
                    depth++;
                }
                
                // Form context
                let form = el.closest('form');
                if (form) {
                    result.form_context = {
                        action: form.action || '(empty)',
                        method: form.method || 'get',
                        enctype: form.enctype || 'application/x-www-form-urlencoded',
                        id: form.id || null,
                        inputs: []
                    };
                    // Capture all form inputs
                    const formInputs = form.querySelectorAll('input, select, textarea');
                    formInputs.forEach(inp => {
                        result.form_context.inputs.push({
                            tag: inp.tagName.toLowerCase(),
                            type: inp.type || null,
                            name: inp.name || null,
                            id: inp.id || null,
                            required: inp.required,
                            placeholder: (inp.getAttribute('placeholder') || '').substring(0, 50),
                            value: (inp.value || '').substring(0, 100),
                            disabled: inp.disabled,
                            readonly: inp.readOnly
                        });
                    });
                }
                
                // ARIA roles and states
                result.aria = {
                    role: el.getAttribute('role') || null,
                    states: {}
                };
                const ariaAttrs = ['aria-label', 'aria-labelledby', 'aria-describedby', 
                                   'aria-required', 'aria-checked', 'aria-expanded',
                                   'aria-disabled', 'aria-hidden', 'aria-live',
                                   'aria-invalid', 'aria-current', 'aria-selected'];
                ariaAttrs.forEach(attr => {
                    const val = el.getAttribute(attr);
                    if (val) result.aria.states[attr] = val;
                });
                
                // Accessibility tree position
                result.aria.level = el.getAttribute('aria-level') || null;
                result.aria.posinset = el.getAttribute('aria-posinset') || null;
                result.aria.setsize = el.getAttribute('aria-setsize') || null;
                
                return result;
            }
        """, selector)
        return details, None
    except Exception as e:
        return None, str(e)


def drill_element(url, selector, selector_type="css", max_depth=2):
    """Main drill function."""
    page_id = generate_page_id()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="SecuraTron/1.0 (Element Driller)"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            
            # Resolve selector
            resolved_selector, ref_error = resolve_selector(page, selector, selector_type)
            
            if ref_error:
                browser.close()
                return {
                    "page_id": page_id,
                    "url": url,
                    "selector": selector,
                    "selector_type": selector_type,
                    "found": False,
                    "error": ref_error
                }
            
            # Extract details
            details, extract_error = extract_element_details(page, resolved_selector)
            
            if extract_error:
                browser.close()
                return {
                    "page_id": page_id,
                    "url": url,
                    "selector": selector,
                    "selector_type": selector_type,
                    "found": False,
                    "error": extract_error
                }
            
            if not details:
                browser.close()
                return {
                    "page_id": page_id,
                    "url": url,
                    "selector": selector,
                    "selector_type": selector_type,
                    "found": False,
                    "error": f"Selector '{resolved_selector}' did not match any element"
                }
            
            output = {
                "page_id": page_id,
                "url": url,
                "selector": selector,
                "selector_type": selector_type,
                "resolved_selector": resolved_selector,
                "found": True,
                "element": details,
                "ts": datetime.now(timezone.utc).isoformat()
            }
            
            browser.close()
            return output
            
        except Exception as e:
            browser.close()
            return {
                "page_id": page_id,
                "url": url,
                "selector": selector,
                "selector_type": selector_type,
                "found": False,
                "error": str(e)
            }


def main():
    parser = argparse.ArgumentParser(description="Element Deep-Dive Drill")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--selector", required=True, help="CSS selector, XPath, or ref_id")
    parser.add_argument("--selector-type", default="css", choices=["css", "xpath", "ref"],
                       help="Selector type (default: css)")
    parser.add_argument("--max-depth", type=int, default=2, help="Parent context depth")
    
    args = parser.parse_args()
    
    output = drill_element(
        url=args.url,
        selector=args.selector,
        selector_type=args.selector_type,
        max_depth=args.max_depth
    )
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
