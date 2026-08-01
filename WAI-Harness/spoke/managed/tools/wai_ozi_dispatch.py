#!/usr/bin/env python3
"""OziDispatch — lug dispatch, status updates, and changelog logging."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from wai_ozi_config import OziConfig

# Lug leasing (optional — graceful fallback if module absent).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lug_lease  # noqa: E402
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False

# UAT-request-on-completion emission (impl-exitclarity-5, optional — graceful
# fallback if module absent so a UAT-emission bug can never brick dispatch).
try:
    from uat_request import emit_uat_request  # noqa: E402
    _UAT_REQUEST_AVAILABLE = True
except ImportError:
    _UAT_REQUEST_AVAILABLE = False

# Independent completion certification (W2/W3, epic-close-the-presumption-gap-v1).
try:
    import completion_certifier  # noqa: E402
    _CERTIFIER_AVAILABLE = True
except ImportError:
    _CERTIFIER_AVAILABLE = False

# Lug types where "completed" is an ASSERTION someone could be wrong about, and
# therefore the types the certifier gates. A report, a notation, a signal or a
# received notice is a RECORD -- it is complete because it arrived, not because
# work was done, and holding those for certification would be pure noise. This
# distinction is not cosmetic: 124 of the 172 completions in the week before the
# gate shipped were upgrade-reports.
CERTIFIABLE_TYPES = frozenset({
    "impl", "bug", "fix", "change", "task", "epic", "feature", "spec",
})


def _certifier_roots(config):
    """(repo_root, spoke_base) for the certifier, derived from bytype_dir only.

    bytype_dir is the one path on the config with an unambiguous shape
    (<base>/lugs/bytype). Deriving the repo from spoke_path instead landed one
    directory off, which made every mechanical `test -f` run in the wrong cwd and
    refuted work that was genuinely done -- a false REFUTED is as damaging as a
    false CERTIFIED, in the opposite direction."""
    base = Path(config.bytype_dir).parent.parent
    for cand in [base] + list(base.parents):
        if (cand / ".git").exists():
            return str(cand), str(base)
    # No git (tests, bare checkouts). Do NOT assume a fixed depth: v4 bases live at
    # <repo>/WAI-Harness/spoke/local (3 up) and v3 bases at <repo>/WAI-Spoke (1 up).
    # A hardcoded 3 silently pointed the certifier above the repo on v3 layouts, so
    # every `test -f` ran in the wrong directory and refuted real work.
    for cand in [base] + list(base.parents):
        if cand.name in ("WAI-Harness", "WAI-Spoke"):
            return str(cand.parent), str(base)
    return str(base), str(base)


# ── Builder taste block (impl-inject-tastegraph-into-autopilot-dispatch-prompt-v1)
# The autonomous builders had the operator's steering wheel disconnected: TasteGraph
# reached the interactive session via hooks, but a dispatched agent runs with
# WAI_AP_DISPATCH=1, which short-circuits session-start before any injection, and this
# prompt carried zero preference content. So the agents the operator worried would
# "force busy work" decided how to proceed with no preference signal at all.
#
# We inject the EXECUTION vector (work_style/workflow prefs that fire DURING work) —
# NOT presentation prefs a headless builder cannot act on. And we cap HARD: s138
# measured that over-injection collapses compliance (the 33-cap / truncation finding).
# A builder gets only the handful of highest-actionability prefs, phrased as rules.
_BUILDER_TASTE_CAP = 8
# The prefs a headless builder can actually obey, in priority order. Matched by id
# substring against the execution vector so this survives pref-id churn.
_BUILDER_TASTE_IDS = [
    "taste-user-002",                    # surgical edits over rewrites
    "work-style-verification-standard",  # verify to falsify; never "probably"
    "taste-user-007",                    # complete PEV/acceptance before creating a lug
    "work-style-scope-discipline",       # stay in the lug's scope
    "taste-user-011",                    # obvious safe fix -> just fix it
    "work-style-quality-bar-maintainable-performant-focused",
    "risk-tolerance-claim-is-not-evidence",  # verified=true needs a re-runnable check
    "taste-user-003",                    # highest-ROI action, don't ask for safe ops
]


def _builder_taste_block(spoke_root: Optional[str]) -> str:
    """Return a short, capped TasteGraph block for a dispatched builder, or "".

    Fully fail-safe: any error yields no block — a builder must never fail to
    dispatch because preference selection hiccuped. Off unless
    WAI_AP_TASTE=1 (default on; set WAI_AP_TASTE=0 to A/B against the baseline)."""
    if os.environ.get("WAI_AP_TASTE", "1") == "0":
        return ""
    try:
        tv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tastegraph_vector.py")
        if not os.path.isfile(tv):
            return ""
        # --spoke-path is a TOP-LEVEL arg (before the subcommand), not a select arg.
        cmd = [sys.executable, tv]
        if spoke_root:
            cmd += ["--spoke-path", str(spoke_root)]
        cmd += ["select", "--vector", "execution", "--format", "json"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if out.returncode != 0 or not out.stdout.strip():
            return ""
        data = json.loads(out.stdout)
        prefs = data.get("selected") or data.get("prefs") or []
        by_id = {p.get("id"): p for p in prefs if isinstance(p, dict)}
        picked = []
        for want in _BUILDER_TASTE_IDS:
            p = by_id.get(want)
            if p:
                picked.append(p)
            if len(picked) >= _BUILDER_TASTE_CAP:
                break
        if not picked:                                   # cap not matched — fall back to top N
            picked = [p for p in prefs if isinstance(p, dict)][:_BUILDER_TASTE_CAP]
        if not picked:
            return ""
        lines = ["\nHow the operator wants work done (TasteGraph — obey these):"]
        for p in picked:
            body = (p.get("value") or p.get("statement") or p.get("body")
                    or p.get("summary") or p.get("text") or "").strip().replace("\n", " ")
            if body:
                lines.append(f"- {body[:200]}")
        return "\n".join(lines) + "\n"
    except Exception:
        return ""


class OziDispatch:
    """Handles subagent dispatch, lug status writes, and changelog logging."""

    AUTO_EXCLUDED_TYPES = {"implementation", "epic", "review", "session-summary"}

    def __init__(self, config: OziConfig):
        self._config = config

    def auto_dispatch_work(self, queue: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        if not self._config.is_auto_mode_enabled():
            return []
        config = self._config.load_runtime_config()
        max_parallel = int(config.get("max_parallel", 1))
        active_claims = len(queue.get("claimed_by_me", []))
        available_slots = max(0, max_parallel - active_claims)
        if available_slots == 0:
            return []

        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent / "tools"))
            from lug_utils import evaluate_execute_when, load_phases_from_state
            phases = load_phases_from_state()
        except ImportError:
            phases = []
            evaluate_execute_when = None

        dispatched: List[str] = []
        for lug in self._roi_sorted_lugs(queue.get("ready", [])):
            if len(dispatched) >= available_slots:
                break
            lug_type = lug.get("type", lug.get("_fs_type", "unknown"))
            if lug_type in self.AUTO_EXCLUDED_TYPES:
                continue
            lug_id = lug.get("id")
            if not isinstance(lug_id, str) or not lug_id:
                continue
            if evaluate_execute_when:
                ready, reason = evaluate_execute_when(lug, phases)
                if not ready:
                    continue
            if self._dispatch_lug_to_subagent(lug_id, lug):
                dispatched.append(lug_id)
        return dispatched

    def _roi_sorted_lugs(self, lugs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent / "tools"))
            from score_backlog import score_lug
        except ImportError:
            return sorted(lugs, key=lambda l: str(
                l.get("created_at") or l.get("updated_at") or l.get("id") or ""
            ))

        def roi_key(lug: Dict[str, Any]) -> float:
            lug_type = lug.get("_fs_type", lug.get("type", "other"))
            status = lug.get("_fs_status", "open")
            return score_lug(lug, lug_type, status)

        return sorted(lugs, key=roi_key, reverse=True)

    def _dispatch_lug_to_subagent(self, lug_id: str, lug: Dict[str, Any]) -> bool:
        workflow = {
            "current_owner": self._config.current_owner_name(),
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dispatch_method": "auto",
            "auto_session_key": self._config.session_key(),
            "subagent_prompt": self.create_implementation_prompt(lug_id, lug),
        }
        updated = self.update_lug_status(lug_id, "in_progress", workflow)
        if not updated:
            return False
        print(self.render_start_summary(lug_id, lug))
        self.log_changelog(
            {
                "type": "auto_dispatch",
                "lug_id": lug_id,
                "lug_type": lug.get("type", "unknown"),
                "title": lug.get("title", lug_id),
                "dispatched_by": "ozi",
            }
        )
        return True

    def render_start_summary(self, lug_id: str, lug: Dict[str, Any]) -> str:
        title = lug.get("title", lug_id)
        lug_type = str(lug.get("type", "task")).replace("-", " ").title()
        category = lug.get("category")
        tags = lug.get("tags", [])

        if category:
            type_label = f"{lug_type} / {str(category).replace('-', ' ').title()}"
        elif "refactor" in tags and lug_type.lower() != "refactor":
            type_label = f"{lug_type} / Refactor"
        else:
            type_label = lug_type

        priority = str(lug.get("priority", "medium")).title()
        priority_label = (
            f"{priority} (Downtime work)" if "downtime-work" in tags else priority
        )
        description = str(lug.get("description", "No description provided.")).strip()
        tag_label = ", ".join(tags) if tags else "none"

        return "\n".join(
            [
                "",
                f"1. {title} (ID: {lug_id})",
                f"* Type: {type_label}",
                f"* Priority: {priority_label}",
                f"* Tags: {tag_label}",
                f"* Description: {description}",
            ]
        )

    def create_implementation_prompt(self, lug_id: str, lug: Dict[str, Any]) -> str:
        title = lug.get("title", lug.get("t", "Untitled"))
        description = lug.get("description", lug.get("summary", "No description"))
        lug_type = lug.get("type", lug.get("_fs_type", "task"))
        # Base-aware fallback path: derive from the resolved spoke working base
        # (v4: WAI-Harness/spoke/local) so the subagent is pointed at the real
        # tree, not a dead WAI-Spoke path (impl-fix-p2-v3noop-sweep-v1).
        default_path = str(
            self._config.bytype_dir / lug_type / "open" / f"{lug_id}.json"
        )
        file_path = lug.get("_file_path", default_path)
        perceive = lug.get("perceive", "")
        execute = lug.get("execute", "")
        verify = lug.get("verify", "")
        pev_block = ""
        if perceive or execute or verify:
            pev_block = (
                f"\nPEV Contract:\n"
                f"  Perceive: {perceive}\n"
                f"  Execute: {execute}\n"
                f"  Verify: {verify}\n"
            )
        return (
            "You are a builder sub-agent dispatched by Ozi.\n\n"
            f"Your ONLY job: Complete {lug_type} {lug_id}\n\n"
            f"Title: {title}\n\n"
            f"Description:\n{description}\n"
            f"{pev_block}\n"
            "Instructions:\n"
            f"1. Read the full lug from: {file_path}\n"
            "2. Follow the PEV contract: perceive -> execute -> verify\n"
            "3. Stay in scope -- only change what the lug specifies\n"
            "4. Update the lug file with progress and completion notes\n"
            "5. When complete, move lug to completed/ and set status to ready_for_recheck\n"
            "\nStanding Rules (non-negotiable):\n"
            "- Integrated services (gh, vercel, supabase, etc.): USE THEM DIRECTLY."
            " Never ask the user to run service commands. The user configured the integration;"
            " you operate it.\n"
            "- git push: NEVER suggest or run 'git push' unless the lug explicitly requires it"
            " or the user has stated it is blocking. Commits are fine; push is not your call.\n"
            "- Session ceremony: NEVER prompt the user to run savepoint, closeout, or any"
            " session-end protocol. They have those skills and will run them when ready.\n"
            + _builder_taste_block(getattr(self._config, "spoke_path", None))
        )

    def _find_lug_file(self, lug_id: str) -> Optional[Path]:
        bytype_dir = self._config.bytype_dir
        if not bytype_dir.exists():
            return None
        for type_dir in bytype_dir.iterdir():
            if not type_dir.is_dir():
                continue
            for status_dir in type_dir.iterdir():
                if not status_dir.is_dir():
                    continue
                candidate = status_dir / f"{lug_id}.json"
                if candidate.exists():
                    return candidate
        return None

    def update_lug_status(
        self,
        lug_id: str,
        status: str,
        workflow: Dict[str, Any],
        extra_fields: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        activity_log: Optional[Path] = None,
        uat_evidence: Optional[Dict[str, Any]] = None,
    ) -> bool:
        # RULE 1 (spec-lug-lifecycle-ownership-v1, claim-on-pickup): this is
        # the single sanctioned entry point both autopilot dispatch paths
        # (ozi_autopilot.py _dispatch_subprocess and this module's
        # auto_dispatch_work) funnel through to move a lug into in_progress/.
        # Take the lease HERE, atomically with the status transition, so a
        # second worker racing the same lug is refused instead of silently
        # double-claiming it. The lease primitive already existed but was
        # previously consulted only read-only at the dispatch gate — pickup
        # itself never took one, which is the exact gap that let a Herald
        # spawn and a native session both believe they owned the same lug.
        if status == "in_progress" and _LEASE_AVAILABLE:
            # Config may be a lightweight stand-in (tests, embedded callers) that
            # carries paths but not the session API — leasing must degrade, never
            # raise: an AttributeError here would brick every dispatch path.
            _owner = getattr(self._config, "current_owner_name", None)
            sid = session_id or (_owner() if callable(_owner) else "unknown-session")
            try:
                if not lug_lease.claim(lug_id, sid):
                    return False  # live lease held by a different session
            except Exception:
                pass  # fail-open: leasing must never brick dispatch
            workflow = dict(workflow)
            workflow.setdefault("lane", sid)
        elif status in ("completed", "open", "needs_attention") and _LEASE_AVAILABLE:
            # Release on every terminal/rollback transition out of in_progress
            # so the lug is free for the next worker immediately, rather than
            # relying on the 4h TTL to age the lease out.
            # Config may be a lightweight stand-in (tests, embedded callers) that
            # carries paths but not the session API — leasing must degrade, never
            # raise: an AttributeError here would brick every dispatch path.
            _owner = getattr(self._config, "current_owner_name", None)
            sid = session_id or (_owner() if callable(_owner) else "unknown-session")
            try:
                lug_lease.release(lug_id, sid)
            except Exception:
                pass

        # NO SILENT PARKING (bug-a-round-with-zero-claims-reports-ok-clean-v1).
        #
        # A lug moved to needs_attention with no reason is unactionable: the next
        # agent inherits a stopped piece of work and no account of why it stopped,
        # and the operator sees a queue growing with no explanation.
        #
        # Measured round-20260801T200536: all three dispatched lugs were parked
        # here with attention_reason absent. One of them had in fact COMPLETED its
        # work and merely failed to commit it — indistinguishable, from the lug
        # alone, from the one that achieved nothing.
        #
        # Stamp rather than refuse. Refusing would leave the lug stuck in
        # in_progress holding a lease, which is a worse failure than a poor reason;
        # and the marker below is deliberately blunt so it reads as the defect it
        # is rather than as a real explanation.
        if status == "needs_attention":
            extra_fields = dict(extra_fields or {})
            _reason_keys = ("attention_reason", "escalation_reason", "blocked_reason")
            if not any(str(extra_fields.get(k) or "").strip() for k in _reason_keys):
                extra_fields["attention_reason"] = (
                    "UNRECORDED — the caller parked this lug without a reason. "
                    "Whatever stopped it is known only to the agent that stopped it, "
                    "and that agent is gone. Re-read the diff and the activity log "
                    "before re-dispatching."
                )
                extra_fields["attention_reason_missing"] = True

        lug_path = self._find_lug_file(lug_id)
        if not lug_path:
            return False

        try:
            lug = json.loads(lug_path.read_text())
        except (json.JSONDecodeError, OSError):
            return False

        lug["status"] = status
        lug["s"] = status
        lug["updated_at"] = datetime.now(timezone.utc).isoformat()
        current_workflow = lug.get("workflow", {})
        current_workflow.update(workflow)
        lug["workflow"] = current_workflow
        # impl-spine-c8-predicted-vs-realized-join-v1: optional top-level
        # fields (e.g. predicted_roi/urgency_tier/sort_rank) merged onto the
        # lug alongside the status transition -- never required, never nested.
        if extra_fields:
            lug.update(extra_fields)

        # ---- Independent completion certification, at the CHOKE-POINT ----
        # W2 first put this gate in ozi_autopilot._dispatch_subprocess. Measured
        # afterwards: of 172 completions in the previous 7 days, ZERO came through
        # that path and exactly 2 carried a certification block. Gating one caller
        # gates nothing -- which is why the last recertification sweep produced a
        # number and no durable change. The gate belongs here, on the transition
        # itself, per this method's own contract as the single sanctioned entry
        # point (RULE 1 above).
        #
        # SCOPED TO LUGS THAT CLAIM WORK. An upgrade-report or a notation is a
        # record, not a claim that something was built; holding those for
        # certification would be noise, and 124 of those 172 completions were
        # exactly that. CERTIFIABLE_TYPES names the types where "done" is an
        # assertion someone could be wrong about.
        #
        # IDEMPOTENT: a caller that already certified (autopilot does) passes its
        # verdict in extra_fields and is not re-run.
        if status == "completed" and _CERTIFIER_AVAILABLE and not lug.get("certification"):
            _t = (lug.get("type") or lug.get("_fs_type") or "").lower()
            if _t in CERTIFIABLE_TYPES:
                try:
                    _repo, _cbase = _certifier_roots(self._config)
                    _v = completion_certifier.certify(
                        lug, _repo, _cbase, use_agent=False,
                    )
                    lug["certification"] = _v
                    lug["certified_by"] = "completion_certifier @ update_lug_status (choke-point)"
                    if _v["file_targets_backfilled"]:
                        lug["file_targets"] = _v["file_targets"]
                    if _v["disposition"] == completion_certifier.HALTED:
                        status = "open"
                        lug["reopened_reason"] = _v["reason"]
                    elif _v["disposition"] == completion_certifier.ESCALATE:
                        status = "needs_attention"
                        lug["escalation_reason"] = _v["reason"]
                    elif _v["disposition"] == completion_certifier.AWAITING_HUMAN:
                        # The machine's half held; the rest is typed as a human's.
                        # needs_attention is the operator's existing queue, so this
                        # reuses it rather than minting a fifth lifecycle directory
                        # that every reader would have to learn. It is marked
                        # distinctly because it is NOT a failed escalation, and the
                        # skipped steps ride along so the operator sees exactly what
                        # is being asked of them.
                        status = "needs_attention"
                        lug["awaiting_human"] = True
                        lug["awaiting_human_reason"] = _v["reason"]
                        lug["awaiting_human_steps"] = list(
                            _v.get("manual_steps_skipped") or [])
                except Exception as _e:  # noqa: BLE001
                    # FAIL-SAFE, NOT FAIL-OPEN. A broken certifier must not become
                    # a free pass -- that is the presumption being removed.
                    status = "needs_attention"
                    lug["escalation_reason"] = (
                        "completion certifier failed to run (%s) -- an uncertified "
                        "completion is never auto-approved" % _e)
                lug["status"] = status
                lug["s"] = status

        # ---- EVIDENCE FLOOR: a completion without evidence is a CLAIM ----
        #
        # change-canon-autopilot-completion-requires-evidence-v1, measured by basher
        # on run ohr-20260801-2017: 8 lugs dispatched, 89,846 tokens, headline "0
        # errors", and all THREE lugs moved to completed/ carried completed_at: null
        # and no evidence field of any kind. The WORK was real in all three — basher
        # verified by hand. The RECORD is what failed, and an unevidenced completion
        # is indistinguishable from a false one, which makes the "0 errors" headline
        # unverifiable. A run cannot certify itself.
        #
        # This sits BELOW the certifier deliberately, because the certifier above is
        # skipped in two ways: `not lug.get("certification")` lets any caller that
        # supplies its own verdict past (autopilot does exactly that), and non-
        # CERTIFIABLE_TYPES never enter it at all. Neither path asserted completed_at
        # or evidence. The floor is unconditional so no caller can opt out of it.
        #
        # This is canon's own doctrine finally enforced rather than a new rule — the
        # exit gate in signal-lug-gate-before-work-v1 and the "false completions"
        # anti-pattern both already require it; nothing in the dispatch path did.
        _ev_type = (lug.get("type") or lug.get("_fs_type") or "").lower()
        if status == "completed" and _ev_type in CERTIFIABLE_TYPES:
            # Scoped to CERTIFIABLE_TYPES for the SAME reason the certifier is: a
            # report, notation, signal or received notice is a RECORD — complete
            # because it arrived, not because work was done. Demanding evidence of
            # those would be pure noise (124 of the 172 completions in the week
            # before the certifier shipped were upgrade-reports) and would train
            # people to route around the floor.
            #
            # My first draft gated every type and broke test_records_are_not_gated.
            # The distinction was already there, deliberate and documented; I had
            # simply not honoured it.
            # Write to `lug`, NOT to extra_fields: lug.update(extra_fields) already
            # ran above, so anything set on extra_fields here would be silently
            # dropped. Caught by tracing the write order rather than assuming it —
            # the first draft of this guard set extra_fields and would have enforced
            # nothing at all while appearing to.
            # A certification counts as evidence ONLY when the certifier actually
            # RAN here and checked something. That is the distinction basher's lug
            # turns on: autopilot supplies its own verdict, which skips the
            # certifier above, and letting a self-issued claim be its own proof is
            # the free pass they measured. But a certification this choke-point
            # produced, having executed the lug's verify steps, is the STRONGEST
            # evidence available — refusing it would reject exactly the work the
            # system verified hardest.
            #
            # My first draft got this backwards in both directions: it counted a
            # caller-supplied certification as evidence, and then refused a
            # genuinely-certified completion for want of a timestamp.
            def _ran_certification():
                c = lug.get("certification")
                if not isinstance(c, dict):
                    return False
                return bool(c.get("certified_checks")) or "choke-point" in str(
                    lug.get("certified_by") or "")

            _ev_keys = ("verification", "completion_note", "completion_notes",
                        "done_list", "evidence", "uat_evidence")

            def _present(key):
                v = lug.get(key)
                return bool(v) and str(v).strip() not in ("", "None", "null", "[]", "{}")

            _has_evidence = any(_present(k) for k in _ev_keys) or _ran_certification()
            _has_stamp = _present("completed_at")

            # A missing timestamp is a RECORDING gap the system can close itself,
            # and refusing a properly evidenced completion over it would punish the
            # wrong thing. Missing EVIDENCE is not recoverable that way — nobody can
            # reconstruct what was done. So: stamp the one, refuse the other.
            if _has_evidence and not _has_stamp:
                lug["completed_at"] = datetime.now(timezone.utc).isoformat()
                lug["completed_at_backfilled"] = True
                _has_stamp = True

            if not (_has_evidence and _has_stamp):
                _missing = ["evidence (" + " | ".join(_ev_keys[:5]) + ")"]
                status = "needs_attention"
                lug["status"] = status
                lug["s"] = status
                lug["unevidenced_completion"] = True
                lug["attention_reason"] = (
                    "COMPLETION REFUSED — the lug claimed completed but carries no "
                    + " and no ".join(_missing) + ". The work may well be real; the "
                    "RECORD is not, and an unevidenced completion cannot be told "
                    "apart from a false one. Add the evidence and re-complete."
                )

        # UAT-request-on-completion emission (impl-exitclarity-5): this method is
        # the single sanctioned entry point every completion transition funnels
        # through (see RULE 1 above), so it is the single choke-point to emit
        # from. Mutates `lug` in place (uat_status="awaiting_user") before the
        # write below persists it. Fail-safe: any error here must never block
        # the completion write itself.
        if status == "completed" and _UAT_REQUEST_AVAILABLE:
            try:
                _wf = lug.get("workflow") or {}
                ev = dict(uat_evidence or {})
                ev.setdefault("dispatch_method", _wf.get("dispatch_method"))
                ev.setdefault("grounded_verdict", _wf.get("grounded_verdict"))
                ev.setdefault("completed_at", _wf.get("completed_at"))
                emit_uat_request(
                    lug,
                    self._config.bytype_dir,
                    evidence=ev,
                    activity_log=activity_log,
                )
            except Exception:
                pass  # UAT emission must never block a completion write

        current_status_dir = lug_path.parent.name
        type_dir = lug_path.parent.parent
        new_status_dir = status.replace("-", "_")

        if current_status_dir != new_status_dir:
            new_dir = type_dir / new_status_dir
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / lug_path.name
            lug.pop("_file_path", None)
            lug.pop("_fs_status", None)
            lug.pop("_fs_type", None)
            new_path.write_text(json.dumps(lug, indent=2) + "\n")

            # Delete source file after successful write to completed/
            # Use Path.unlink(missing_ok=True) for safe deletion
            try:
                lug_path.unlink(missing_ok=True)

                # If spoke is a git repo, stage the deletion so it lands in the run commit
                try:
                    # Spoke root is two levels up from bytype (spoke_root/WAI-Spoke/lugs/bytype)
                    spoke_root = self._config.spoke_path.parent.parent
                    if spoke_root and spoke_root.exists():
                        git_check = subprocess.run(
                            ["git", "rev-parse", "--git-dir"],
                            cwd=str(spoke_root),
                            capture_output=True,
                            timeout=5,
                            text=True,
                        )
                        if git_check.returncode == 0:
                            # We're in a git repo — stage the deletion
                            rel_path = lug_path.relative_to(spoke_root)
                            subprocess.run(
                                ["git", "rm", "--cached", str(rel_path)],
                                cwd=str(spoke_root),
                                capture_output=True,
                                timeout=5,
                            )
                except (subprocess.TimeoutExpired, OSError, FileNotFoundError, ValueError):
                    # Git not available or command failed — that's ok, file is already deleted
                    pass
            except OSError:
                # If deletion fails, the write succeeded so return True (best effort cleanup)
                pass
        else:
            lug.pop("_file_path", None)
            lug.pop("_fs_status", None)
            lug.pop("_fs_type", None)
            lug_path.write_text(json.dumps(lug, indent=2) + "\n")

        return True

    def log_changelog(self, entry: Dict[str, Any]) -> None:
        changelog = self._config.changelog_file
        if not changelog.exists():
            changelog.parent.mkdir(parents=True, exist_ok=True)
            changelog.touch()
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        entry.setdefault("session_key", self._config.session_key())
        with open(changelog, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
