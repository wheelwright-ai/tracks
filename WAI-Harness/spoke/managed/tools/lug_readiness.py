#!/usr/bin/env python3
"""lug_readiness.py — the backlog reclassifier ("Lug B").

Conductor's health gate refuses to spend cycles when every spoke reads spin/not_ready,
and prints "reclassify backlog (Lug B) first" — but no such tool existed. This is it.

THE READY-TO-WORK CONTRACT (canonical, mirrors spoke_health_check.classify_lug):
  a lug is `auto_build` (drainable by autopilot NOW) iff it has, all three:
    - non-empty acceptance_criteria
    - non-empty file_targets       (the edit surface the dispatched agent acts on)
    - execute OR perceive          (the plan)
  else it is `review` — counted by the expediter but it WILL NOT execute (spin).

Why a backlog rolls IDLE despite a big "dispatchable" count (measured s135: 23/739 = 3%
ready across the core fleet): 672 lugs carry NO file_targets, 292 are advisory artifacts
(crew-recommend/advisor-scout/coverage-eval — not feature work), 228 lack AC. The
expediter counts them; the engine skips them; the wave spins.

WHAT THIS TOOL DOES — deterministic moves only (no guessing):
  audit     tally auto_build / review / needs_you / blocked across spoke(s), with the
            why-not-ready breakdown. Read-only. (the repeatable version of the s135 probe)
  plan      per-lug promotability verdict for one spoke: mech_promote | needs_ac |
            needs_authoring | advisory_retire | already_ready. Read-only.
  promote   mechanical promotion of ONE lug: lift files_to_edit/files_to_create ->
            file_targets, v4ize stale WAI-Spoke/ paths. Flips review->auto_build ONLY if
            the result satisfies the contract; otherwise reports exactly what authoring is
            still missing and changes nothing. --write to persist.
  retire    mark an advisory artifact reclassified (disposition=reclassified_advisory)
            so it stops inflating the dispatchable count. --write to persist.
  groom     Phase-0.5 authoring-completeness gate for impl lugs at creation/intake time:
            fails (exit 1) any impl lug missing file_targets/effort_score/verify. Point it
            at one lug file or a directory (e.g. incoming/). --flag-only reports without
            failing the exit code (refine-lug-authoring-completeness-v1).

What this tool deliberately does NOT do: invent file_targets or acceptance_criteria. The
380 "truly no targets" lugs need a real authoring pass (human, or an LLM enrichment run) —
promote() flags them needs_authoring and leaves them untouched. Honesty over false-ready.

Cross-spoke note: a spoke does not edit another spoke's lugs directly. Run this inside the
owning spoke (or have Basher/Herald dispatch it per spoke). audit/plan are read-only and
safe to run fleet-wide from the hub.
"""
from __future__ import annotations
import argparse, glob, json, os, re, sys
from datetime import datetime, timezone

ADVISORY = re.compile(r"^(crew-recommend|advisor-scout|scout-refine|scout-|coverage-eval|needs-you)")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def file_targets(d):
    """Canonical edit-surface, tolerant of the legacy field split."""
    ft = d.get("file_targets") or []
    if ft:
        return list(ft)
    merged = (d.get("files_to_edit") or []) + (d.get("files_to_create") or [])
    return [x for x in merged if x]


def classify_lug(d):
    """Canonical — kept in lockstep with spoke_health_check.classify_lug, but reads the
    edit surface through file_targets() so a lug whose targets sit under the legacy
    files_to_edit/files_to_create names is judged on substance, not field naming."""
    t = (d.get("type") or "").lower(); title = (d.get("title") or "").lower()
    if d.get("disposition") in ("auto_build", "needs_you", "review", "blocked", "reclassified_advisory"):
        return "review" if d["disposition"] == "reclassified_advisory" else d["disposition"]
    if d.get("needs_attention") or d.get("needs_you") or t == "decision" or d.get("decision_question") \
       or any(k in title for k in ("operator", "approve", " decide")):
        return "needs_you"
    if d.get("blocked_by"):
        return "blocked"
    if (d.get("acceptance_criteria") or []) and file_targets(d) and (d.get("execute") or d.get("perceive")):
        return "auto_build"
    return "review"


def _is_advisory(d, lid=None):
    lid = (lid or d.get("id") or "").lower()
    return bool(ADVISORY.match(lid))


GROOM_TYPES = ("implementation", "impl")


def groom_gate(d, lid=None):
    """Phase-0.5 authoring-completeness gate (refine-lug-authoring-completeness-v1).

    Narrower than classify_lug: only impl-type lugs are gated (advisory/task/spec/
    etc. lugs have different authoring shapes and are out of scope), and it checks
    the specific triad the backlog-not-ready-to-work finding named -- file_targets,
    effort_score, verify -- rather than classify_lug's broader auto_build test.
    Returns {"ok": bool, "missing": [...]} -- missing is empty when ok is True.
    Non-impl lugs always pass (nothing to gate)."""
    t = (d.get("type") or "").lower()
    if t not in GROOM_TYPES:
        return {"ok": True, "missing": []}
    if _is_advisory(d, lid):
        return {"ok": True, "missing": []}
    missing = []
    if not file_targets(d):
        missing.append("file_targets")
    if d.get("effort_score") is None:
        missing.append("effort_score")
    if not (d.get("verify") or d.get("acceptance_criteria")):
        missing.append("verify")
    return {"ok": not missing, "missing": missing}


def v4ize(d):
    """Rewrite stale v3 WAI-Spoke/ instruction paths -> v4 (canonical, mirrors
    ozi_autopilot._v4ize_lug). Returns (new_dict, changed)."""
    def fix(s):
        if not isinstance(s, str):
            return s
        return (s.replace("WAI-Spoke/advisors", "WAI-Harness/spoke/advisors")
                 .replace("WAI-Spoke/lugs", "WAI-Harness/spoke/local/lugs")
                 .replace("WAI-Spoke/", "WAI-Harness/spoke/local/"))
    def walk(v):
        if isinstance(v, str): return fix(v)
        if isinstance(v, list): return [walk(x) for x in v]
        if isinstance(v, dict): return {k: walk(x) for k, x in v.items()}
        return v
    new = walk(d)
    return new, (json.dumps(new, sort_keys=True) != json.dumps(d, sort_keys=True))


def promotability(d, lid=None):
    """Deterministic verdict on how (or whether) a review lug can be moved to auto_build."""
    cls = classify_lug(d)
    if cls == "auto_build":
        return "already_ready"
    if cls in ("needs_you", "blocked"):
        return cls
    if _is_advisory(d, lid):
        return "advisory_retire"
    has_targets = bool(file_targets(d))
    legacy_only = has_targets and not (d.get("file_targets") or [])
    has_ac = bool(d.get("acceptance_criteria") or [])
    has_pev = bool(d.get("execute") or d.get("perceive"))
    if not has_targets:
        return "needs_authoring"            # no edit surface under any name -> human/LLM
    if legacy_only and has_ac and has_pev:
        return "mech_promote"               # targets present, just normalize the field
    if legacy_only and has_pev and not has_ac:
        return "needs_ac"                   # targets present, AC missing
    return "needs_authoring"


def promote(d, lid=None):
    """Mechanical promotion. Returns (new_dict, became_auto_build, missing[])."""
    new = dict(d)
    ft = file_targets(new)
    if ft:
        new["file_targets"] = ft            # normalize legacy split -> canonical field
    new, _ = v4ize(new)
    missing = []
    if not (new.get("acceptance_criteria") or []):
        missing.append("acceptance_criteria")
    if not file_targets(new):
        missing.append("file_targets")
    if not (new.get("execute") or new.get("perceive")):
        missing.append("execute|perceive")
    became = classify_lug(new) == "auto_build"
    if became:
        new["disposition"] = "auto_build"
        new["status"] = new.get("status") if new.get("status") in ("open", "in_progress") else "open"
        new["updated_at"] = now_iso()
        new.setdefault("readiness_history", []).append(
            {"ts": now_iso(), "action": "mech_promote", "by": "lug_readiness"})
    return new, became, missing


def retire(d):
    new = dict(d)
    new["disposition"] = "reclassified_advisory"
    new["updated_at"] = now_iso()
    new.setdefault("readiness_history", []).append(
        {"ts": now_iso(), "action": "retire_advisory", "by": "lug_readiness"})
    return new


# ── lug discovery ───────────────────────────────────────────────────────────
def lug_files(root):
    out = []
    for base in (root + "/WAI-Harness/spoke/local/lugs/bytype", root + "/WAI-Spoke/lugs/bytype"):
        out += glob.glob(base + "/*/open/*.json") + glob.glob(base + "/*/in_progress/*.json")
    return out


def _load(f):
    try:
        return json.load(open(f))
    except Exception:
        return None


# ── triage (the needs_authoring tail: retire stale/dead vs enrich live) ───────
STALE_DAYS = 30


def _open_initiative_ids(root):
    ids = set()
    for p in (root + "/WAI-Harness/spoke/local/initiatives/index.json",
              root + "/WAI-Spoke/initiatives/index.json"):
        d = _load(p)
        if not isinstance(d, dict):
            continue
        for it in d.get("initiatives", []) or []:
            if isinstance(it, dict) and it.get("status") not in ("done", "closed", "abandoned"):
                ids.add(it.get("id"))
    return ids


def _age_days(d):
    iso = d.get("updated_at") or d.get("created_at")
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


def triage_authoring(d, open_inits):
    """For a needs_authoring lug, route it — but NEVER auto-drop on age (operator
    directive s135: 'old' != irrelevant). Two routes:
      enrich_candidate  maps to a live initiative, or recently touched -> author now.
      review_candidate  stale + not initiative-mapped -> a HUMAN/LLM relevance review
                        decides keep-and-enrich vs retire. Age only flags it FOR review;
                        it is never a retirement verdict on its own."""
    iid = d.get("initiative_id") or d.get("initiative")
    mapped = bool(iid and iid in open_inits)
    age = _age_days(d)
    stale = (age is not None and age > STALE_DAYS)
    if mapped:
        return "enrich_candidate"          # tied to live work -> worth authoring
    if stale or age is None:
        return "review_candidate"          # orphaned + cold -> REVIEW for relevance, not auto-drop
    return "enrich_candidate"              # recent, unmapped -> keep for now


# ── completed-lug verification (the one-time AP hygiene pre-filter) ────────────
_CODE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".json", ".md", ".yaml", ".yml", ".jsonl", ".toml", ".css", ".html")
_GLOB_CHARS = set("*?[]")


def _has_evidence(d):
    vt = d.get("verification_test")
    if isinstance(vt, list) and any(isinstance(t, dict) and t.get("result") is not None for t in vt):
        return True
    return bool(d.get("test_result_history"))


def _resolve_target(root, t):
    t = str(t)
    if t.startswith("WAI-Spoke/"):
        t = t.replace("WAI-Spoke/", "WAI-Harness/spoke/local/", 1)
    return os.path.join(root, t)


def verify_completed_signal(d, root):
    """Deterministic pre-filter for a COMPLETED lug — narrows the agent-verification
    campaign. Completion != verification: most legacy completed lugs carry no
    verification_test (the field is newer), so absence of evidence is informational,
    NOT proof of a false-complete. The SHARP signal is a named code/file target that is
    absent on disk. Returns one of:
      absent_target   names a non-glob code file_target that does NOT exist -> AGENT VERIFY
      no_evidence     has code targets that exist but no recorded test run -> low-priority audit
      behavioral      no file targets -> can only be judged behaviorally (agent, if campaign is full)
      ok              targets present AND execution evidence recorded
    Glob targets (*?[]) and pure-deletion lugs are NOT flagged absent (absence may be success)."""
    fts = [t for t in file_targets(d) if str(t).endswith(_CODE_EXT)]
    title = (d.get("title") or "").lower()
    is_deletion = any(w in title for w in ("cleanup", "delete", "remove", "retire", "archive", "prune"))
    if not fts:
        return "behavioral"
    checkable = [t for t in fts if not (set(str(t)) & _GLOB_CHARS)]
    absent = [t for t in checkable if not os.path.exists(_resolve_target(root, t))]
    if absent and not is_deletion:
        return "absent_target"
    if not _has_evidence(d):
        return "no_evidence"
    return "ok"


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_audit(args):
    from collections import Counter, defaultdict
    spokes = _resolve_spokes(args)
    grand = Counter(); why = Counter(); per = defaultdict(Counter); adv = 0
    for name, root in spokes.items():
        for f in lug_files(root):
            d = _load(f)
            if d is None: continue
            cls = classify_lug(d); grand[cls] += 1; per[name][cls] += 1
            lid = (d.get("id") or os.path.basename(f))
            if _is_advisory(d, lid): adv += 1
            if cls == "review":
                if not file_targets(d): why["no_file_targets"] += 1
                if not (d.get("acceptance_criteria") or []): why["no_acceptance_criteria"] += 1
                if "WAI-Spoke/" in json.dumps(d): why["v3_path_rot"] += 1
                if _is_advisory(d, lid): why["advisory_artifact"] += 1
    tot = sum(grand[k] for k in ("auto_build", "review", "needs_you", "blocked"))
    rep = {"total": tot, "auto_build": grand["auto_build"], "review": grand["review"],
           "needs_you": grand["needs_you"], "blocked": grand["blocked"],
           "advisory_artifacts": adv, "why_review": dict(why),
           "per_spoke": {n: dict(c) for n, c in per.items()}}
    if args.json:
        print(json.dumps(rep, indent=2)); return
    print(f"=== READY-TO-WORK AUDIT (open + in_progress) — {len(spokes)} spoke(s) ===")
    print(f"TOTAL: {tot}")
    for k in ("auto_build", "review", "needs_you", "blocked"):
        print(f"  {k:11}: {grand[k]:4}  ({100*grand[k]//max(tot,1)}%)")
    print(f"  advisory artifacts: {adv}")
    print("WHY review (overlapping):")
    for k, v in why.most_common():
        print(f"  {k:22}: {v}")


def cmd_groom(args):
    """Gate a single lug file, or every lug under a directory, through groom_gate.
    Exit 1 if any impl lug fails (missing file_targets/effort_score/verify) --
    designed to be called at lug creation/intake time, not just periodic audit."""
    targets = [args.target] if os.path.isfile(args.target) else lug_files(args.target)
    failures = []
    for f in targets:
        d = _load(f)
        if d is None:
            continue
        lid = d.get("id") or os.path.basename(f)
        res = groom_gate(d, lid)
        if not res["ok"]:
            failures.append({"id": lid, "path": f, "missing": res["missing"]})
    if args.json:
        print(json.dumps({"ok": not failures, "failures": failures}, indent=2))
    else:
        if failures:
            print(f"groom: {len(failures)} impl lug(s) fail authoring-completeness")
            for r in failures:
                print(f"  FAIL: {r['id']} — missing {', '.join(r['missing'])} ({r['path']})")
        else:
            print("groom: clean")
    if failures and not args.flag_only:
        sys.exit(1)


def cmd_plan(args):
    from collections import Counter
    root = args.root
    tally = Counter(); rows = []
    for f in lug_files(root):
        d = _load(f)
        if d is None: continue
        if classify_lug(d) != "review":
            continue
        lid = d.get("id") or os.path.basename(f)
        v = promotability(d, lid); tally[v] += 1
        rows.append((v, lid, f))
    if args.json:
        print(json.dumps({"summary": dict(tally),
                          "lugs": [{"verdict": v, "id": l, "path": p} for v, l, p in rows]}, indent=2))
        return
    print(f"=== PLAN: {root} — {sum(tally.values())} review lug(s) ===")
    for k, v in tally.most_common():
        print(f"  {k:18}: {v}")
    if args.show:
        for v, l, _ in sorted(rows):
            print(f"    [{v}] {l}")


def cmd_triage(args):
    from collections import Counter
    spokes = _resolve_spokes(args)
    tally = Counter(); rows = []
    for name, root in spokes.items():
        open_inits = _open_initiative_ids(root)
        for f in lug_files(root):
            d = _load(f)
            if d is None:
                continue
            lid = d.get("id") or os.path.basename(f)
            if classify_lug(d) != "review":
                continue
            if promotability(d, lid) != "needs_authoring":
                continue
            v = triage_authoring(d, open_inits); tally[v] += 1
            rows.append((v, name, lid, f))
    if args.json:
        print(json.dumps({"summary": dict(tally),
                          "lugs": [{"verdict": v, "spoke": s, "id": l, "path": p} for v, s, l, p in rows]}, indent=2))
        return
    print(f"=== TRIAGE of needs_authoring tail — {len(spokes)} spoke(s), stale>{STALE_DAYS}d ===")
    print(f"  total needs_authoring: {sum(tally.values())}")
    for k, v in tally.most_common():
        print(f"  {k:18}: {v}")
    if args.show:
        for v, s, l, _ in sorted(rows):
            print(f"    [{v}] {s}: {l}")


def completed_files(root):
    out = []
    for base in (root + "/WAI-Harness/spoke/local/lugs/bytype", root + "/WAI-Spoke/lugs/bytype"):
        out += glob.glob(base + "/*/completed/*.json")
    return out


def cmd_verify_completed(args):
    """One-time AP-hygiene pre-filter: scan completed lugs and bucket them by verification
    signal. The `absent_target` bucket is the agent-verification work-list (claimed-but-
    absent files); `behavioral` needs an agent only on a full campaign; `ok`/`no_evidence`
    are low/zero priority. Read-only — produces the campaign queue, does not reopen."""
    from collections import Counter
    spokes = _resolve_spokes(args)
    tally = Counter(); rows = []
    for name, root in spokes.items():
        for f in completed_files(root):
            d = _load(f)
            if d is None:
                continue
            sig = verify_completed_signal(d, root); tally[sig] += 1
            if sig in ("absent_target",) or (args.all and sig == "behavioral"):
                rows.append({"spoke": name, "id": d.get("id") or os.path.basename(f),
                             "signal": sig, "title": (d.get("title") or "")[:80], "path": f})
    if args.json:
        print(json.dumps({"summary": dict(tally), "work_list": rows}, indent=2)); return
    print(f"=== COMPLETED-LUG VERIFICATION pre-filter — {len(spokes)} spoke(s) ===")
    print(f"  total completed: {sum(tally.values())}")
    for k in ("absent_target", "no_evidence", "behavioral", "ok"):
        print(f"  {k:14}: {tally[k]}")
    print(f"\n  AGENT work-list (absent_target{' + behavioral' if args.all else ''}): {len(rows)}")
    if args.show:
        for r in rows:
            print(f"    [{r['signal']}] {r['spoke']}: {r['id']}")


def cmd_promote(args):
    d = _load(args.lug)
    if d is None:
        print(f"cannot read {args.lug}", file=sys.stderr); sys.exit(2)
    new, became, missing = promote(d)
    verdict = "auto_build" if became else f"still review (missing: {', '.join(missing) or 'n/a'})"
    print(f"{os.path.basename(args.lug)}: {classify_lug(d)} -> {verdict}")
    if became and args.write:
        json.dump(new, open(args.lug, "w"), indent=2)
        print("  WROTE.")
    elif became:
        print("  (dry-run; pass --write to persist)")


def cmd_retire(args):
    d = _load(args.lug)
    if d is None:
        print(f"cannot read {args.lug}", file=sys.stderr); sys.exit(2)
    if not _is_advisory(d, d.get("id") or os.path.basename(args.lug)):
        print("refusing: not an advisory artifact (crew/scout/coverage). Use promote.", file=sys.stderr)
        sys.exit(3)
    new = retire(d)
    print(f"{os.path.basename(args.lug)}: advisory -> reclassified_advisory")
    if args.write:
        json.dump(new, open(args.lug, "w"), indent=2); print("  WROTE.")
    else:
        print("  (dry-run; pass --write to persist)")


CORE = {
 "keeping-open-lines": "/home/mario/projects/keeping-open-lines",
 "basher": "/home/mario/projects/basher",
 "website": "/home/mario/projects/wheelwright/website",
 "track-prompt-lab": "/home/mario/projects/track-prompt-lab",
 "ezorg-email-website": "/home/mario/projects/ezorg-email-website",
 "minder": "/home/mario/projects/minder",
 "solutions-by-mv": "/home/mario/projects/solutions-by-mv",
 "canwesellitonline": "/home/mario/projects/canwesellitonline",
 "pathfinder": "/home/mario/projects/pathfinder",
}


def _resolve_spokes(args):
    if args.root:
        return {os.path.basename(args.root.rstrip("/")): args.root}
    if args.spokes:
        want = set(args.spokes.split(","))
        return {k: v for k, v in CORE.items() if k in want}
    return dict(CORE)


def main():
    ap = argparse.ArgumentParser(description="Lug readiness audit + deterministic reclassifier (Lug B)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit"); a.add_argument("--spokes"); a.add_argument("--root"); a.add_argument("--json", action="store_true"); a.set_defaults(fn=cmd_audit)
    p = sub.add_parser("plan"); p.add_argument("root"); p.add_argument("--show", action="store_true"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_plan)
    tg = sub.add_parser("triage"); tg.add_argument("--spokes"); tg.add_argument("--root"); tg.add_argument("--show", action="store_true"); tg.add_argument("--json", action="store_true"); tg.set_defaults(fn=cmd_triage)
    vc = sub.add_parser("verify-completed"); vc.add_argument("--spokes"); vc.add_argument("--root"); vc.add_argument("--all", action="store_true", help="include behavioral (no-file-target) lugs in the work-list"); vc.add_argument("--show", action="store_true"); vc.add_argument("--json", action="store_true"); vc.set_defaults(fn=cmd_verify_completed)
    pr = sub.add_parser("promote"); pr.add_argument("lug"); pr.add_argument("--write", action="store_true"); pr.set_defaults(fn=cmd_promote)
    rt = sub.add_parser("retire"); rt.add_argument("lug"); rt.add_argument("--write", action="store_true"); rt.set_defaults(fn=cmd_retire)
    gr = sub.add_parser("groom"); gr.add_argument("target", help="a lug file, or a directory to scan"); gr.add_argument("--flag-only", action="store_true", help="report but do not fail exit code"); gr.add_argument("--json", action="store_true"); gr.set_defaults(fn=cmd_groom)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
