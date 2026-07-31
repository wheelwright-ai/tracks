#!/usr/bin/env python3
"""uat_verdict.py -- the uat-verdict verb (impl-exitclarity-5-uat-request-on-completion-v1).

Flips a completed lug's uat_status (accepted/rejected), closes the companion
UAT review lug (bytype/review/open/uat-<id>.json), and on reject authors a fix
lug carrying the rejection reason + original evidence.

Usage:
  uat_verdict.py <lug-id> accept
  uat_verdict.py <lug-id> reject "<reason>"
  uat_verdict.py <lug-id> reject "<reason>" --spoke-path WAI-Harness/spoke/local
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uat_request import apply_verdict  # noqa: E402
from wai_paths import resolve_wai_root  # noqa: E402  (v3/v4 resolver)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="uat-verdict -- accept or reject a UAT-needed lug")
    ap.add_argument("lug_id", help="the ORIGINAL completed lug's id (not the uat-<id> review lug)")
    ap.add_argument("verdict", choices=["accept", "reject"])
    ap.add_argument("reason", nargs="?", default="", help="required for reject; ignored for accept")
    ap.add_argument("--spoke-path", default=".", help="project root (default: cwd)")
    args = ap.parse_args(argv)

    if args.verdict == "reject" and not args.reason.strip():
        print("uat-verdict: a reject verdict requires a reason -- "
              "uat_verdict.py <lug-id> reject '<reason>'", file=sys.stderr)
        return 2

    base, _mode = resolve_wai_root(args.spoke_path)
    spoke_wai = Path(base) if base else Path(args.spoke_path)
    bytype_dir = spoke_wai / "lugs" / "bytype"
    activity_log = spoke_wai.parent / "advisors" / "autopilot" / "activity-log.jsonl"
    if not activity_log.parent.exists():
        activity_log = spoke_wai / "advisors" / "autopilot" / "activity-log.jsonl"

    result = apply_verdict(
        args.lug_id, args.verdict, args.reason, bytype_dir, activity_log=activity_log
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
