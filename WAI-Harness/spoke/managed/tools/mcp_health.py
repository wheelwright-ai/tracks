#!/usr/bin/env python3
"""mcp_health.py -- which MCP servers exist, which answer, and which are actually used.

MEASURED 2026-08-19 before this existed:

    gitnexus   user-level; MANDATED by CLAUDE.md before any symbol edit
    magic      user-level; ZERO references across 68 projects and all harness files
    supabase   ezorg only -- the single project-level server in the estate
    harness    ZERO awareness: no mcpServers / mcp__ / modelcontextprotocol anywhere

basher, minder and framework each carry an EMPTY .mcp.json. That is worse than absent: it
reads as configured, and no surface flags it.

THREE STATES, NEVER TWO, because the actions differ:

    DECLARED    is it in a config file anywhere
    REACHABLE   does it answer an MCP `initialize` handshake
    USED        has any session actually called one of its tools

  declared + unreachable  -> broken; something depends on it and it is not answering
  reachable + unused      -> waste; it costs config and attention and earns nothing
  declares nothing        -> a config bug; an empty server list masquerading as setup

A boolean forces all three into one answer, which is exactly how an empty .mcp.json on
three spokes went unnoticed. This is the s141 defect class -- correct-looking, unverifiable
-- applied to a protocol the harness could not previously see at all.

UNKNOWN IS NOT GREEN. If a probe cannot run, the verdict is UNKNOWN and the reason is
printed. A server that could not be checked must never read as healthy.

USAGE
  mcp_health.py inventory [--json]          what is declared, and where
  mcp_health.py probe [--server NAME] [--json] [--timeout S]   does it answer
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

TOOL_VERSION = "1.0.0"

# Verdict vocabulary. Distinct strings on purpose -- collapsing any two loses an action.
ABSENT = "ABSENT"
DECLARES_NOTHING = "DECLARES_NOTHING"
DECLARED = "DECLARED"
REACHABLE = "REACHABLE"
UNREACHABLE = "UNREACHABLE"
UNKNOWN = "UNKNOWN"
USED = "USED"
UNUSED = "UNUSED"
UNMEASURED = "UNMEASURED"

USER_CONFIG = "~/.claude.json"
TRANSCRIPTS = "~/.claude/projects/*/*.jsonl"


def _read(path):
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def declared(project_globs=(), user_config=None) -> dict:
    """Every declared server, with WHERE it was declared.

    An empty mcpServers block is reported as DECLARES_NOTHING against the file rather than
    silently contributing zero servers -- the file is a claim, and an empty claim is a
    finding.
    """
    out = {"servers": {}, "empty_declarations": [], "sources": []}

    # user_config is a PARAMETER, not a constant. Reading ~/.claude.json unconditionally
    # made this function untestable -- every fixture inherited the real machine's servers,
    # so "declares nothing" could never be observed. A function that cannot be given its
    # inputs cannot be given a failing case either.
    uc = USER_CONFIG if user_config is None else user_config
    user = _read(uc) if uc else None
    for name, cfg in ((user or {}).get("mcpServers") or {}).items():
        out["servers"].setdefault(name, []).append({"scope": "user", "file": uc,
                                                    "config": cfg})
    if uc:
        out["sources"].append(uc)

    for pattern in project_globs:
        for path in sorted(glob.glob(os.path.expanduser(pattern))):
            data = _read(path)
            if data is None:
                continue
            out["sources"].append(path)
            servers = data.get("mcpServers") or {}
            if not servers:
                out["empty_declarations"].append(path)
                continue
            for name, cfg in servers.items():
                out["servers"].setdefault(name, []).append(
                    {"scope": "project", "file": path, "config": cfg})
    return out


def probe(config: dict, timeout: float = 10.0) -> dict:
    """Spawn the server and speak MCP at it: does it answer `initialize`?

    This is the real handshake, not a process-liveness check. A command that starts and
    then fails to negotiate is UNREACHABLE, and the distinction matters -- `npx` will
    happily start for a package that does not exist.
    """
    command = config.get("command")
    if not command:
        return {"state": UNKNOWN, "why": "config declares no command to run"}
    argv = [command] + list(config.get("args") or [])
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (config.get("env") or {}).items()})

    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "wai-mcp-health", "version": TOOL_VERSION}},
    }) + "\n"

    try:
        proc = subprocess.run(argv, input=request, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except FileNotFoundError:
        return {"state": UNREACHABLE, "why": f"command not found: {command}"}
    except subprocess.TimeoutExpired:
        # A server that never answers is not healthy, but it is also not proven dead.
        return {"state": UNKNOWN, "why": f"no response within {timeout}s"}
    except Exception as exc:                                    # noqa: BLE001
        return {"state": UNKNOWN, "why": f"probe could not run: {exc}"}

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue                       # servers log to stdout; step over the noise
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == 1 and "result" in msg:
            info = (msg["result"] or {}).get("serverInfo") or {}
            return {"state": REACHABLE, "why": "answered initialize",
                    "server_name": info.get("name", ""), "version": info.get("version", ""),
                    "protocol": (msg["result"] or {}).get("protocolVersion", "")}
        if msg.get("id") == 1 and "error" in msg:
            return {"state": UNREACHABLE, "why": f"initialize error: {msg['error']}"}
    tail = (proc.stderr or "").strip().splitlines()
    return {"state": UNREACHABLE,
            "why": "no initialize response" + (f"; stderr: {tail[-1][:120]}" if tail else "")}


def used(names, transcripts=TRANSCRIPTS, limit_files=400) -> dict:
    """Has any session actually CALLED one of this server's tools?

    Measured from transcripts by the `mcp__<server>__` tool-name prefix. When no transcripts
    can be read the answer is UNMEASURED, never UNUSED -- inferring absence from a source
    that was not consulted is the false green this whole object exists to prevent.
    """
    files = sorted(glob.glob(os.path.expanduser(transcripts)))[-limit_files:]
    if not files:
        return {n: {"state": UNMEASURED, "why": "no transcripts readable"} for n in names}
    hits = {n: 0 for n in names}
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                blob = fh.read()
        except OSError:
            continue
        for n in names:
            hits[n] += blob.count(f"mcp__{n}__")
    return {n: {"state": USED if c else UNUSED, "calls": c,
                "why": f"{c} tool call(s) across {len(files)} transcript(s)"}
            for n, c in hits.items()}


def report(project_globs=(), do_probe=True, timeout=10.0, user_config=None) -> dict:
    decl = declared(project_globs, user_config=user_config)
    names = sorted(decl["servers"])
    usage = used(names)
    rows = []
    for name in names:
        where = decl["servers"][name]
        row = {"server": name, "declared_in": [w["file"] for w in where],
               "scopes": sorted({w["scope"] for w in where}),
               "reachability": {"state": UNMEASURED, "why": "probe not requested"},
               "usage": usage.get(name, {"state": UNMEASURED})}
        if do_probe:
            row["reachability"] = probe(where[0]["config"], timeout=timeout)
        rows.append(row)
    return {"servers": rows, "empty_declarations": decl["empty_declarations"],
            "sources_read": len(decl["sources"]), "tool_version": TOOL_VERSION}


def _print(res):
    print(f"\nMCP INVENTORY -- {len(res['servers'])} server(s) across "
          f"{res['sources_read']} config file(s)\n")
    for r in res["servers"]:
        reach, use = r["reachability"], r["usage"]
        print(f"  {r['server']:<12} {reach['state']:<14} {use['state']:<12} "
              f"({','.join(r['scopes'])})")
        print(f"               reach: {reach.get('why','')[:88]}")
        print(f"               usage: {use.get('why','')[:88]}")
    if res["empty_declarations"]:
        print(f"\n  {len(res['empty_declarations'])} file(s) DECLARE NOTHING -- an empty "
              "server list reads as configured:")
        for f in res["empty_declarations"]:
            print(f"    {f}")
    print("\n  declared+unreachable = broken · reachable+unused = waste · "
          "UNKNOWN = could not check, NOT healthy")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inventory", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        p.add_argument("--timeout", type=float, default=10.0)
        p.add_argument("--glob", action="append", default=[],
                       help="project config glob; repeatable")
        if name == "probe":
            p.add_argument("--server", default="")
    args = ap.parse_args(argv)

    globs = args.glob or ["/home/mario/projects/*/.mcp.json",
                          "/home/mario/projects/wheelwright/*/.mcp.json"]
    res = report(globs, do_probe=(args.cmd == "probe"), timeout=args.timeout)
    if getattr(args, "server", ""):
        res["servers"] = [r for r in res["servers"] if r["server"] == args.server]
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        _print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
