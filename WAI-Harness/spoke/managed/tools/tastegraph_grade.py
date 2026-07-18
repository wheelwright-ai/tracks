#!/usr/bin/env python3
"""tastegraph_grade.py — the checklist grade: blind dual grading + openness trajectory.

THE RITUAL (operator design, s138 final test): every TasteGraph version is a
checklist. Agent and operator each grade a session/period against it BLINDLY —
neither sees the other's scores until both are sealed — then `compare` reveals
both, scores the agreement, and `trajectory` plots convergence across versions.
The trajectory IS the openness measure: two honest graders converge; a flattering
agent and a frustrated operator diverge, visibly.

INHERITANCE ("the parent tells the child what we've agreed you've become"):
`inheritance` emits the compact statement a new session/version receives at
birth — the version, the active preference counts, the latest agreed grade, and
the currently-worst-graded items as the child's explicit growth edge.

Verbs
  checklist                 render vN's gradeable checklist (stated/verified prefs only)
  grade --grader X          score interactively-prepared JSON; sealed until compared
  compare                   reveal both graders for a version; agreement + deltas
  trajectory                convergence across all versions with paired grades
  inheritance               the birth statement for the next session/version

Scores: 0 = violated, 1 = partially honored, 2 = honored. Grades live under
hub/local/tastegraph-grades/v{version}/{grader}.json. A sealed grade file is
data; the BLINDNESS is procedural — `grade` refuses to show the other grader's
file, and `compare` is the only reveal path.
"""
import argparse, json, os, sys, datetime

GRAPH = "WAI-Harness/hub/local/tastegraph-org.json"
GRADES = "WAI-Harness/hub/local/tastegraph-grades"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_graph(path):
    with open(path) as f:
        return json.load(f)


def active_items(g):
    return [p for p in sorted(g.get("preferences", []), key=lambda p: (p.get("category", ""), p["id"]))
            if p.get("confidence") in ("stated", "verified")]


def cmd_checklist(a):
    g = load_graph(a.graph)
    items = active_items(g)
    print(f"TASTEGRAPH CHECKLIST v{g.get('version')} — {len(items)} gradeable items (stated/verified only)")
    print("score each 0=violated 1=partial 2=honored | grade file: {\"scores\": {\"<id>\": 0|1|2}, \"evidence\": {\"<id>\": \"...\"}}")
    cat = None
    for p in items:
        if p.get("category") != cat:
            cat = p.get("category")
            print(f"\n[{cat}]")
        print(f"  {p['id']}: {str(p.get('value'))[:110]}")
    return 0


def cmd_grade(a):
    g = load_graph(a.graph)
    ver = g.get("version")
    items = {p["id"] for p in active_items(g)}
    with open(a.scores) as f:
        payload = json.load(f)
    scores = payload.get("scores", {})
    unknown = sorted(set(scores) - items)
    missing = sorted(items - set(scores))
    if unknown:
        print(f"REFUSED: {len(unknown)} score(s) for ids not in v{ver}: {unknown[:5]}")
        return 2
    bad = {k: v for k, v in scores.items() if v not in (0, 1, 2)}
    if bad:
        print(f"REFUSED: non 0/1/2 scores: {list(bad)[:5]}")
        return 2
    out_dir = os.path.join(a.grades, f"v{ver}")
    os.makedirs(out_dir, exist_ok=True)
    other = [f for f in os.listdir(out_dir) if f.endswith(".json") and not f.startswith(a.grader)]
    out = os.path.join(out_dir, f"{a.grader}.json")
    rec = {"version": ver, "grader": a.grader, "graded_at": _now(),
           "scope": a.scope, "scores": scores,
           "evidence": payload.get("evidence", {}),
           "not_graded": missing,
           "sealed": True}
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    os.replace(tmp, out)
    n = len(scores)
    mean = sum(scores.values()) / n if n else 0.0
    print(f"grade SEALED: v{ver} grader={a.grader} items={n} mean={mean:.2f} ungraded={len(missing)}")
    if other:
        print(f"the other grader has also sealed ({other[0]}) — run `compare` to reveal both together")
    else:
        print("blindness holds: the other grader has not sealed yet; this tool will not show them your scores")
    return 0


def _pair(a, ver):
    d = os.path.join(a.grades, f"v{ver}")
    if not os.path.isdir(d):
        return None
    files = {f[:-5]: json.load(open(os.path.join(d, f))) for f in os.listdir(d) if f.endswith(".json")}
    graders = sorted(files)
    return files if len(graders) >= 2 else None


def cmd_compare(a):
    g = load_graph(a.graph)
    ver = a.version or g.get("version")
    pair = _pair(a, ver)
    if not pair:
        print(f"compare v{ver}: fewer than two sealed grades — blindness holds, nothing to reveal")
        return 1
    (ga, ra), (gb, rb) = sorted(pair.items())[:2]
    common = sorted(set(ra["scores"]) & set(rb["scores"]))
    agree = [i for i in common if ra["scores"][i] == rb["scores"][i]]
    deltas = sorted(((abs(ra["scores"][i] - rb["scores"][i]), i) for i in common), reverse=True)
    pct = 100.0 * len(agree) / len(common) if common else 0.0
    print(f"REVEAL v{ver}: {ga} vs {gb} | {len(common)} co-graded | agreement {pct:.0f}% "
          f"| means {sum(ra['scores'][i] for i in common)/len(common):.2f} vs {sum(rb['scores'][i] for i in common)/len(common):.2f}")
    worst = [i for d, i in deltas if d > 0][: a.top]
    for i in worst:
        print(f"  DIVERGE {i}: {ga}={ra['scores'][i]} {gb}={rb['scores'][i]}")
    low = sorted(common, key=lambda i: ra["scores"][i] + rb["scores"][i])[: a.top]
    print("  agreed-weakest (the growth edge):")
    for i in low:
        print(f"    {i}: {ra['scores'][i]}+{rb['scores'][i]}")
    summary = {"version": ver, "revealed_at": _now(), "graders": [ga, gb],
               "co_graded": len(common), "agreement_pct": round(pct, 1),
               "divergent": worst, "growth_edge": low}
    out = os.path.join(a.grades, f"v{ver}", "REVEALED.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"reveal recorded: {out}")
    return 0


def cmd_trajectory(a):
    if not os.path.isdir(a.grades):
        print("trajectory: no grades yet")
        return 1
    rows = []
    for v in sorted(os.listdir(a.grades)):
        rev = os.path.join(a.grades, v, "REVEALED.json")
        if os.path.isfile(rev):
            r = json.load(open(rev))
            rows.append((v, r.get("agreement_pct"), r.get("co_graded")))
    if not rows:
        print("trajectory: no revealed comparisons yet — the openness curve starts at the first mutual reveal")
        return 1
    print("OPENNESS TRAJECTORY (agreement % per version — converging graders = honest system)")
    for v, pct, n in rows:
        bar = "#" * int((pct or 0) / 5)
        print(f"  {v:>10} {pct:5.1f}%  {bar}  (n={n})")
    return 0


def cmd_inheritance(a):
    g = load_graph(a.graph)
    ver = g.get("version")
    items = active_items(g)
    by_cat = {}
    for p in items:
        by_cat.setdefault(p.get("category", "?"), []).append(p)
    lines = [f"WHAT WE'VE AGREED YOU'VE BECOME — TasteGraph v{ver}",
             f"{len(items)} preferences in force (stated/verified); "
             f"{sum(1 for p in g.get('preferences', []) if p.get('confidence') not in ('stated','verified'))} held awaiting the operator's word.",
             "By category: " + ", ".join(f"{c}={len(v)}" for c, v in sorted(by_cat.items()))]
    rev = os.path.join(a.grades, f"v{ver}", "REVEALED.json")
    prev = sorted(os.listdir(a.grades))[-1] if os.path.isdir(a.grades) and os.listdir(a.grades) else None
    src = rev if os.path.isfile(rev) else (os.path.join(a.grades, prev, "REVEALED.json") if prev else None)
    if src and os.path.isfile(src):
        r = json.load(open(src))
        lines.append(f"Latest mutual grade ({r['version']}): agreement {r['agreement_pct']}% across {r['co_graded']} items.")
        if r.get("growth_edge"):
            lines.append("Your growth edge (the agreed-weakest items — improve these first): " + ", ".join(r["growth_edge"]))
    else:
        lines.append("No mutual grade yet: the first blind reveal defines your baseline. Invite the operator to grade.")
    lines.append("This inheritance supersedes memory of older doctrine: where an old transcript disagrees with the graph, the graph is what we agreed.")
    text = "\n".join(lines)
    print(text)
    if a.write:
        out = "WAI-Harness/hub/local/tastegraph-inheritance.md"
        with open(out, "w") as f:
            f.write(text + "\n")
        print(f"\n(written: {out})")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", default=GRAPH)
    ap.add_argument("--grades", default=GRADES)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checklist")
    gr = sub.add_parser("grade")
    gr.add_argument("--grader", required=True, choices=["agent", "operator"])
    gr.add_argument("--scores", required=True, help="JSON file: {scores:{id:0|1|2}, evidence:{id:str}}")
    gr.add_argument("--scope", default="session")
    cp = sub.add_parser("compare")
    cp.add_argument("--version", default=None)
    cp.add_argument("--top", type=int, default=5)
    sub.add_parser("trajectory")
    ih = sub.add_parser("inheritance")
    ih.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    return {"checklist": cmd_checklist, "grade": cmd_grade, "compare": cmd_compare,
            "trajectory": cmd_trajectory, "inheritance": cmd_inheritance}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
