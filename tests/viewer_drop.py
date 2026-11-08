"""Browser test: drop a sample track on viewer/index.html via file:// (no server)."""
import pathlib, sys
from playwright.sync_api import sync_playwright
root = pathlib.Path(__file__).resolve().parent.parent
sample = (root / "samples/coding-session.jsonl").read_text()
with sync_playwright() as p:
    import glob, os; ex = os.environ.get("CHROMIUM") or (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")) or [None])[0]; b = p.chromium.launch(executable_path=ex); pg = b.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((root / "viewer/index.html").as_uri())
    dt = pg.evaluate_handle("""t => { const d = new DataTransfer();
      d.items.add(new File([t], 'coding-session.jsonl')); return d; }""", sample)
    pg.dispatch_event("body", "drop", {"dataTransfer": dt})
    pg.wait_for_function("document.querySelector('#summary-turns').textContent !== '0'")
    turns = pg.inner_text("#summary-turns"); opn = pg.inner_text("#summary-open")
    assert turns == "10", turns
    assert int(opn) > 0, opn
    assert pg.locator("#timeline-list li").count() == 10
    pg.locator("#timeline-list li").first.click()
    detail = pg.inner_text("#detail-view")
    assert "ecision" in detail and "pen" in detail, detail[:300]
    assert not errs, errs
    b.close()
print("viewer drop test: PASS")
