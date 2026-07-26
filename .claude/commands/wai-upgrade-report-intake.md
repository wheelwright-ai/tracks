# WAI Upgrade Report Intake

Turn upgrade-report lugs into work. Invoked from `wai.md` Step 2.5 for each report
found in `WAI-Harness/spoke/local/lugs/bytype/upgrade-report/open/`.

## What changed, and why this ceremony was rewritten

This ceremony has existed and run at every wakeup for months without ever
receiving a single report, because the only thing that wrote one was a
copy-paste JSON template in the adoption ceremony, on v3 paths, addressed to a
deprecated repo. Half a circle looks exactly like a whole one from the half that
works.

Reports are now produced by `harness_upgrade.py` automatically, on the spoke that
took the upgrade, and they answer a different question than the old ones did:

| old (never arrived) | now |
|---|---|
| a human's adoption friction | a machine's validation result |
| `teaching_id` + friction prose | `validation.checks[]` with evidence |
| written by hand, sometimes | written by the engine, every upgrade |
| graded on absolute outcome | graded on REGRESSION vs a pre-upgrade baseline |

The grading distinction is the important one. `outcome: partial` means checks
failed but they were failing before this upgrade too — the upgrade is not
answerable for damage it did not cause. `outcome: fail` means a check that
passed before the upgrade fails after it. Only `fail` is a defect in the cut.

---

## Step 1 — Read the report

```python
import glob, json, os

BASE = "WAI-Harness/spoke/local"
if not os.path.isdir(BASE):
    BASE = "WAI-Spoke"          # v3 coexist spokes only

report = json.load(open(report_path))
report_id  = report["id"]
spoke_id   = report.get("spoke_id", "unknown")
outcome    = report.get("outcome", "partial")          # pass | partial | fail
validation = report.get("validation", {})
regressions   = validation.get("regressions", [])
preexisting   = validation.get("preexisting_failures", [])
failed_checks = [c for c in validation.get("checks", []) if c.get("status") == "fail"]
```

## Step 2 — `outcome: pass` → archive, no lugs

Nothing broke and nothing was already broken. Skip to Step 5.

## Step 2.6 — `outcome: fail` but it's a TRANSIENT FREEZE → archive, no bug

Not every FAIL is a regression. When master's own self-verification aborts on a
dirty `managed/` working tree, EVERY spoke that pulls in that window emits
`outcome: fail` with an empty validation block and a summary like "self-verification
… corrupt master" / "bytes MISMATCHED; ABORTED before validation". The spoke was
never broken — the master was briefly un-shippable — and it self-heals on the next
pull. Opening a regression bug per such report buries the queue in phantom "spoke
broke" bugs (18 in one day, 2026-07-22). Detect the freeze signature and archive as
transient instead.

```python
_freeze_sig = ("self-verification", "corrupt master", "bytes mismatched", "aborted before validation")
_summary = str(report.get("summary", "")).lower()
if outcome == "fail" and any(s in _summary for s in _freeze_sig) and not regressions:
    report["_disposition"] = {"verdict": "transient master-freeze, not a regression — archived, no bug",
                              "detail": "master self-verification aborted on a dirty managed/ tree; "
                                        "the spoke self-heals on the next pull. See managed_sentinel.py."}
    # Skip to Step 5 (archive). Do NOT open a bug.
    failed_checks = []
    regressions = []
```

## Step 3 — `outcome: fail` → one bug lug per REGRESSION

A regression is a defect in the cut that master shipped. It gets a bug lug per
broken check, at high urgency, because a spoke is broken right now.

```python
import datetime, re

def slug(t): return re.sub(r"[^a-z0-9]+", "-", str(t).lower()).strip("-")[:40]

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
version = report.get("harness_version", "unknown")
bug_count = 0

for check in [c for c in failed_checks if c["check"] in regressions]:
    bug_id = f"bug-upgrade-{slug(version)}-broke-{slug(check['check'])}-on-{slug(spoke_id)}-v1"
    path = f"{BASE}/lugs/bytype/bug/open/{bug_id}.json"
    if os.path.exists(path):
        continue                                   # dedup: same cut, same check, same spoke
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({
        "id": bug_id, "type": "bug", "status": "open", "routed_to": "LOCAL",
        "created_at": now, "created_by": "wai-upgrade-report-intake",
        "title": f"Harness {version} broke '{check['check']}' on {spoke_id}",
        "summary": (f"Validation check '{check['check']}' PASSED before the upgrade to "
                    f"{version} and FAILS after it on spoke {spoke_id}. {check.get('detail','')}"),
        "perceive": [f"Read the upgrade report {report_id}",
                     f"Evidence: {'; '.join(check.get('evidence') or []) or 'see report'}",
                     "Reproduce: python3 tools/harness_upgrade.py validate --spoke-root <spoke>"],
        "execute": [f"Fix the master file(s) responsible for the '{check['check']}' failure",
                    "Recut MANIFEST and redistribute — do not patch the spoke directly"],
        "verify": [f"python3 tools/harness_upgrade.py validate --spoke-root <spoke> => '{check['check']}' passes",
                   "A fresh pull on a clean copy of the spoke reports outcome=pass or partial, never fail"],
        "file_targets": ["WAI-Harness/spoke/managed/"],
        "impact": 9, "effort": 2, "urgency": 5,
        "model_fit": "sonnet",
        "source_report": report_id, "source_spoke": spoke_id,
    }, open(path, "w"), indent=2)
    bug_count += 1
```

## Step 4 — `outcome: partial` → ONE debt lug per pre-existing check

Pre-existing failures are real and worth fixing, but they are not this cut's
fault and they are usually identical across every spoke. One lug per check name,
deduped — never one per spoke per upgrade, which would bury the queue in copies
of the same finding.

```python
impl_count = 0
for name in preexisting:
    lug_id = f"impl-validation-debt-{slug(name)}-v1"
    path = f"{BASE}/lugs/bytype/impl/open/{lug_id}.json"
    if os.path.exists(path):
        continue
    os.makedirs(os.path.dirname(path), exist_ok=True)
    check = next((c for c in failed_checks if c["check"] == name), {})
    json.dump({
        "id": lug_id, "type": "impl", "status": "open", "routed_to": "LOCAL",
        "created_at": now, "created_by": "wai-upgrade-report-intake",
        "title": f"Validation check '{name}' is failing on spokes before any upgrade touches them",
        "summary": (f"'{name}' fails at upgrade time and was already failing beforehand, so no "
                    f"single upgrade is answerable for it. First seen on {spoke_id}. "
                    f"{check.get('detail','')}"),
        "perceive": ["Reproduce: python3 tools/harness_upgrade.py validate --spoke-root <spoke>",
                     f"Evidence: {'; '.join(check.get('evidence') or []) or 'see report'}",
                     "Check whether this is fleet-wide or specific to one spoke before fixing"],
        "execute": [f"Fix the underlying cause of the '{name}' failure at master"],
        "verify": [f"python3 tools/harness_upgrade.py validate --spoke-root . => '{name}' passes"],
        "file_targets": ["WAI-Harness/spoke/managed/"],
        "impact": 6, "effort": 3,
        "model_fit": "sonnet",
        "source_report": report_id, "source_spoke": spoke_id,
    }, open(path, "w"), indent=2)
    impl_count += 1
```

## Step 5 — Archive the report

```python
import shutil
dst_dir = f"{BASE}/lugs/bytype/upgrade-report/completed"
os.makedirs(dst_dir, exist_ok=True)
shutil.move(report_path, os.path.join(dst_dir, os.path.basename(report_path)))
```

## Step 6 — Track event

```python
state = json.load(open(f"{BASE}/WAI-State.json"))
track_path = state.get("_session", {}).get("track_path", "")
event = {
    "event": "upgrade_report_processed",
    "ts": now,
    "spoke_id": spoke_id,
    "harness_version": version,
    "outcome": outcome,
    "regressions": regressions,
    "preexisting_failures": preexisting,
    "bug_lugs_opened": bug_count,
    "impl_lugs_opened": impl_count,
}
if track_path and os.path.isfile(track_path):
    with open(track_path, "a") as f:
        f.write(json.dumps(event) + "\n")
```

## Step 7 — Report to the operator

```
Upgrade report from {spoke_id} ({version}): {outcome}
  regressions      {n}  -> {n} bug lug(s) opened   [a spoke is broken NOW]
  pre-existing     {n}  -> {n} debt lug(s) opened  [not this cut's fault]
```

Say nothing when there were no reports — an empty intake is the normal case. But
if reports stop arriving entirely across a period in which upgrades DID happen,
that is the producer half of this circle failing again, and it is worth saying so
out loud rather than reading silence as health.
