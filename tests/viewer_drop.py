"""Browser test (B-004): drop a sample track on the static viewer, opened from
file:// (no server), and see its turns, decisions and open items."""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

root = pathlib.Path(__file__).resolve().parent.parent
sample = root / "samples" / "coding-session.jsonl"
pts = [json.loads(l) for l in sample.read_text().splitlines() if l.strip()]
pts = [p for p in pts if "turn" in p]
n_dec = sum(len(p.get("decisions", [])) for p in pts)
n_open = sum(len(p.get("open", [])) for p in pts)

with sync_playwright() as p:
    import glob, os
    exe = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium*/*/chrome-headless-shell"))
                 + glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/*/chrome")))
    try:
        b = p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path=exe[-1])
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto((root / "viewer" / "index.html").as_uri())
    page.evaluate("""async ([name, text]) => {
      const dt = new DataTransfer();
      dt.items.add(new File([text], name, {type: 'application/jsonl'}));
      for (const t of ['dragenter', 'dragover', 'drop'])
        window.dispatchEvent(new DragEvent(t, {dataTransfer: dt, bubbles: true, cancelable: true}));
    }""", [sample.name, sample.read_text()])
    page.wait_for_selector("#timeline-list li")
    assert page.locator("#timeline-list li").count() == len(pts), "turns"
    assert page.inner_text("#summary-turns") == str(len(pts))
    dec = page.inner_text("#digest-decisions")
    opn = page.inner_text("#digest-open")
    assert f"Decisions ({n_dec})" in dec and n_dec > 0
    assert f"Open items ({n_open})" in opn and n_open > 0
    first_dec = next(d for p_ in pts for d in p_.get("decisions", []))
    probe = next(str(v) for v in (first_dec.values() if isinstance(first_dec, dict) else [first_dec]))
    assert probe in dec, "decision text visible"
    assert not errors, errors
    b.close()
print(f"PASS: dropped {sample.name}: {len(pts)} turns, {n_dec} decisions, {n_open} open items shown")
