#!/usr/bin/env python3
"""lug_gate.py — author-time lug validation gate (impl-author-time-lug-gate-v1).

Mechanizes the anti-placeholder / improve-at-creation doctrine: a lug cannot be
written without passing 5 mechanical checks the moment it is authored. This is the
FIRST of two gates that share ONE verify grammar (`_extract_command()`, imported
directly from wai_assurance.py — not reimplemented here): Gate-1 (this tool) checks
a verify[] entry is runnable at authoring time; Gate-4 (wai_assurance.verify_single_lug)
actually executes it later. Same parsing, two moments.

The 5 checks (gate_lug()):
  1. schema              (placeholder-schema)        — PEV/acceptance/file_targets/lenses non-empty
  2. verify-runnability   (mechanical-no-runnable)     — verify_mode:mechanical needs >=1 runnable cmd
  3. reasoned-tiering     (unjustified-model_fit)      — model_fit needs a model_fit_reason
  4. blocked_by-resolution(dangling-or-cyclic-blocker) — every blocker must resolve + no cycles
  5. gate-consistency     (gate-not-encoded)           — prose-named gates must be in blocked_by[]

Any BLOCK-severity finding fails the lug. Findings are also emitted as typed
`verification-finding` rows to the CapabilitiesGraph blocks ledger (capgraph_blocks.py)
so recurring error classes become visible to the hygiene/monitor cadence — never a
crash if that ledger is unavailable (degrades to no-op).

CLI:
  lug_gate.py --lug <path>              gate one lug file
  lug_gate.py --staged                  gate staged lug files (pre-commit entry)
  lug_gate.py --sweep <dir> [--json]    gate every lug under a directory
  lug_gate.py --self-test               run the seed corpus (s137 error-class coverage)
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Path resolution — lug_gate.py lives at WAI-Harness/spoke/managed/tools/,
# 4 parents up is the repo root.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_WAI_ASSURANCE_DIR = os.path.join(_REPO_ROOT, "WAI-Harness", "hub", "local", "scripts")
if _WAI_ASSURANCE_DIR not in sys.path:
    sys.path.insert(0, _WAI_ASSURANCE_DIR)

# ONE verify grammar, two gates — import, never reimplement.
from wai_assurance import _extract_command  # noqa: E402


def _load_capgraph_blocks():
    """Dynamic-import capgraph_blocks.py (same tools/ dir) for emitting typed
    verification-finding rows. Returns None (never raises) if unavailable — the
    finding-emit phase then no-ops, matching capgraph_blocks' own contract."""
    tool = os.path.join(_HERE, "capgraph_blocks.py")
    if not os.path.isfile(tool):
        return None
    try:
        spec = importlib.util.spec_from_file_location("lug_gate_capgraph_blocks", tool)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        return None


def _bytype_dir(root):
    return os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype")


def _spoke_local(root):
    return os.path.join(root, "WAI-Harness", "spoke", "local")


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------

def build_index(bytype_dir):
    """Collect all known lug ids: every bytype/<type>/<status>/*.json, plus
    lugs/WAI-LugIndex.jsonl (one json object per line, id field) if present."""
    ids = set()
    for path in glob.glob(os.path.join(bytype_dir, "*", "*", "*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
            lid = d.get("id")
            if lid:
                ids.add(lid)
        except Exception:
            continue

    lug_index_path = os.path.join(os.path.dirname(os.path.normpath(bytype_dir)), "WAI-LugIndex.jsonl")
    if os.path.isfile(lug_index_path):
        try:
            with open(lug_index_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        lid = d.get("id")
                        if lid:
                            ids.add(lid)
                    except Exception:
                        continue
        except Exception:
            pass
    return ids


def _find_lug_by_id(root, lug_id):
    """Locate a lug on disk by id (used only for the cheap 2-cycle blocked_by check).
    Never raises; returns None if not found or on any read error."""
    try:
        for path in glob.glob(os.path.join(_bytype_dir(root), "*", "*", "*.json")):
            try:
                with open(path) as f:
                    d = json.load(f)
                if d.get("id") == lug_id:
                    return d
            except Exception:
                continue
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# The 5 checks
# ---------------------------------------------------------------------------

# Receipt-shaped types record what ALREADY happened, or are purely informational.
# PEV describes work still to DO, so requiring it of a receipt is a category error
# that can only be satisfied by inventing it — and invented PEV is worse than thin
# (improve-at-creation doctrine, skeptic lens). These are NOT exempt from
# validation: they answer to _check_receipt_schema below, which enforces identity
# plus a substantive body. A receipt with no content still fails.
_RECEIPT_TYPES = {
    "ack", "notice", "report", "signal", "notation",
    "completion", "receipt", "addendum",
    # "upgrade-report" is emitted by harness_upgrade on the spoke that took the
    # cut: a machine's validation result, not a plan. Demanding PEV of it blocked
    # the very first real feed from being archived (2026-07-22) — the work it
    # implies is opened as separate bug/impl lugs by the intake ceremony.
    "upgrade-report", "upgrade_report",
}

# Any one of these, non-empty, satisfies "this receipt actually says something".
_RECEIPT_BODY_FIELDS = ("summary", "one_liner", "notes", "verdict", "title")


def _check_receipt_schema(lug):
    """Identity + substance bar for receipt-shaped lugs.

    Deliberately NOT the PEV bar: a receipt has no work to plan. It must still
    identify itself and carry real content, so this cannot be used as a bypass —
    retyping a work lug to `notice` to dodge PEV would strip it of the execute[]
    that made it a work lug in the first place.
    """
    findings = []
    missing = [k for k in ("id", "type", "title")
               if not isinstance(lug.get(k), str) or not lug.get(k, "").strip()]

    def _nonempty(v):
        if isinstance(v, str):
            return bool(v.strip())
        if isinstance(v, (list, dict)):
            return len(v) > 0
        return False

    has_body = any(_nonempty(lug.get(f)) for f in _RECEIPT_BODY_FIELDS
                   if f != "title")

    if missing:
        findings.append({
            "check": "schema", "error_class": "placeholder-schema", "severity": "block",
            "msg": f"receipt-shaped lug missing/empty identity fields: {', '.join(missing)}",
        })
    if not has_body:
        findings.append({
            "check": "schema", "error_class": "placeholder-schema", "severity": "block",
            "msg": ("receipt-shaped lug has no substantive body — needs at least one of: "
                    f"{', '.join(f for f in _RECEIPT_BODY_FIELDS if f != 'title')}"),
        })

    # Close the only bypass this exemption could open: retyping a work lug to a
    # receipt type to dodge the PEV bar while still carrying the work. A receipt
    # records; it does not plan. If it plans, it is a work lug wearing a receipt's
    # label and must answer to the PEV bar under its real type.
    #
    # `perceive` is deliberately NOT a work field. Observing is exactly what a
    # signal/report/notice DOES — "here is the gap I saw" is the whole point of the
    # type. Only PLANNING marks a work lug: execute[] and acceptance_criteria[].
    # Including perceive here was an over-reach that flagged 10 legitimate
    # signal-conductor-harness-gap lugs whose only sin was recording an observation.
    work_fields = [k for k in ("execute", "acceptance_criteria")
                   if isinstance(lug.get(k), list) and len(lug.get(k)) > 0]
    if work_fields:
        findings.append({
            "check": "schema", "error_class": "receipt-carrying-work", "severity": "block",
            "msg": (f"type '{lug.get('type')}' is receipt-shaped but carries work fields: "
                    f"{', '.join(work_fields)}. A receipt records what happened; it does not "
                    "plan work. Retype to a work type (change/impl/fix/feature/bug/task) and "
                    "meet the full PEV bar, or move the plan out into its own lug."),
        })
    return findings


def _check_schema(lug):
    if lug.get("type") in _RECEIPT_TYPES:
        return _check_receipt_schema(lug)

    findings = []
    missing = []
    wrong_shape = []
    for key in ("perceive", "execute", "verify", "acceptance_criteria", "file_targets"):
        val = lug.get(key)
        if isinstance(val, list) and len(val) > 0:
            continue
        # A substantive string is CONTENT THAT EXISTS in the wrong container. Calling
        # it "missing/empty" is a false statement about the lug, and the gate made it
        # 679 times over on `perceive` alone. Wrong-shape still blocks — the schema is
        # lists — but it is reported as what it is, so the fix is a lossless
        # string -> [string] normalisation rather than an invitation to rewrite prose
        # that was never absent.
        if isinstance(val, str) and val.strip():
            wrong_shape.append(key)
        else:
            missing.append(key)

    lenses = lug.get("_improvement_lenses")
    lens_missing = []
    if not isinstance(lenses, dict):
        lens_missing = ["skeptic", "architect", "naive_reader"]
    else:
        for k in ("skeptic", "architect", "naive_reader"):
            v = lenses.get(k)
            if not isinstance(v, str) or not v.strip():
                lens_missing.append(k)

    if missing or lens_missing:
        parts = []
        if missing:
            parts.append(f"missing/empty fields: {', '.join(missing)}")
        if lens_missing:
            parts.append(f"missing/empty _improvement_lenses: {', '.join(lens_missing)}")
        findings.append({
            "check": "schema", "error_class": "placeholder-schema", "severity": "block",
            "msg": "; ".join(parts),
        })

    # Reported separately from placeholder-schema on purpose: this lug is NOT a
    # placeholder, and conflating the two is what made the backlog look like 150
    # lazy authors instead of one shape mismatch.
    if wrong_shape:
        findings.append({
            "check": "schema", "error_class": "field-shape-string-not-list", "severity": "block",
            "msg": (f"fields present with real content but as a string, not a list: "
                    f"{', '.join(wrong_shape)}. Content is NOT missing — normalise "
                    "string -> [string] (lossless); do not rewrite it."),
        })
    return findings


def _check_verify_runnability(lug):
    findings = []
    if lug.get("verify_mode") == "mechanical":
        verify_items = lug.get("verify") or []
        runnable = any(_extract_command(v) is not None for v in verify_items)
        if not runnable:
            findings.append({
                "check": "verify-runnability", "error_class": "mechanical-no-runnable", "severity": "block",
                "msg": "verify_mode:mechanical requires >=1 runnable `cmd:` verify entry, or set verify_mode:attested",
            })
    return findings


def _check_reasoned_tiering(lug):
    findings = []
    if lug.get("model_fit"):
        # `model_rationale` is the older name for the same field and 37 lugs carry
        # only it (8 carry both, identically). The check exists to ensure the tier
        # was REASONED, not to police which of two synonyms holds the reasoning —
        # failing a lug that states its rationale under the historical key reports
        # a justified choice as unjustified.
        reason = lug.get("model_fit_reason") or lug.get("model_rationale")
        if not isinstance(reason, str) or not reason.strip():
            findings.append({
                "check": "reasoned-tiering", "error_class": "unjustified-model_fit", "severity": "block",
                "msg": "model_fit requires a one-line model_fit_reason justification",
            })
    return findings


def _check_blocked_by(lug, index, root):
    findings = []
    lug_id = lug.get("id")
    blocked_by = lug.get("blocked_by") or []

    # A bare string here iterated CHARACTER BY CHARACTER: one correctly-named
    # blocker was reported as 18 unknown lug ids ("s, p, e, c, -, g, o, a, ..."),
    # and the real blocker was never checked at all. The gate emitted confident
    # nonsense AND silently skipped its own job. Coerce to a single-element list so
    # the resolution check actually runs, then flag the shape.
    _shape_finding = None
    if isinstance(blocked_by, str):
        _shape_finding = {
            "check": "blocked_by-resolution", "error_class": "field-shape-string-not-list",
            "severity": "block",
            "msg": (f"blocked_by is a bare string ({blocked_by!r}), not a list. Normalise "
                    "string -> [string]; it is checked as a single id below."),
        }
        blocked_by = [blocked_by]
    if _shape_finding:
        findings.append(_shape_finding)

    dangling = [b for b in blocked_by if b not in index]
    if dangling:
        findings.append({
            "check": "blocked_by-resolution", "error_class": "dangling-or-cyclic-blocker", "severity": "block",
            "msg": f"blocked_by references unknown lug id(s): {', '.join(dangling)}",
        })

    if lug_id and lug_id in blocked_by:
        findings.append({
            "check": "blocked_by-resolution", "error_class": "dangling-or-cyclic-blocker", "severity": "block",
            "msg": f"blocked_by contains its own id ({lug_id}) — self-cycle",
        })
    else:
        for b in blocked_by:
            if b in index and b != lug_id:
                other = _find_lug_by_id(root, b)
                if other and lug_id and lug_id in (other.get("blocked_by") or []):
                    findings.append({
                        "check": "blocked_by-resolution", "error_class": "dangling-or-cyclic-blocker",
                        "severity": "block",
                        "msg": f"2-cycle: {lug_id} blocked_by {b} and {b} blocked_by {lug_id}",
                    })
    return findings


# gate phrases: "blocked_by <id>" / "blocked_by: <id>" / "gated by <id>" / "gate: <id>"
_ID_SHAPE = r'[a-z0-9][a-z0-9-]+-v\d+|[a-z][a-z-]+'
_GATE_PATTERNS = [
    re.compile(r'\bblocked_by:?\s+(' + _ID_SHAPE + r')'),
    re.compile(r'\bgated by\s+(' + _ID_SHAPE + r')'),
    re.compile(r'\bgate:\s+(' + _ID_SHAPE + r')'),
]


def _check_gate_consistency(lug, index):
    # A prose token is only treated as a gate reference if it is a REAL lug id
    # (present in `index`). This is the discriminator that stops English words
    # like "resolution" in "blocked_by resolution" (feature prose) from being
    # mistaken for an un-encoded gate — only an actual lug named in prose but
    # absent from blocked_by[] is the true "gate-not-encoded" error class.
    findings = []
    prose = " ".join([
        lug.get("summary") or "",
        lug.get("one_liner") or "",
        " ".join(lug.get("execute") or []),
    ])
    blocked_by = set(lug.get("blocked_by") or [])
    referenced = set()
    for pat in _GATE_PATTERNS:
        for m in pat.finditer(prose):
            gid = m.group(1)
            if gid in index and gid != lug.get("id"):
                referenced.add(gid)
    missing = sorted(referenced - blocked_by)
    for gid in missing:
        findings.append({
            "check": "gate-consistency", "error_class": "gate-not-encoded", "severity": "block",
            "msg": f"gate {gid} named in prose but not encoded in blocked_by[]",
        })
    return findings


def gate_lug(lug_dict, index, root):
    """Run all 5 checks. Empty list == PASS."""
    findings = []
    findings += _check_schema(lug_dict)
    findings += _check_verify_runnability(lug_dict)
    findings += _check_reasoned_tiering(lug_dict)
    findings += _check_blocked_by(lug_dict, index, root)
    findings += _check_gate_consistency(lug_dict, index)
    return findings


# ---------------------------------------------------------------------------
# Finding emission (capgraph blocks ledger)
# ---------------------------------------------------------------------------

def _emit_findings(lug, findings, root):
    """Emit one verification-finding row per BLOCK finding. Never crashes the gate."""
    try:
        cb = _load_capgraph_blocks()
        if cb is None:
            return
        lug_id = lug.get("id", "unknown")
        spoke_local = _spoke_local(root)
        for f in findings:
            if f.get("severity") != "block":
                continue
            payload = {
                "error_class": f.get("error_class"),
                "caught_by": "creation-gate",
                "author_context": lug.get("authored_by", "unknown"),
                "artifact": lug_id,
                "tier": "creation-gate",
            }
            try:
                cb.record_event(kind="verification-finding", subject=lug_id, payload=payload, spoke_local=spoke_local)
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Verification-signal ledger: dogfood KPI + pattern -> enhancement loop
# ---------------------------------------------------------------------------

# Channels that count as "caught LATE" (after authoring) — the denominator the
# dogfood ratio must invert against. creation-gate is the "caught at creation"
# numerator. These names match the payload caught_by vocabulary.
_LATE_CHANNELS = {"assurance", "convened", "operator"}


def _read_findings(root):
    """All verification-finding rows from the spoke-local capgraph blocks log."""
    path = os.path.join(_spoke_local(root), "capabilitygraph", "blocks.jsonl")
    rows = []
    if not os.path.isfile(path):
        return rows
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("kind") == "verification-finding":
                    rows.append(d)
    except Exception:
        pass
    return rows


def _detect_patterns(rows, threshold=3):
    """error_class -> count for any class recurring >= threshold times. A pattern
    hit is the signal that feeds enhancement planning (the improvement loop)."""
    from collections import Counter
    c = Counter(r.get("error_class") for r in rows if r.get("error_class"))
    return {ec: n for ec, n in c.items() if n >= threshold}


def cmd_dogfood_kpi(root, threshold, emit, as_json):
    """Compute the dogfood ratio FROM the verification-finding ledger (never
    hand-tallied): errors caught AT creation vs LATE. KPI target = inverted
    (creation >= late). Flags recurring error-classes as PATTERNS and derives
    enhancement-planning candidates; with --emit, appends them to the local
    enhancement-candidates ledger (the improvement loop's intake)."""
    rows = _read_findings(root)
    creation = sum(1 for r in rows if r.get("caught_by") == "creation-gate")
    late = sum(1 for r in rows if r.get("caught_by") in _LATE_CHANNELS)
    patterns = _detect_patterns(rows, threshold)
    candidates = [
        {"error_class": ec, "occurrences": n,
         "recommendation": (f"recurring '{ec}' ({n}x >= {threshold}) — candidate for a "
                            f"targeted enhancement (tighten the author-time check or its guidance).")}
        for ec, n in sorted(patterns.items(), key=lambda kv: -kv[1])
    ]
    inverted = creation >= late
    result = {
        "total_findings": len(rows),
        "caught_at_creation": creation,
        "caught_late": late,
        "ratio_creation_over_late": (round(creation / late, 2) if late else None),
        "inverted": inverted,
        "pattern_threshold": threshold,
        "patterns": patterns,
        "enhancement_candidates": candidates,
    }
    if emit and candidates:
        cand_path = os.path.join(_spoke_local(root), "capabilitygraph", "enhancement-candidates.jsonl")
        try:
            os.makedirs(os.path.dirname(cand_path), exist_ok=True)
            with open(cand_path, "a") as f:
                for cand in candidates:
                    f.write(json.dumps({"kind": "enhancement-candidate", "source": "dogfood-kpi", **cand}) + "\n")
            result["emitted_to"] = cand_path
        except Exception as e:
            result["emit_error"] = str(e)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        r = result["ratio_creation_over_late"]
        print(f"dogfood KPI: caught_at_creation={creation}  caught_late={late}  "
              f"ratio={r if r is not None else 'inf'}  inverted={'YES' if inverted else 'NO'}")
        print(f"  patterns (>= {threshold}): {patterns or 'none'}")
        for c in candidates:
            print(f"  ENHANCEMENT CANDIDATE: {c['error_class']} x{c['occurrences']}")
    return 0 if inverted else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_json(path):
    with open(path) as f:
        return json.load(f)


def cmd_lug(lug_path, root):
    try:
        lug = _load_json(lug_path)
    except Exception as e:
        print(json.dumps({
            "lug": lug_path, "verdict": "FAIL",
            "findings": [{"check": "load", "error_class": "unparseable-json", "severity": "block", "msg": str(e)}],
        }, indent=2))
        return 1

    index = build_index(_bytype_dir(root))
    findings = gate_lug(lug, index, root)
    verdict = "FAIL" if any(f["severity"] == "block" for f in findings) else "PASS"
    lug_id = lug.get("id", os.path.basename(lug_path))
    print(json.dumps({"lug": lug_id, "verdict": verdict, "findings": findings}, indent=2))
    if verdict == "FAIL":
        _emit_findings(lug, findings, root)
    return 0 if verdict == "PASS" else 1


def _blockers_at_head(rel, root, index):
    """Blocker count for this lug as it exists at HEAD, or None if it is new.

    None means "no prior state to ratchet against" => the caller applies the full
    author-time bar. FAIL-CLOSED: any git error, unreadable blob, or unparseable
    prior returns None, so an unverifiable history can never soften the gate.
    """
    try:
        p = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=root,
                           capture_output=True, text=True, timeout=15)
        if p.returncode != 0 or not (p.stdout or "").strip():
            return None                      # new file at HEAD => full bar
        prior = json.loads(p.stdout)
    except Exception:
        return None                          # unverifiable => full bar
    try:
        return len([f for f in gate_lug(prior, index, root) if f["severity"] == "block"])
    except Exception:
        return None


def cmd_staged(root):
    try:
        p = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root,
                            capture_output=True, text=True, timeout=30)
        out = p.stdout or ""
    except Exception as e:
        print(f"lug_gate --staged: could not read staged files ({e}) — skipping gate.", file=sys.stderr)
        return 0

    paths = [l.strip() for l in out.splitlines() if l.strip()]
    pattern = re.compile(r'lugs/bytype/.*\.json$')
    targets = [p for p in paths if pattern.search(p)]

    index = build_index(_bytype_dir(root))
    failed = []
    improved = []
    for rel in targets:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        try:
            lug = _load_json(full)
        except Exception as e:
            failed.append((rel, [{"check": "load", "error_class": "unparseable-json", "severity": "block", "msg": str(e)}]))
            continue
        findings = gate_lug(lug, index, root)
        blockers = [f for f in findings if f["severity"] == "block"]
        if not blockers:
            continue

        # RATCHET (the backlog's real blocker). Author-time full bar applies to a
        # lug that is NEW here. For a lug that ALREADY EXISTS at HEAD in a failing
        # state, demanding perfection to accept an IMPROVEMENT is what froze ~150
        # legacy lugs: the only moves were "perfect it now" or "throw the
        # improvement away", so nobody improved anything and the backlog outlived
        # every attempt — while a dirty tree blocked the fleet from receiving canon.
        #
        # So: never worse. A pre-existing lug commits if its blocker count did not
        # INCREASE. This is not a weakening — it is monotone. New lugs still face
        # the full bar (prior=None => any blocker fails), and a regression on any
        # lug still fails. Quality can only ratchet up.
        prior = _blockers_at_head(rel, root, index)
        if prior is not None and len(blockers) <= prior:
            improved.append((rel, prior, len(blockers)))
            continue
        failed.append((rel, blockers))

    if failed:
        print("lug_gate --staged: FAIL — the following staged lugs are non-compliant:")
        for rel, blockers in failed:
            print(f"  {rel}:")
            for b in blockers:
                print(f"    [{b['error_class']}] {b['msg']}")
        return 1

    if improved:
        print(f"lug_gate --staged: {len(improved)} pre-existing lug(s) still non-compliant but NOT WORSE "
              f"(ratchet — allowed, must not regress):")
        for rel, prior, now in improved[:10]:
            trend = "improved" if now < prior else "unchanged"
            print(f"    {os.path.basename(rel)}: {prior} -> {now} blocker(s) [{trend}]")
        if len(improved) > 10:
            print(f"    ... and {len(improved)-10} more")
    print(f"lug_gate --staged: PASS ({len(targets)} staged lug(s) checked)")
    return 0


def cmd_sweep(sweep_dir, root, as_json, initiative=None):
    lug_paths = glob.glob(os.path.join(sweep_dir, "**", "*.json"), recursive=True)
    index = build_index(_bytype_dir(root))

    total = 0
    compliant = 0
    noncompliant = []
    mech_without_runnable = 0

    for path in lug_paths:
        try:
            lug = _load_json(path)
        except Exception:
            continue
        # scope filter: when --initiative is given, only gate lugs in that initiative
        if initiative is not None and lug.get("initiative_id") != initiative:
            continue
        total += 1
        findings = gate_lug(lug, index, root)
        blockers = [f for f in findings if f["severity"] == "block"]
        if any(f["error_class"] == "mechanical-no-runnable" for f in blockers):
            mech_without_runnable += 1
        if blockers:
            noncompliant.append({"lug": lug.get("id", path), "path": path, "findings": blockers})
        else:
            compliant += 1

    if as_json:
        print(json.dumps({
            "total": total,
            "compliant": compliant,
            "noncompliant": noncompliant,
            "mechanical_without_runnable": mech_without_runnable,
        }, indent=2))
    else:
        print(f"lug_gate --sweep {sweep_dir}")
        print(f"  total: {total}  compliant: {compliant}  noncompliant: {len(noncompliant)}")
        print(f"  mechanical-mode lugs without runnable commands: {mech_without_runnable}")
        for nc in noncompliant:
            print(f"  - {nc['lug']} ({nc['path']}):")
            for f in nc["findings"]:
                print(f"      [{f['error_class']}] {f['msg']}")

    return 0 if len(noncompliant) == 0 else 1


# ---------------------------------------------------------------------------
# --self-test — seed corpus (s137 error-class coverage)
# ---------------------------------------------------------------------------

def _self_test():
    base_lens = {"skeptic": "resolved.", "architect": "resolved.", "naive_reader": "resolved."}
    base_fields = dict(
        perceive=["p1"], execute=["e1"], verify=["cmd: python3 -m py_compile foo.py"],
        acceptance_criteria=["a1"], file_targets=["f1.py"],
        _improvement_lenses=dict(base_lens),
    )

    cases = []

    # 1. mechanical-no-runnable
    lug1 = {**base_fields, "id": "case-mech-no-runnable-v1", "verify_mode": "mechanical",
            "verify": ["This is prose describing intent with no runnable command in it."]}
    cases.append(("mechanical-no-runnable", lug1, set(), "mechanical-no-runnable"))

    # 2. unjustified-model_fit
    lug2 = {**base_fields, "id": "case-model-fit-v1", "model_fit": "opus"}
    cases.append(("unjustified-model_fit", lug2, set(), "unjustified-model_fit"))

    # 3. gate-not-encoded
    lug3 = {**base_fields, "id": "case-gate-not-encoded-v1",
            "summary": "This work is blocked_by cut-gate-v1 and must wait for it.",
            "blocked_by": []}
    cases.append(("gate-not-encoded", lug3, {"cut-gate-v1"}, "gate-not-encoded"))

    # 4. placeholder-schema
    lug4 = {"id": "case-placeholder-v1", "perceive": [], "execute": [], "verify": [],
            "acceptance_criteria": [], "file_targets": [], "_improvement_lenses": {}}
    cases.append(("placeholder-schema", lug4, set(), "placeholder-schema"))

    # 5. dangling-blocker
    lug5 = {**base_fields, "id": "case-dangling-v1", "blocked_by": ["does-not-exist-v1"]}
    cases.append(("dangling-blocker", lug5, set(), "dangling-or-cyclic-blocker"))

    # 6. compliant — expect PASS (zero findings)
    lug6 = {**base_fields, "id": "case-compliant-v1", "verify_mode": "mechanical",
            "model_fit": "sonnet", "model_fit_reason": "routine mechanical work, no deep judgment needed.",
            "blocked_by": ["known-dep-v1"]}
    cases.append(("compliant", lug6, {"known-dep-v1"}, None))

    # 7. prose-word-not-a-gate (false-positive guard): prose contains "blocked_by
    #    resolution" but "resolution" is not a real lug id -> must NOT flag.
    lug7 = {**base_fields, "id": "case-prose-word-v1", "verify_mode": "mechanical",
            "model_fit": "sonnet", "model_fit_reason": "mechanical.",
            "summary": "Implements blocked_by resolution + acyclicity against the live index.",
            "blocked_by": ["known-dep-v1"]}
    cases.append(("prose-word-not-a-gate", lug7, {"known-dep-v1"}, None))

    all_ok = True
    rows = []
    for name, lug, index, expect_class in cases:
        findings = gate_lug(lug, index, _REPO_ROOT)
        blockers = [f for f in findings if f["severity"] == "block"]
        if expect_class is None:
            ok = len(blockers) == 0
            expected = "PASS"
            actual = "PASS" if ok else "FAIL " + str([b["error_class"] for b in blockers])
        else:
            ok = any(b["error_class"] == expect_class for b in blockers)
            expected = f"BLOCK[{expect_class}]"
            actual = ("BLOCK" + str([b["error_class"] for b in blockers])) if blockers else "PASS (unexpected)"
        all_ok = all_ok and ok
        rows.append((name, expected, actual, "OK" if ok else "MISMATCH"))

    # pattern-monitor self-check: 3 synthetic findings of one class -> flagged as PATTERN
    synthetic = [{"error_class": "synthetic-recurring", "caught_by": "creation-gate"} for _ in range(3)]
    pattern_ok = "synthetic-recurring" in _detect_patterns(synthetic, threshold=3)
    all_ok = all_ok and pattern_ok
    rows.append(("pattern-monitor-3-same-class", "PATTERN[synthetic-recurring]",
                 "PATTERN" if pattern_ok else "MISSED (unexpected)", "OK" if pattern_ok else "MISMATCH"))

    print(f"{'case':28} {'expected':26} {'actual':40} result")
    print("-" * 100)
    for name, expected, actual, res in rows:
        print(f"{name:28} {expected:26} {actual:40} {res}")

    print()
    print("HONESTY NOTE — s137 error classes NOT mechanically catchable by a creation gate:")
    print("  post-cert-drift-T5        -> certification gate (fires post-authoring, on re-cert pass)")
    print("  premature-claim           -> lease gate (needs runtime claim/lease state, not lug content)")
    print("  overstated-commit-message -> commit-msg gate (needs the commit message, not the lug body)")
    print("  dormant-advisor-design    -> design review (needs human/LLM judgment of intent, not schema)")
    print()
    verdict = "PASS" if all_ok else "FAIL"
    print(f"--self-test: {verdict}")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="lug_gate — author-time lug validation gate")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--lug", metavar="PATH", help="gate a single lug JSON file")
    g.add_argument("--staged", action="store_true", help="gate staged lug files (git diff --cached) — pre-commit entry")
    g.add_argument("--sweep", metavar="DIR", help="gate every lug under DIR (recursively)")
    g.add_argument("--self-test", action="store_true", help="run the seed corpus")
    g.add_argument("--dogfood-kpi", action="store_true",
                   help="compute the caught-at-creation vs caught-late ratio from the verification-finding ledger + flag patterns")
    parser.add_argument("--json", action="store_true", help="with --sweep/--dogfood-kpi, print a JSON summary")
    parser.add_argument("--initiative", metavar="ID", default=None,
                        help="with --sweep, only gate lugs whose initiative_id == ID")
    parser.add_argument("--threshold", type=int, default=3,
                        help="with --dogfood-kpi, min occurrences for an error_class to be a PATTERN (default 3)")
    parser.add_argument("--emit", action="store_true",
                        help="with --dogfood-kpi, append enhancement-planning candidates to the local ledger")
    args = parser.parse_args(argv)

    root = _REPO_ROOT

    if args.self_test:
        return _self_test()
    if args.dogfood_kpi:
        return cmd_dogfood_kpi(root, args.threshold, args.emit, args.json)
    if args.lug:
        return cmd_lug(args.lug, root)
    if args.staged:
        return cmd_staged(root)
    if args.sweep:
        return cmd_sweep(args.sweep, root, args.json, args.initiative)
    return 2


if __name__ == "__main__":
    sys.exit(main())
