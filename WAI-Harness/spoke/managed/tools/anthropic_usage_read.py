#!/usr/bin/env python3
"""Read the Anthropic usage page, because it is the only place the real number exists.

OPERATOR 2026-08-15: "ill authenticate the playwright session how can we do it".

WHY A BROWSER AT ALL. No Anthropic API exposes remaining subscription headroom. The
harness has carried a hand-typed percentage for this since July, and on 2026-08-15 that
number was 583 HOURS old while still being read as current -- it was closing the budget
gate over a spend ledger generated that morning, so paid-for capacity expired unused every
window. A number a human must remember to retype is a number that goes stale.

BLOCKED IN PRACTICE, 2026-08-15. The operator tried --login and claude.ai served an endless
human-verification challenge. That check is WORKING AS INTENDED: a Playwright-driven
Chromium is detectable, and the challenge exists to stop automated session use. Do not add
stealth flags, a UA override, or a solver -- that is bot-detection evasion against the
operator's own account and risks the account, which costs far more than the ten seconds the
manual path takes.

USE `wai budget --record` INSTEAD. Read the three numbers off the page by eye and type them;
the gate treats a hand-recorded reading exactly the same and expires it after 5h either way.

This file is kept rather than deleted because the finding is worth more than the code: it
records that the browser route was tried, why it failed, and why the failure must not be
"fixed". Anyone reaching for automation here should read this paragraph first.

TWO MODES, because authentication is a one-time human act and reading is not:

    anthropic_usage_read.py --login    headed browser, you sign in, profile is saved
    anthropic_usage_read.py --read     headless, reuses that profile, records the numbers

SCRAPING A UI IS BRITTLE AND THIS FILE ADMITS IT. The contract is therefore narrow:

  - It NEVER writes a number it did not parse. A missing window is absent, not zero.
  - It saves the raw extracted text next to the reading, so a wrong parse is auditable
    rather than merely wrong.
  - It reports UNREADABLE and exits nonzero when the page shape changes, which it will.
    A scraper that silently starts returning nothing is the stale-file failure again, and
    the whole point of this exercise was to stop that.

The profile directory holds a live session cookie. It is gitignored and never printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROFILE = REPO / "WAI-Harness" / "spoke" / "local" / "runtime" / "browser-profile"
RAW = REPO / "WAI-Harness" / "spoke" / "local" / "runtime" / "anthropic-usage-raw.txt"
USAGE_URL = "https://claude.ai/settings/usage"

# What each window is called on the page, in the order we prefer to match. Several spellings
# because the label has changed before and will change again; an unmatched label is reported,
# never guessed at.
WINDOW_PATTERNS = {
    "five_hour": (r"(?:current\s+)?(?:5|five)[\s-]*hour", r"session"),
    "weekly": (r"weekly.*(?:all[\s-]*model|usage|limit)", r"week"),
    "opus": (r"opus", r"frontier"),
}
PCT = re.compile(r"(\d{1,3})\s*%")
RESET = re.compile(r"[Rr]esets?\s+(?:at\s+|on\s+|in\s+)?([^\n,.]{3,40})")


def _pw():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed: pip install playwright && playwright install chromium")
    return sync_playwright


def login() -> int:
    """Open a real browser so the operator can sign in once. Saves the session profile."""
    PROFILE.mkdir(parents=True, exist_ok=True)
    with _pw()() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, viewport={"width": 1280, "height": 900})
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(USAGE_URL, wait_until="domcontentloaded")
        print("A browser window is open on Claude Settings -> Usage.")
        print("Sign in if prompted, make sure the usage numbers are visible, then come back")
        print("here and press Enter. The session is saved to the profile; your credentials")
        print("are never read by this script.")
        input("  press Enter when the usage page is showing... ")
        text = page.inner_text("body")
        context.close()
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(text, encoding="utf-8")
    print(f"profile saved. captured {len(text)} chars of page text -> {RAW}")
    return 0


def _extract(text: str) -> dict:
    """Pull a remaining-percent and a reset hint per window. Absent beats guessed."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found = {}
    for key, patterns in WINDOW_PATTERNS.items():
        for index, line in enumerate(lines):
            if not any(re.search(p, line, re.I) for p in patterns):
                continue
            # The percent usually sits on the label line or within the next two.
            window = " ".join(lines[index:index + 3])
            pct = PCT.search(window)
            if not pct:
                continue
            used = int(pct.group(1))
            reset = RESET.search(window)
            found[key] = {
                # The page reports USED. The gate stores REMAINING, and confusing the two is
                # not a rounding error, it is the gate inverted.
                "pct_used_on_page": used,
                "pct_left": 100 - used,
                "resets_at": reset.group(1).strip() if reset else "",
                "matched_line": line[:120],
            }
            break
    return found


def read(record: bool) -> int:
    if not PROFILE.is_dir():
        print("no saved profile: run --login first", file=sys.stderr)
        return 2
    with _pw()() as p:
        context = p.chromium.launch_persistent_context(str(PROFILE), headless=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(USAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        text = page.inner_text("body")
        context.close()

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(text, encoding="utf-8")

    if "log in" in text.lower() or "sign in" in text.lower():
        print("UNREADABLE: the session is not authenticated. Run --login again.",
              file=sys.stderr)
        return 1

    found = _extract(text)
    if not found:
        print(f"UNREADABLE: no usage window matched. Raw page text saved to {RAW} -- the "
              "page shape has changed and WINDOW_PATTERNS needs updating. Nothing was "
              "recorded, because a scraper that writes on a failed parse is worse than one "
              "that stops.", file=sys.stderr)
        return 1

    for key, row in found.items():
        print(f"  {key:<10} {row['pct_left']}% left "
              f"(page said {row['pct_used_on_page']}% used)"
              + (f", resets {row['resets_at']}" if row["resets_at"] else ""))

    if record:
        sys.path.insert(0, str(REPO / "WAI-Harness"))
        from kernel import budget
        saved = budget.record_observation(
            REPO,
            five_hour_pct_left=found.get("five_hour", {}).get("pct_left"),
            weekly_pct_left=found.get("weekly", {}).get("pct_left"),
            opus_pct_left=found.get("opus", {}).get("pct_left"),
            resets_at=found.get("five_hour", {}).get("resets_at", ""),
            weekly_resets_at=found.get("weekly", {}).get("resets_at", ""),
            note="scraped from claude.ai/settings/usage by anthropic_usage_read.py")
        print(f"recorded {len(saved['windows'])} window(s); expires as evidence after 5h")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", action="store_true", help="headed sign-in, saves the profile")
    ap.add_argument("--read", action="store_true", help="headless read of the usage page")
    ap.add_argument("--record", action="store_true",
                    help="with --read, write the reading into the budget gate")
    args = ap.parse_args(argv)
    if args.login:
        return login()
    if args.read:
        return read(args.record)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
