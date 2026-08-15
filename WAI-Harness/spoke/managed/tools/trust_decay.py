#!/usr/bin/env python3
"""trust_decay.py -- M1 of the LOW TRUST tenet: greens expire.

    "every green carries who verified it, with which oracle, and when;
     past TTL it renders AMBER, never green"
                                     -- spec-low-trust-tenet-v1, mechanism M1

THE DEFECT. Nothing in this harness gives a green an expiry date. `proven` is
awarded by trust_epoch the moment an independent verdict is recorded and is then
true forever: a certification from six months ago, run by a checker that has
since been retired, against a file that has since been rewritten, still reads
exactly as green as one earned this morning. That is not a measurement of trust,
it is a measurement of whether anyone ever looked. The same shape as the SILENT
oracle problem (M5) and the stale registry version column, arriving one layer up.

THE STAMP CONTRACT. A claim may render GREEN only if it answers all three
questions. They are not decoration; each closes a different way a green lies:

    WHO      an identified verifier            -- an unattributed pass cannot be
                                                  challenged, re-run, or blamed
    ORACLE   the specific check that was run   -- "it was verified" without naming
                                                  the check is a mood, and is the
                                                  exact phrasing the tenet was
                                                  written against
    WHEN     a parseable timestamp             -- without it there is no such thing
                                                  as expiry, so decay is unenforceable

A claim missing any of the three is UNSTAMPED. Deliberately NOT amber: amber says
"this was true and has aged out", which is a stronger statement than the evidence
supports. Unstamped says the green was never really independent to begin with, and
that is a different repair.

TTL, AND WHY IT IS NOT A MAGIC NUMBER. A green's life is derived from the cadence
of the oracle that produced it: cadence_days * DECAY_CYCLES. A check that runs
weekly buys about three weeks of confidence, so a green survives a couple of missed
cycles before it starts lying -- but not indefinitely. Where the oracle declares no
cadence, DEFAULT_TTL_DAYS applies, and the report SAYS the TTL was defaulted rather
than derived, because a defaulted TTL is a weaker claim than a derived one and the
reader is entitled to know which they are looking at.

WHAT IT REFUSES TO DO. It never promotes anything. A green can only be renewed by
a fresh verdict from an oracle that actually ran -- which is run_advisor's job, not
this tool's. A decay clock that could also mint greens would be able to launder
them, and this file exists precisely to stop that.

CLI:
    trust_decay.py --root DIR check   [--json]   classify every green claim
    trust_decay.py --root DIR stamp   --claim ID --verifier WHO --oracle WHAT
                                                 record a green with provenance

Exit codes: 0 greens exist and all are current; 1 findings present OR nothing
claims green at all; 2 could not read. An empty population is NOT a 0 -- "no
greens to check" is UNKNOWN, and UNKNOWN is not GREEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol
import trust_epoch as te

GREEN = "GREEN"
AMBER = "AMBER"
UNSTAMPED = "UNSTAMPED"

# Three cycles: a green survives a couple of missed runs before it starts lying,
# which is generous enough that ordinary scheduling noise does not raise a false
# amber, and tight enough that a genuinely dead oracle cannot hold a green open.
DECAY_CYCLES = 3
# Applied only where the oracle declares no cadence. Conservative on purpose: an
# unknown cadence is a weaker claim, so it buys less time, not more.
DEFAULT_TTL_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


def _parse(value):
    return te._parse_ts(value) if value else None


def stamp_of(record):
    """Extract (who, oracle, when) from a record, whatever shape it arrived in.

    Accepts either a nested `trust_stamp` object (what `stamp` writes) or the flat
    certification fields trust_epoch already reads, so existing certified lugs are
    evaluated on the evidence they actually carry rather than being declared
    unstamped for using the older shape.
    """
    stamp = record.get("trust_stamp")
    if isinstance(stamp, dict):
        return (stamp.get("verifier"), stamp.get("oracle"),
                _parse(stamp.get("verified_at")))

    who = record.get("certified_by") or record.get("verified_by")
    oracle = record.get("verifying_oracle") or record.get("oracle")
    when = _parse(record.get("certified_at") or record.get("recertified_at"))

    cert = record.get("certification")
    if isinstance(cert, dict):
        who = who or cert.get("certified_by") or cert.get("verifier")
        oracle = oracle or cert.get("oracle") or cert.get("check")
        when = when or _parse(cert.get("at") or cert.get("certified_at"))
    return who, oracle, when


def ttl_days(root, oracle):
    """(days, derived) -- a green lives as long as its oracle's cadence allows."""
    if oracle:
        row = ol.contract_row(root, str(oracle))
        cadence = ol.cadence_days(row) if row else None
        if cadence:
            return cadence * DECAY_CYCLES, True
    return DEFAULT_TTL_DAYS, False


def evaluate(root, claim_id, record, now=None):
    """Classify ONE green claim. Pure -- reads the record, writes nothing."""
    now = now or _now()
    who, oracle, when = stamp_of(record)

    missing = [name for name, value in
               (("verifier", who), ("oracle", oracle), ("verified_at", when))
               if not value]
    if missing:
        return {
            "claim": claim_id, "state": UNSTAMPED, "verifier": who,
            "oracle": oracle, "verified_at": te._iso(when) if when else None,
            "missing": missing,
            "why": ("cannot render green -- the stamp is missing "
                    + ", ".join(missing)
                    + "; an unattributed pass cannot be challenged or re-run, so it "
                      "was never independent evidence"),
        }

    days, derived = ttl_days(root, oracle)
    age = (now - when).days
    expires = when + timedelta(days=days)
    state = GREEN if now < expires else AMBER
    return {
        "claim": claim_id, "state": state, "verifier": who, "oracle": oracle,
        "verified_at": te._iso(when), "age_days": age, "ttl_days": days,
        "ttl_derived": derived, "expires_at": te._iso(expires),
        "why": (f"verified by {who} via {oracle} {age}d ago; "
                + (f"TTL {days}d derived from that oracle's cadence"
                   if derived else
                   f"TTL defaulted to {days}d -- that oracle declares no cadence, "
                   "so this green rests on a weaker claim than a derived one")
                + ("" if state == GREEN else
                   " -- EXPIRED, and renders AMBER until an oracle rules again")),
    }


def green_claims(root, mode=None):
    """Every record in this spoke that currently CLAIMS to be green.

    Today that is exactly the `proven` set from trust_epoch: work asserted as
    independently certified. Provisional work is excluded on purpose -- it makes
    no green claim, so it has nothing to decay, and sweeping it in here would
    inflate the finding count with records that are already honest about
    themselves.
    """
    out = []
    epoch = te.epoch_of(root, mode)
    for path in te.completed_lug_paths(root, mode):
        try:
            with open(path) as handle:
                lug = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(lug, dict):
            continue
        klass, _ = te.classify_lug(lug, epoch)
        if klass != te.CLASS_PROVEN:
            continue
        out.append((lug.get("id") or os.path.basename(path)[:-5], lug, path))
    return out


def check(root, mode=None, now=None):
    rows = [evaluate(root, cid, lug, now) for cid, lug, _ in green_claims(root, mode)]
    counts = {GREEN: 0, AMBER: 0, UNSTAMPED: 0}
    for row in rows:
        counts[row["state"]] += 1
    return {
        "checked_at": te._iso(now or _now()),
        "green_claims": len(rows),
        "counts": counts,
        "decay_cycles": DECAY_CYCLES,
        "default_ttl_days": DEFAULT_TTL_DAYS,
        "rows": rows,
        # An empty population is NOT a pass. Nothing claims green here yet, and
        # reporting that as "all greens current" is the false-green this whole
        # tenet exists to remove.
        "headline": (
            "no green claims on this spoke -- nothing to decay, and that is not a pass"
            if not rows else
            f"{counts[GREEN]} green, {counts[AMBER]} amber, {counts[UNSTAMPED]} unstamped"
        ),
    }


def stamp(root, claim_id, verifier, oracle, mode=None, when=None):
    """Record provenance on a completed lug. Records WHO/ORACLE/WHEN -- it does
    NOT award proven. Only an oracle's verdict does that, and keeping the two
    apart is what stops this tool from being able to launder a green."""
    for path in te.completed_lug_paths(root, mode):
        try:
            with open(path) as handle:
                lug = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(lug, dict):
            continue
        if (lug.get("id") or os.path.basename(path)[:-5]) != claim_id:
            continue
        lug["trust_stamp"] = {
            "verifier": verifier,
            "oracle": oracle,
            "verified_at": te._iso(when or _now()),
            "_contract": ("who verified it, with which oracle, and when -- a green "
                          "missing any of the three renders UNSTAMPED (M1)"),
        }
        with open(path, "w") as handle:
            json.dump(lug, handle, indent=2)
        return {"claim": claim_id, "stamped": True, "path": path,
                "stamp": lug["trust_stamp"]}
    return {"claim": claim_id, "stamped": False,
            "why": "no completed lug with that id -- refusing to stamp what is not there"}


def render(report):
    lines = [f"trust_decay {report['checked_at']}  {report['headline']}"]
    for row in report["rows"]:
        lines.append(f"  [{row['state']:9}] {row['claim']}")
        lines.append(f"      {row['why']}")
    return "\n".join(lines)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="M1 decay clock -- greens expire")
    ap.add_argument("--root", default=".")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sp = sub.add_parser("stamp")
    sp.add_argument("--claim", required=True)
    sp.add_argument("--verifier", required=True)
    sp.add_argument("--oracle", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "stamp":
        result = stamp(args.root, args.claim, args.verifier, args.oracle, args.mode)
        print(json.dumps(result, indent=2) if args.json else
              (f"stamped {result['claim']}" if result["stamped"]
               else f"REFUSED: {result['why']}"))
        return 0 if result["stamped"] else 2

    try:
        report = check(args.root, args.mode)
    except OSError as exc:
        print(f"trust_decay: cannot read spoke -- {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else render(report))
    # An EMPTY population exits 1, not 0. Exit 0 means "the greens here are
    # current", and a spoke with no green claims has not earned that sentence --
    # it has simply never been measured. UNKNOWN is not GREEN is the whole tenet;
    # a decay clock that reported success over an empty set would be the first
    # thing to violate it.
    if not report["rows"]:
        return 1
    return 1 if (report["counts"][AMBER] or report["counts"][UNSTAMPED]) else 0


if __name__ == "__main__":
    sys.exit(_main())
