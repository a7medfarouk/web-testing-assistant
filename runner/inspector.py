"""Opens a page in a visible browser and extracts its interactive elements.

Usage (quick test):
    uv run python runner/inspector.py https://example.com
    uv run python runner/inspector.py https://example.com "#login-form"
    uv run python runner/inspector.py https://example.com --headless   # no window (CI / servers)

The result is plain JSON-serialisable data. Everything in it was OBSERVED on the
page (or verified against the live page, for locators). Nothing is guessed.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from time import perf_counter

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

MAX_ELEMENTS = 300  # cap per scan so huge pages stay fast and fit in a model prompt
NETWORK_IDLE_MS = 5000  # best-effort wait so script-rendered pages (SPAs) can finish
TEXT_LIMIT = 80  # text/labels are cut here; locators on cut text are skipped

# JavaScript that runs INSIDE the page. It only reads the page and returns plain data.
# `scope` is an optional CSS selector that limits the scan to one part of the page.
COLLECT_JS = r"""
([scope, maxElements, textLimit]) => {
  let root = document;
  if (scope) {
    try { root = document.querySelector(scope); }
    catch (e) { return {error: 'invalid_scope'}; }
    if (!root) return {error: 'scope_not_found'};
  }

  const selector = [
    'a[href]', 'button', 'input', 'select', 'textarea', 'summary',
    '[contenteditable=""]', '[contenteditable="true"]',
    '[role=button]', '[role=link]', '[role=checkbox]', '[role=radio]',
    '[role=switch]', '[role=tab]', '[role=menuitem]', '[role=combobox]',
    '[role=textbox]', '[role=searchbox]', '[role=option]',
  ].join(',');

  const wanted = ['id', 'name', 'type', 'placeholder', 'aria-label', 'aria-labelledby',
                  'href', 'data-testid', 'data-test', 'data-cy', 'data-qa', 'role',
                  'title', 'alt', 'required', 'readonly', 'pattern', 'minlength',
                  'maxlength', 'min', 'max', 'target', 'aria-disabled',
                  'aria-checked', 'aria-expanded'];

  const norm = (s, n = textLimit) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);

  // Collect matching elements in page order. Also looks inside open shadow roots
  // (querySelectorAll cannot), and includes the scope element itself if it matches.
  const found = [];
  const visit = (node) => {
    if (node.nodeType === 1 && node.matches(selector)) found.push(node);
    if (node.shadowRoot) for (const c of node.shadowRoot.children) visit(c);
    for (const c of node.children) visit(c);
  };
  visit(root);

  // Text of a <label> without the text of the controls inside it
  // (a label wrapping a <select> would otherwise include every option).
  const labelText = (label) => {
    const copy = label.cloneNode(true);
    copy.querySelectorAll('input, select, textarea, button').forEach(n => n.remove());
    return copy.textContent;
  };

  // Visible name of a field: aria-label, aria-labelledby, then <label> (for= or wrapping).
  const labelOf = (el) => {
    if (el.getAttribute('aria-label')) return norm(el.getAttribute('aria-label'));
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const scopeRoot = el.getRootNode();
      const t = by.split(/\s+/).map(id => {
        const n = scopeRoot.getElementById ? scopeRoot.getElementById(id) : null;
        return n ? n.textContent : '';
      }).join(' ');
      if (norm(t)) return norm(t);
    }
    if (el.labels && el.labels.length) {
      return norm([...el.labels].map(labelText).join(' '));
    }
    return '';
  };

  const textOf = (el) => {
    if (el.tagName === 'INPUT') {
      return ['submit', 'button', 'reset'].includes(el.type) ? norm(el.value) : '';
    }
    if (el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') return '';
    return norm(el.innerText || el.textContent);
  };

  const quoteAttr = (v) => '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';

  // Position-based path from the nearest ancestor with a unique id (or the root).
  // Fragile, so Python only uses it as a last-resort locator.
  const cssPath = (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const tree = n.getRootNode();
      if (n.id && tree.querySelectorAll('[id=' + quoteAttr(n.id) + ']').length === 1) {
        parts.unshift('[id=' + quoteAttr(n.id) + ']');
        break;
      }
      const tag = n.tagName.toLowerCase();
      const same = [...(n.parentElement ? n.parentElement.children : [n])]
                     .filter(s => s.tagName === n.tagName);
      parts.unshift(same.length > 1 ? `${tag}:nth-of-type(${same.indexOf(n) + 1})` : tag);
    }
    return parts.join(' > ');
  };

  const buttonLike = ['submit', 'button', 'reset', 'image'];
  const elements = found
    .filter(el => el.type !== 'hidden')
    .slice(0, maxElements)
    .map(el => {
      const box = el.getBoundingClientRect();
      const attrs = {};
      wanted.forEach(n => {
        if (el.hasAttribute(n)) attrs[n] = el.getAttribute(n).slice(0, 300);
      });
      // value identifies buttons/radios/checkboxes; never record typed text or passwords
      if (el.tagName === 'INPUT' && [...buttonLike, 'radio', 'checkbox'].includes(el.type)
          && el.hasAttribute('value')) {
        attrs.value = el.getAttribute('value').slice(0, 300);
      }
      const form = el.closest('form');
      const out = {
        tag: el.tagName.toLowerCase(),
        text: textOf(el),
        label: labelOf(el),
        attributes: attrs,
        visible: box.width > 0 && box.height > 0 &&
                 getComputedStyle(el).visibility !== 'hidden',
        // :disabled also covers inputs inside <fieldset disabled>
        enabled: !el.matches(':disabled') && el.getAttribute('aria-disabled') !== 'true',
        form: form ? (form.id || form.getAttribute('name') || 'form') : null,
        css_path: cssPath(el),
      };
      if (el.tagName === 'INPUT' && ['checkbox', 'radio'].includes(el.type)) {
        out.checked = el.checked;
      }
      if (el.tagName === 'SELECT') {
        out.options = [...el.options].slice(0, 50).map(o => norm(o.text, 60));
      }
      if (el.getRootNode() instanceof ShadowRoot) out.in_shadow_dom = true;
      return out;
    });

  return {elements, total: found.filter(el => el.type !== 'hidden').length};
}
"""

# input types that have a different ARIA role than "textbox"
INPUT_ROLES = {
    "checkbox": "checkbox",
    "radio": "radio",
    "search": "searchbox",
    "number": "spinbutton",
    "range": "slider",
    "submit": "button",
    "button": "button",
    "reset": "button",
    "image": "button",
}
# input types with no ARIA role that get_by_role can find
INPUT_NO_ROLE = {"file", "color", "date", "datetime-local", "month", "time", "week"}


def guess_role(el):
    """Map an element to its ARIA role, used for get_by_role locators."""
    tag, attrs = el["tag"], el["attributes"]
    explicit = attrs.get("role", "").split(" ")[0].lower()
    if explicit:  # an explicit role="..." overrides the tag (e.g. <a role="button">)
        return explicit
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "select":
        return "combobox"
    if tag == "textarea":
        return "textbox"
    if tag == "input":
        input_type = attrs.get("type", "text").lower()
        if input_type in INPUT_NO_ROLE:
            return None
        return INPUT_ROLES.get(input_type, "textbox")
    return None


def css_quote(value):
    """Quote a value for a CSS attribute selector, e.g. [id="a\\"b"]."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_locators(page, el):
    """Build candidate locators, best first, and count how many elements each matches.

    unique=True means the locator matches exactly one element (safe to act on).
    stable=False marks position-based locators that break when the layout changes.
    """
    attrs, q = el["attributes"], json.dumps  # json.dumps quotes strings safely
    options = []  # (strategy, code, playwright locator)

    if attrs.get("data-testid"):
        v = attrs["data-testid"]
        options.append(("test_id", f"get_by_test_id({q(v)})", page.get_by_test_id(v)))

    # Skip role locators for long names: the text was cut at TEXT_LIMIT characters,
    # so it would not match the element's real accessible name.
    role, name = guess_role(el), (el["label"] or el["text"])
    if role and name and len(name) < TEXT_LIMIT:
        options.append(
            (
                "role",
                f"get_by_role({q(role)}, name={q(name)}, exact=True)",
                page.get_by_role(role, name=name, exact=True),
            )
        )

    if el["label"] and el["tag"] in ("input", "select", "textarea"):
        options.append(
            (
                "label",
                f"get_by_label({q(el['label'])}, exact=True)",
                page.get_by_label(el["label"], exact=True),
            )
        )

    if attrs.get("placeholder"):
        v = attrs["placeholder"]
        options.append(
            (
                "placeholder",
                f"get_by_placeholder({q(v)}, exact=True)",
                page.get_by_placeholder(v, exact=True),
            )
        )

    # Elements with no ARIA role (e.g. <summary>) can still be found by their text.
    if not role and el["text"] and len(el["text"]) < TEXT_LIMIT:
        options.append(
            (
                "text",
                f"get_by_text({q(el['text'])}, exact=True)",
                page.get_by_text(el["text"], exact=True),
            )
        )

    if attrs.get("id"):
        css = f"[id={css_quote(attrs['id'])}]"
        options.append(("css_id", f"locator({q(css)})", page.locator(css)))

    # Sites that use another test attribute than data-testid (data-test, data-cy, ...)
    for attr in ("data-test", "data-cy", "data-qa"):
        if attrs.get(attr):
            css = f"[{attr}={css_quote(attrs[attr])}]"
            options.append(
                (
                    f"css_{attr.replace('-', '_')}",
                    f"locator({q(css)})",
                    page.locator(css),
                )
            )

    if attrs.get("name"):
        css = f"{el['tag']}[name={css_quote(attrs['name'])}]"
        options.append(("css_name", f"locator({q(css)})", page.locator(css)))

    if el["tag"] == "a" and attrs.get("href"):
        css = f"a[href={css_quote(attrs['href'])}]"
        options.append(("css_href", f"locator({q(css)})", page.locator(css)))

    results = []
    for strategy, code, locator in options:
        count = safe_count(locator)
        if count > 0:  # a locator that matches nothing is not a usable candidate
            results.append(
                {
                    "strategy": strategy,
                    "code": code,
                    "match_count": count,
                    "unique": count == 1,
                    "stable": True,
                }
            )

    # Last resort: if nothing above is unique, offer a position-based locator so the
    # element can still be targeted. It is marked stable=False for the tester.
    if not any(r["unique"] for r in results) and el.get("css_path"):
        css = el["css_path"]
        count = safe_count(page.locator(css))
        if count > 0:
            results.append(
                {
                    "strategy": "css_path",
                    "code": f"locator({q(css)})",
                    "match_count": count,
                    "unique": count == 1,
                    "stable": False,
                }
            )
    return results


def safe_count(locator):
    """Count matches; an unusable locator counts as 0 instead of aborting the scan."""
    try:
        return locator.count()
    except PlaywrightError:
        return 0


def inspect_page(url, scope=None, headless=False):
    """Open `url` in a (visible) browser and return the structured findings."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    started = perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            response = page.goto(url, wait_until="load")
            try:  # best effort: pages that never go idle are scanned as they are
                page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
            except PlaywrightTimeoutError:
                pass

            collected = page.evaluate(COLLECT_JS, [scope, MAX_ELEMENTS, TEXT_LIMIT])
            if "error" in collected:
                if collected["error"] == "invalid_scope":
                    raise ValueError(f"Scope is not a valid CSS selector: {scope}")
                raise ValueError(f"Scope selector not found on the page: {scope}")

            elements = []
            # Numbered 1..n in page order for THIS scan only. A scan with another scope
            # (or a later rescan) numbers its own elements again from 1.
            for i, el in enumerate(collected["elements"], start=1):
                el["id"] = i
                el["locators"] = build_locators(page, el)
                del el["css_path"]  # internal helper, already turned into a locator
                elements.append(el)

            status = response.status if response else None
            result = {
                "url": page.url,  # final URL, after any redirects
                "requested_url": url,
                "title": page.title(),
                "scope": scope,
                "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "http_status": status,
                "browser": f"chromium {browser.version}",
                "scan_seconds": round(perf_counter() - started, 2),
                "element_count": len(elements),
                "truncated": collected["total"] > len(elements),
                "warnings": scan_warnings(
                    page, status, scope, collected["total"], elements
                ),
                "elements": elements,
            }
            return result
        finally:
            browser.close()


def scan_warnings(page, status, scope, total, elements):
    """Things the tester should know about because they limit what was observed."""
    warnings = []
    if status is not None and status >= 400:
        warnings.append(
            f"The page answered with HTTP {status}; it may be an error page."
        )
    iframes = len(page.frames) - 1
    if iframes > 0 and not scope:
        warnings.append(f"{iframes} iframe(s) on the page were NOT inspected.")
    if total > len(elements):
        warnings.append(
            f"Only the first {len(elements)} of {total} elements are listed. "
            "Narrow the scope to see the rest."
        )
    if not elements:
        warnings.append(
            "No interactive elements found"
            + (" inside the given scope." if scope else ".")
        )
    return warnings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument(
        "scope", nargs="?", help="optional CSS selector to limit the scan"
    )
    parser.add_argument(
        "--headless", action="store_true", help="do not show the browser"
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # so emojis print on Windows
    print(
        json.dumps(
            inspect_page(args.url, args.scope, args.headless),
            indent=2,
            ensure_ascii=False,
        )
    )
