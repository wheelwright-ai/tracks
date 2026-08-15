#!/usr/bin/env python3
"""run_advisor.py -- execute an advisor's declared command AND record that it ran.

W10 of the LOW TRUST tenet (spec-low-trust-tenet-v1), and the missing half of L2.

THE DEFECT, FOUND BY RUNNING THE FIX. On 2026-08-02 the assurance oracle and the
proofer were executed by hand for the first time in their existence. Both produced
real findings. Both still reported NEVER afterwards, because nothing on the way out
wrote down that they had run: their scan_state.json still said `runs: 0`, and the
schedule index still said `last_run_at: null`.

That is worse than it sounds. It means a nightly scheduler could have been running
every advisor perfectly for months and every instrument would still have reported
NEVER -- and, symmetrically, that no amount of running things fixes the liveness
number. The loop was open at the RECORDING end, not the execution end. Cadences,
schedulers and good intentions were all downstream of a write that nobody made.

WHAT THIS DOES. Resolves the advisor's declared command (index first, then its own
contract), runs it, and writes the outcome to the two places every reader looks:

  * <advisor>/runs.jsonl        append-only, one row per run, with exit code
  * <advisor>/scan_state.json   stats.runs incremented, last_run_at stamped
  * schedule-index.json         last_run_at stamped for that advisor

A FAILED RUN IS STILL A RUN, and is recorded as one. This is the inversion from
oracle_liveness restated at the write end: an advisor that ran and failed has told
you something, and downgrading it back to NEVER would hide a working oracle behind
a red result. `ok` is recorded separately from the fact of running, so a reader can
ask either question.

WHAT IT REFUSES. It will not record a run it did not perform. There is no --force,
no --assume-ok, and a command that cannot be resolved is reported UNRUNNABLE and
records nothing -- because a liveness record is evidence, and evidence you wrote
without doing the work is the exact failure this whole tenet exists to remove.

CLI:
    run_advisor.py --root DIR run ADVISOR [--timeout N] [--dry-run]
    run_advisor.py --root DIR run-all [--state STATE] [--timeout N] [--dry-run]
    run_advisor.py --root DIR resolve ADVISOR      show the command, run nothing

Exit codes: 0 ran and the command succeeded, 1 ran and it failed, 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol
import trust_epoch as te

DEFAULT_TIMEOUT = 900
_PY_PATH = re.compile(r"([\w./-]+\.py)")


def _advisor_dir(root, advisor_id):
    return os.path.join(ol.advisors_dir(root), advisor_id)


def resolve_command(root, advisor_id):
    """(command, source) or (None, reason). Index first, then the contract.

    A bare `tool` value is turned into `python3 <tool>`; a `command` or
    `dispatch_command` is taken as written. Every .py path named must exist -- an
    unresolvable command is UNRUNNABLE, never something to attempt and hope.
    """
    index = ol.schedule_index(root).get(advisor_id, {})
    contract_path = os.path.join(_advisor_dir(root, advisor_id), "contract.json")
    contract = {}
    try:
        with open(contract_path) as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            contract = loaded
    except (OSError, ValueError):
        pass

    for source, blob in (("schedule-index", index), ("contract", contract)):
        for key in ("dispatch_command", "command"):
            value = blob.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), f"{source}.{key}"
        tool = blob.get("tool")
        if isinstance(tool, str) and tool.strip():
            return f"python3 {tool.strip()}", f"{source}.tool"

    # AGENT FALLBACK. An advisor with no tool is not automatically unrunnable --
    # it may be agent-backed, which until 2026-08-03 meant permanently unrunnable:
    # zero of 34 advisors carried a dispatch command, so every agent-backed one was
    # declined forever and two sat SILENT for 59 days with no path back.
    #
    # Gated on `fund: true` per the operator's ruling (s140): unattended jobs may
    # spend tokens on agent-backed advisors WHEN Ozi has determined they are worth
    # prioritising. `fund` is that determination and already governs ozi_autopilot
    # and spoke_pulse; honouring it here extends an existing decision rather than
    # inventing a second one that could disagree with it.
    #
    # Deliberately last: a tool-backed advisor must never be dispatched to a model,
    # because a deterministic check answered by a language model is not the same
    # check and would cost money to produce a weaker answer.
    if contract.get("fund") is True and os.path.exists(
            os.path.join(_advisor_dir(root, advisor_id), "context_prompt.md")):
        return (f"python3 WAI-Harness/spoke/managed/tools/advisor_agent_dispatch.py "
                f"--root . --advisor {advisor_id}"), "agent-dispatch (funded)"

    return None, "no dispatch_command, command, or tool declared"


def _missing_paths(root, command):
    return [p for p in _PY_PATH.findall(command)
            if not os.path.exists(os.path.join(root, p))]


def record_run(root, advisor_id, command, returncode, tail):
    """Write the run to every place a reader looks. Called only after execution."""
    directory = _advisor_dir(root, advisor_id)
    os.makedirs(directory, exist_ok=True)
    stamp = te._iso(te._now())
    row = {"advisor_id": advisor_id, "ran_at": stamp, "command": command,
           "exit_code": returncode, "ok": returncode == 0, "tail": tail[:400]}

    with open(os.path.join(directory, "runs.jsonl"), "a") as handle:
        handle.write(json.dumps(row) + "\n")

    state_path = os.path.join(directory, "scan_state.json")
    state = {}
    try:
        with open(state_path) as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            state = loaded
    except (OSError, ValueError):
        pass
    state.setdefault("advisor_id", advisor_id)
    state["last_run_at"] = stamp
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    stats["runs"] = int(stats.get("runs") or 0) + 1
    if returncode == 0:
        stats["last_green"] = stamp
    else:
        stats["last_red"] = stamp
    state["stats"] = stats
    with open(state_path, "w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")

    index_path = os.path.join(ol.advisors_dir(root), "schedule-index.json")
    # BOTH SHAPES ARE REAL ON DISK. This file is written as a BARE LIST of advisor
    # rows by the schedulers, but was read here as {"advisors": [...]}. A bare list
    # has no .get, and AttributeError is not in the except clause below -- so the
    # exception escaped record_run and killed the process AFTER the advisor had
    # already executed. The run happened; the record never landed; the bench then
    # reported the advisor as "never run". MEASURED 2026-08-06 (basher s123): 5 of
    # 10 advisors showed "never run" for this reason, not for lack of running.
    # Normalise on read, write back in the shape we found.
    try:
        with open(index_path) as handle:
            index = json.load(handle)
        if isinstance(index, list):
            rows, was_list = index, True
        elif isinstance(index, dict):
            rows, was_list = index.setdefault("advisors", []), False
        else:
            raise ValueError(f"unsupported schedule-index shape: {type(index).__name__}")
        for entry in rows:
            if isinstance(entry, dict) and entry.get("advisor_id") == advisor_id:
                entry["last_run_at"] = stamp
                break
        else:
            rows.append({"advisor_id": advisor_id, "last_run_at": stamp})
        with open(index_path, "w") as handle:
            json.dump(rows if was_list else index, handle, indent=2)
            handle.write("\n")
        row["index_updated"] = True
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        # Never let a bookkeeping failure discard a real run again.
        row["index_updated"] = False
        row["index_error"] = f"{type(exc).__name__}: {exc}"
    return row


def run(root, advisor_id, timeout=DEFAULT_TIMEOUT, dry_run=False):
    command, source = resolve_command(root, advisor_id)
    if command is None:
        return {"advisor": advisor_id, "state": "UNRUNNABLE", "ran": False,
                "reason": source}
    missing = _missing_paths(root, command)
    if missing:
        return {"advisor": advisor_id, "state": "UNRUNNABLE", "ran": False,
                "command": command, "source": source,
                "reason": f"command names missing path(s): {', '.join(missing)}"}
    if dry_run:
        return {"advisor": advisor_id, "state": "RESOLVED", "ran": False,
                "command": command, "source": source,
                "reason": "dry-run -- nothing executed and nothing recorded"}
    try:
        proc = subprocess.run(command, shell=True, cwd=root, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A timeout is not a run: no verdict was reached, so recording one would be
        # inventing evidence. Reported loudly instead.
        return {"advisor": advisor_id, "state": "TIMEOUT", "ran": False,
                "command": command, "reason": f"exceeded {timeout}s -- nothing recorded"}
    except OSError as exc:
        return {"advisor": advisor_id, "state": "UNRUNNABLE", "ran": False,
                "command": command, "reason": str(exc)}

    output = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-6:])
    row = record_run(root, advisor_id, command, proc.returncode, tail)
    return {"advisor": advisor_id, "ran": True, "ok": proc.returncode == 0,
            "state": "RAN_OK" if proc.returncode == 0 else "RAN_FAILED",
            "exit_code": proc.returncode, "command": command, "source": source,
            "recorded_at": row["ran_at"], "tail": tail}


def run_all(root, states=("NEVER", "SILENT"), timeout=DEFAULT_TIMEOUT, dry_run=False):
    report = ol.check(root)
    targets = [r["advisor"] for r in report["results"] if r["state"] in states]
    return {"targeted_states": list(states), "targets": targets,
            "results": [run(root, a, timeout, dry_run) for a in targets]}


def render(result):
    if "results" in result:
        lines = [f"targeting {', '.join(result['targeted_states'])}: "
                 f"{len(result['targets'])} advisor(s)"]
        for r in result["results"]:
            lines.append(f"  [{r['state']:<10}] {r['advisor']:<26} "
                         f"{r.get('reason') or r.get('tail','').splitlines()[-1:] or ''}")
        return "\n".join(str(l) for l in lines)
    lines = [f"[{result['state']}] {result['advisor']}"]
    if result.get("command"):
        lines.append(f"  command: {result['command']}  ({result.get('source','')})")
    if result.get("reason"):
        lines.append(f"  {result['reason']}")
    if result.get("ran"):
        lines.append(f"  recorded at {result['recorded_at']} (exit {result['exit_code']})")
    return "\n".join(lines)


_EXIT = {"RAN_OK": 0, "RAN_FAILED": 1, "RESOLVED": 0,
         "UNRUNNABLE": 2, "TIMEOUT": 2}


def _main(argv=None):
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--json", action="store_true")
    top.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    top.add_argument("--dry-run", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--timeout", type=int, default=argparse.SUPPRESS)
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("advisor")
    p_all = sub.add_parser("run-all", parents=[common])
    p_all.add_argument("--state", action="append", default=None)
    p_res = sub.add_parser("resolve", parents=[common])
    p_res.add_argument("advisor")
    args = parser.parse_args(argv)

    if args.cmd == "resolve":
        command, source = resolve_command(args.root, args.advisor)
        out = {"advisor": args.advisor, "command": command, "source": source}
        print(json.dumps(out, indent=2) if args.json else
              f"{args.advisor}: {command or 'UNRESOLVABLE'}  ({source})")
        return 0 if command else 2

    if args.cmd == "run-all":
        out = run_all(args.root, tuple(args.state or ("NEVER", "SILENT")),
                      args.timeout, args.dry_run)
        print(json.dumps(out, indent=2) if args.json else render(out))
        return 2 if any(r["state"] in ("UNRUNNABLE", "TIMEOUT") for r in out["results"]) \
            else (1 if any(r["state"] == "RAN_FAILED" for r in out["results"]) else 0)

    out = run(args.root, args.advisor, args.timeout, args.dry_run)
    print(json.dumps(out, indent=2) if args.json else render(out))
    return _EXIT.get(out["state"], 2)


if __name__ == "__main__":
    raise SystemExit(_main())
