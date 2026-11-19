"""Opens a page in a visible browser and extracts its interactive elements.

Usage (quick test):
    uv run python runner/inspector.py https://example.com
    uv run python runner/inspector.py https://example.com "#login-form"
"""
import json
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

# JavaScript that runs INSIDE the page. It only reads the page and returns plain data.
# `scope` is an optional CSS selector that limits the scan to one part of the page.
COLLECT_JS = """
(scope) => {
  const root = scope ? document.querySelector(scope) : document;
  if (!root) return null;

  const selector = 'a[href], button, input, select, textarea, [role=button]';
  const wanted = ['id', 'name', 'type', 'placeholder', 'aria-label',
                  'href', 'data-testid', 'role'];

  // Find the visible label of a field (aria-label, <label for=...>, or wrapping <label>)
  const labelOf = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) return l.innerText.trim();
    }
    const wrap = el.closest('label');
    return wrap ? wrap.innerText.trim() : '';
  };

  return [...root.querySelectorAll(selector)]
    .filter(el => el.type !== 'hidden')
    .map(el => {
      const box = el.getBoundingClientRect();
      const attrs = {};
      wanted.forEach(n => { if (el.hasAttribute(n)) attrs[n] = el.getAttribute(n); });
      const isInputButton = el.tagName === 'INPUT' &&
                            ['submit', 'button', 'reset'].includes(el.type);
      const form = el.closest('form');
      return {
        tag: el.tagName.toLowerCase(),
        text: (isInputButton ? el.value : (el.innerText || ''))
                .replace(/\\s+/g, ' ').trim().slice(0, 80),
        label: labelOf(el),
        attributes: attrs,
        visible: box.width > 0 && box.height > 0 &&
                 getComputedStyle(el).visibility !== 'hidden',
        enabled: !el.disabled,
        form: form ? (form.id || form.getAttribute('name') || 'form') : null,
      };
    });
}
"""


def guess_role(el):
    """Map an element to its ARIA role, used for get_by_role locators."""
    tag, attrs = el["tag"], el["attributes"]
    input_type = attrs.get("type", "text")
    if tag == "a":
        return "link"
    if (tag == "button" or attrs.get("role") == "button"
            or (tag == "input" and input_type in ("submit", "button", "reset"))):
        return "button"
    if tag == "select":
        return "combobox"
    if tag == "textarea":
        return "textbox"
    if tag == "input":
        return {"checkbox": "checkbox", "radio": "radio"}.get(input_type, "textbox")
    return None


def build_locators(page, el):
    """Build candidate locators, best first, and count how many elements each matches.

    unique=True means the locator matches exactly one element (safe to act on).
    """
    attrs, q = el["attributes"], json.dumps  # json.dumps quotes strings safely
    options = []  # (strategy, code, playwright locator)

    if attrs.get("data-testid"):
        v = attrs["data-testid"]
        options.append(("test_id", f"get_by_test_id({q(v)})", page.get_by_test_id(v)))

    # Skip role locators for long names: the text was cut at 80 characters,
    # so it would not match the element's real accessible name.
    role, name = guess_role(el), (el["label"] or el["text"])
    if role and name and len(name) < 80:
        options.append(("role", f"get_by_role({q(role)}, name={q(name)}, exact=True)",
                        page.get_by_role(role, name=name, exact=True)))

    if el["label"] and el["tag"] in ("input", "select", "textarea"):
        options.append(("label", f"get_by_label({q(el['label'])}, exact=True)",
                        page.get_by_label(el["label"], exact=True)))

    if attrs.get("placeholder"):
        v = attrs["placeholder"]
        options.append(("placeholder", f"get_by_placeholder({q(v)}, exact=True)",
                        page.get_by_placeholder(v, exact=True)))

    if attrs.get("id"):
        css = f'[id="{attrs["id"]}"]'
        options.append(("css_id", f"locator({q(css)})", page.locator(css)))

    if attrs.get("name"):
        css = f'{el["tag"]}[name="{attrs["name"]}"]'
        options.append(("css_name", f"locator({q(css)})", page.locator(css)))

    if el["tag"] == "a" and attrs.get("href"):
        css = f'a[href="{attrs["href"]}"]'
        options.append(("css_href", f"locator({q(css)})", page.locator(css)))

    results = []
    for strategy, code, locator in options:
        count = locator.count()
        if count > 0:  # a locator that matches nothing is not a usable candidate
            results.append({"strategy": strategy, "code": code,
                            "match_count": count, "unique": count == 1})
    return results


def inspect_page(url, scope=None, headless=False):
    """Open `url` in a (visible) browser and return the structured findings."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="load")

        raw = page.evaluate(COLLECT_JS, scope)
        if raw is None:
            browser.close()
            raise ValueError(f"Scope selector not found on the page: {scope}")

        elements = []
        for i, el in enumerate(raw, start=1):
            el["id"] = i  # stable id so the user (and the model) can refer to it
            el["locators"] = build_locators(page, el)
            elements.append(el)

        result = {
            "url": page.url,
            "title": page.title(),
            "scope": scope,
            "scanned_at": datetime.now().isoformat(timespec="seconds"),
            "elements": elements,
        }
        browser.close()
        return result


if __name__ == "__main__":
    target = sys.argv[1]
    css_scope = sys.argv[2] if len(sys.argv) > 2 else None
    sys.stdout.reconfigure(encoding="utf-8")  # so emojis print on Windows
    print(json.dumps(inspect_page(target, css_scope), indent=2, ensure_ascii=False))