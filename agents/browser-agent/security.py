"""Passive security probe — read-only inspection of the current page."""
from typing import Any


SECURITY_PROBE_JS = r"""
() => {
    const out = {
        url: location.href,
        title: document.title,
        forms: [],
        captcha: [],
        csrf: false,
        autocomplete_off: false,
        password_inputs: 0,
        scripts_external: [],
        cookies_doc: document.cookie ? document.cookie.split(';').length : 0,
        meta_csp: null,
        meta_referrer: null,
        is_https: location.protocol === 'https:',
        mixed_content: false,
    };
    // CSP meta tag
    const cspMeta = document.querySelector('meta[http-equiv="Content-Security-Policy" i]');
    if (cspMeta) out.meta_csp = cspMeta.getAttribute('content');
    const refMeta = document.querySelector('meta[name="referrer" i]');
    if (refMeta) out.meta_referrer = refMeta.getAttribute('content');

    for (const form of document.querySelectorAll('form')) {
        const f = {
            action: form.action,
            method: (form.method || 'get').toLowerCase(),
            id: form.id || null,
            autocomplete: form.autocomplete || null,
            fields: [],
            has_csrf_token: false,
            insecure_action: form.action && form.action.startsWith('http://'),
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
    const html = document.documentElement.innerHTML.toLowerCase();
    if (html.includes('recaptcha')) out.captcha.push('reCAPTCHA');
    if (html.includes('hcaptcha')) out.captcha.push('hCaptcha');
    if (html.includes('turnstile')) out.captcha.push('Cloudflare Turnstile');
    if (document.querySelector('img[src*="captcha" i]')) out.captcha.push('image-captcha');
    out.csrf = out.forms.some(f => f.has_csrf_token);
    out.autocomplete_off = out.forms.some(f => f.autocomplete === 'off');

    for (const s of document.querySelectorAll('script[src]')) {
        try {
            const u = new URL(s.src);
            if (u.host !== location.host) out.scripts_external.push(u.host);
            if (out.is_https && u.protocol === 'http:') out.mixed_content = true;
        } catch {}
    }
    out.scripts_external = Array.from(new Set(out.scripts_external));
    return out;
}
"""


async def run_security_probe(page) -> dict[str, Any]:
    """Run a passive security probe on the current page (no exploits)."""
    return await page.evaluate(SECURITY_PROBE_JS)


JUDGE_SYSTEM = (
    "You are a security analyst reviewing a browser agent's findings. "
    "Given a goal, the captured page artifacts, and the security probe data, "
    "produce a concise judgement: severity, key risks, and recommended next steps. "
    "Be specific and avoid hand-waving."
)


def build_judge_prompt(goal: str, probe: dict[str, Any], notes: str) -> str:
    import json
    return (
        f"GOAL: {goal}\n\n"
        f"SECURITY PROBE:\n{json.dumps(probe, indent=2)[:4000]}\n\n"
        f"AGENT NOTES:\n{notes[:3000]}\n\n"
        "Produce a short report: 1) Findings 2) Risk rating (low/med/high) 3) Recommendations."
    )
