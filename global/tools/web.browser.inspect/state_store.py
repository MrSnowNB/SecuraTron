"""
State store for browser toolchain — shared page state persistence.
Keeps element mappings between inspect -> drill -> interact calls.
"""

import json
import os

STATE_DIR = os.path.expanduser("~/.securatron/global/tools/web.browser.inspect/.state")


def save_page_state(page_id, url, title, interactive_elements):
    """Save inspect result so drill/interact can find elements without re-scanning."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, f"{page_id}.json")
    data = {
        "page_id": page_id,
        "url": url,
        "title": title,
        "elements": []
    }
    for i, el in enumerate(interactive_elements):
        data["elements"].append({
            "ref_id": el.get("ref_id", f"@e{i+1}"),
            "tag": el.get("tag", "div"),
            "type": el.get("type", ""),
            "text": el.get("text", ""),
            "position": el.get("position", ""),
            "meta": el.get("meta", {}),
            "selector": None,
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def load_page_state(page_id):
    """Load a previously saved page state. Returns None if not found."""
    path = os.path.join(STATE_DIR, f"{page_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def lookup_selector(page, page_id, ref_id):
    """
    Given a freshly-loaded page, find the element that matches the
    stored ref_id using tag + type + text + meta attributes.
    Returns a Playwright selector string or None.
    """
    state = load_page_state(page_id)
    if not state:
        return None

    target = None
    for el in state["elements"]:
        if el["ref_id"] == ref_id:
            target = el
            break

    if not target:
        return None

    tag = target["tag"]
    el_type = target["type"]
    el_text = target["text"]
    meta = target.get("meta", {})
    position = target.get("position", "")

    sel_parts = [tag]

    # For input elements, use meta attributes for precise matching
    if tag == "input":
        # Try by ID first (most specific)
        input_id = meta.get("input_id")
        if input_id:
            sel_parts = [f"#{input_id}"]

        # Try by type + name
        input_type = meta.get("input_type")
        input_name = meta.get("input_name")
        if not input_id:
            if input_type:
                sel_parts.append('[type="{}"]'.format(input_type))
            if input_name:
                sel_parts.append('[name="{}"]'.format(input_name))

        # Try by placeholder
        placeholder = meta.get("placeholder")
        if not (input_id or input_name):
            if placeholder:
                sel_parts.append(':text("{}")'.format(placeholder))

        # Try type + role
        input_role = meta.get("role")
        if not input_id and input_type and not input_name:
            sel_parts = ['input[type="{}"]'.format(input_type)]
            if input_role:
                sel_parts.append('[role="{}"]'.format(input_role))

    elif tag == "button":
        input_id = meta.get("input_id")
        if input_id:
            sel_parts = [f"#{input_id}"]
        elif el_text:
            sel_parts.append(':text("{}")'.format(el_text))

    elif tag in ("a", "button") and el_text:
        sel_parts.append(':text("{}")'.format(el_text))

    # Also try type attribute (for input/button role mismatch)
    if el_type and el_type != tag and not (tag == "input" and meta.get("input_id")):
        # Don't double-add if already in parts
        type_selector = '[type="{}"]'.format(el_type)
        if type_selector not in sel_parts:
            sel_parts.append(type_selector)

    selector = "".join(sel_parts) if len(sel_parts) > 0 else tag

    # Try the constructed selector
    try:
        elem = page.query_selector(selector)
        if elem:
            return selector
    except Exception:
        pass

    # Fallback for input: try :nth-of-type with position hint
    if tag == "input":
        try:
            if position == "top":
                count = page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('input');
                        return Array.from(els).filter(e => {
                            const r = e.getBoundingClientRect();
                            return r.top < window.innerHeight / 3;
                        }).length;
                    }
                """)
                if count <= 5:
                    return "input:nth-of-type({})".format(count)
        except Exception:
            pass

    # Last resort: return the tag
    return tag
