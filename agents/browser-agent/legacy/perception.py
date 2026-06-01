"""Perception: extract a compact, LLM-friendly view of the page."""
import re
from typing import Any

from playwright.async_api import Page


# Snapshot script: tag every interactive element with [refN] and return
# a flat list. Keeps the LLM context small and gives us a stable handle.
SNAPSHOT_JS = r"""
() => {
    const tagMap = new Map();
    let counter = 0;
    const selectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [contenteditable="true"], [onclick]';
    const nodes = Array.from(document.querySelectorAll(selectors));
    const items = [];
    for (const el of nodes) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') continue;
        counter += 1;
        const ref = 'ref' + counter;
        el.setAttribute('data-agent-ref', ref);
        const tag = el.tagName.toLowerCase();
        let label = (el.getAttribute('aria-label')
            || el.getAttribute('placeholder')
            || el.getAttribute('name')
            || el.innerText
            || el.value
            || '').trim().replace(/\s+/g, ' ').slice(0, 100);
        const type = el.getAttribute('type') || '';
        const role = el.getAttribute('role') || '';
        items.push({
            ref,
            tag,
            type,
            role,
            label,
            href: el.getAttribute('href') || null,
            value: (el.value || '').slice(0, 80),
            visible: rect.top < window.innerHeight && rect.bottom > 0,
        });
    }
    return {
        url: location.href,
        title: document.title,
        items,
    };
}
"""


SECURITY_PROBE_JS = r"""
() => {
    const out = {
        forms: [],
        captcha: [],
        csrf: false,
        autocomplete_off: false,
        password_inputs: 0,
        scripts_external: [],
        cookies_doc: document.cookie ? document.cookie.split(';').length : 0,
    };
    for (const form of document.querySelectorAll('form')) {
        const f = {
            action: form.action,
            method: (form.method || 'get').toLowerCase(),
            id: form.id || null,
            autocomplete: form.autocomplete || null,
            fields: [],
            has_csrf_token: false,
        };
        for (const inp of form.querySelectorAll('input, select, textarea')) {
            const name = (inp.name || '').toLowerCase();
            if (/csrf|_token|authenticity/.test(name)) f.has_csrf_token = true;
            if (inp.type === 'password') out.password_inputs += 1;
            f.fields.push({
                name: inp.name,
                type: inp.type || inp.tagName.toLowerCase(),
                required: inp.required,
                autocomplete: inp.getAttribute('autocomplete'),
                placeholder: inp.getAttribute('placeholder'),
            });
        }
        out.forms.push(f);
    }
    // captcha sniff
    const html = document.documentElement.innerHTML.toLowerCase();
    if (html.includes('recaptcha')) out.captcha.push('reCAPTCHA');
    if (html.includes('hcaptcha')) out.captcha.push('hCaptcha');
    if (html.includes('turnstile')) out.captcha.push('Cloudflare Turnstile');
    if (document.querySelector('img[src*="captcha"]')) out.captcha.push('image-captcha');
    out.csrf = out.forms.some(f => f.has_csrf_token);
    out.autocomplete_off = out.forms.some(f => f.autocomplete === 'off');
    // external scripts
    for (const s of document.querySelectorAll('script[src]')) {
        try {
            const u = new URL(s.src);
            if (u.host !== location.host) out.scripts_external.push(u.host);
        } catch {}
    }
    out.scripts_external = Array.from(new Set(out.scripts_external));
    return out;
}
"""


async def snapshot(page: Page) -> dict[str, Any]:
    """Return {url, title, items[], body_excerpt} — compact interactive view."""
    snap = await page.evaluate(SNAPSHOT_JS)
    try:
        body = await page.evaluate("() => (document.body.innerText || '').slice(0, 1500)")
    except Exception:
        body = ""
    snap["body_excerpt"] = body
    return snap


async def security_probe(page: Page) -> dict[str, Any]:
    """Run a passive security probe on the current page (no exploits)."""
    return await page.evaluate(SECURITY_PROBE_JS)


def format_snapshot_for_llm(snap: dict[str, Any], max_items: int = 60) -> str:
    """Render the snapshot as compact text for an LLM prompt."""
    lines = [f"URL: {snap['url']}", f"TITLE: {snap['title']}"]
    body = (snap.get("body_excerpt") or "").strip()
    if body:
        lines.append(f"VISIBLE TEXT (truncated):\n{body[:600]}")
    lines.append("ELEMENTS:")
    for it in snap["items"][:max_items]:
        meta = it["tag"]
        if it["type"]:
            meta += f"[{it['type']}]"
        elif it["role"]:
            meta += f"[role={it['role']}]"
        label = it["label"][:80] or "(no-label)"
        extra = ""
        if it["href"]:
            extra = f" href={it['href'][:60]}"
        if it["value"]:
            extra += f" value={it['value'][:40]}"
        lines.append(f"  [{it['ref']}] {meta} \"{label}\"{extra}")
    if len(snap["items"]) > max_items:
        lines.append(f"  ... +{len(snap['items']) - max_items} more")
    return "\n".join(lines)


def find_ref(snap: dict[str, Any], ref: str) -> dict[str, Any] | None:
    for it in snap["items"]:
        if it["ref"] == ref:
            return it
    return None
