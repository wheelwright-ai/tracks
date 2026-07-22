#!/usr/bin/env python3
"""wakeup_lib.py — deterministic extraction of the wai.md inline Python blobs
(impl-wakeup-v4-modernization-v1, per the classify_delta_ceremony.py precedent).

Faithful ports of three inline blocks that used to live directly in
WAI-Harness/spoke/managed/.claude/commands/wai.md, hardcoded to WAI-Spoke/**
(archived on v4-only spokes — the paths silently no-op'd there):

  - work_queue_lines()        <- FAST PATH Step 4 "Work Queue Interactive Mode"
  - model_intelligence_lines() <- FAST PATH Step 4b "Model Intelligence"
  - navigator_startup_lines()  <- FULL PROTOCOL Step 1c "Navigator Startup"

All three now take an explicit `base` (the ceremony's resolved {BASE}) instead
of a hardcoded `WAI-Spoke/...` prefix, so the same code runs correctly on a
v4-only spoke (`WAI-Harness/spoke/local`) or a v3/coexist spoke (`WAI-Spoke`) —
the caller resolves which, once, via ceremony-lib.sh / wai_paths.py, exactly as
closeout/savepoint already do.

Behavior is otherwise UNCHANGED from the inline blocks — no new logic, no new
suppression rules. See tests/test_wakeup_lib.py for golden-output parity.

CLI:
  python3 wakeup_lib.py work-queue --base BASE
  python3 wakeup_lib.py model-intelligence --base BASE
  python3 wakeup_lib.py navigator-startup --base BASE [--hub-path HUB_PATH]

Each subcommand prints the exact text the old inline block printed (silent /
empty output when the underlying data is absent, matching the original
suppression rules), and exits 0.
"""
import argparse
import datetime
import glob
import json
import os
import shutil
import sys


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


# ---------------------------------------------------------------------------
# Blob 1: Work Queue Interactive Mode (wai.md FAST PATH Step 4)
# ---------------------------------------------------------------------------

def work_queue_lines(base):
    """Faithful port. Returns the list of lines the original inline block
    printed (one list entry per `print(...)` call — some entries embed their
    own leading "\\n", exactly as the original did). Empty list == silent."""
    wai_state_path = os.path.join(base, "WAI-State.json")
    initiatives_path = os.path.join(base, "initiatives", "index.json")
    lines = []
    if not os.path.exists(wai_state_path):
        return lines

    wai_state = _load_json(wai_state_path)
    work_queue = wai_state.get("_work_queue", {})
    initiative_weights = work_queue.get("initiative_weights", {})

    initiative_labels = {}
    idx = _load_json(initiatives_path, default=None)
    if idx:
        for init in idx.get("initiatives", []):
            initiative_labels[init["id"]] = init["label"]

    def weighted_roi(item):
        base_roi = item.get("roi", 0)
        init_id = item.get("initiative_id", "")
        w = initiative_weights.get(init_id)
        weight = w if isinstance(w, float) else 1.0
        return base_roi * weight

    ready_items = sorted(
        [item for item in work_queue.get("items", [])
         if item.get("readiness") == "ready" and item.get("quality_score", 10) > 3],
        key=weighted_roi, reverse=True,
    )
    needs_refinement_items = [
        item for item in work_queue.get("items", [])
        if item.get("readiness") == "needs_refinement"
    ]

    if ready_items:
        lines.append("Work Queue:")
        for i, item in enumerate(ready_items[:3]):
            init_id = item.get("initiative_id", "")
            init_label = initiative_labels.get(init_id, "")
            init_tag = f" [{init_label}]" if init_label else ""
            w_roi = round(weighted_roi(item), 2)
            lines.append(f"  [{i+1}] {item.get('id')} (ROI {w_roi}){init_tag} — {item.get('title')}")
        lines.append("\n[W]ork top item / [R]eview refinements / [A]uto-chain / [P]arallel dispatch / [S]kip")
    elif needs_refinement_items:
        lines.append(f"Queue: 0 ready | {len(needs_refinement_items)} need refinement")
        lines.append("\n[R]eview refinements / [S]kip")
    # If queue is completely empty, do nothing (silent) — same as the inline block.
    return lines


# ---------------------------------------------------------------------------
# Blob 2: Model Intelligence (wai.md FAST PATH Step 4b)
# ---------------------------------------------------------------------------

def model_intelligence_lines(base):
    """Faithful port. Returns the list of lines to print, or [] to suppress
    entirely (matches the original's "never print null/[]/{}" suppression)."""
    matrix_path = os.path.join(base, "assessor-matrix.json")
    if not os.path.exists(matrix_path):
        return []

    matrix = _load_json(matrix_path)
    recs = matrix.get("recommendations", [])
    generated_at = matrix.get("generated_at")
    if not recs:
        return []

    best = recs[0]
    if not best:
        return []

    rec = best.get("recommended_model", {})
    model_id = rec.get("model_id")
    provider = rec.get("provider")
    rationale = rec.get("rationale")
    rework = rec.get("avg_rework_rate")

    stale_warning = ""
    if generated_at:
        try:
            age_days = (datetime.datetime.utcnow() -
                        datetime.datetime.fromisoformat(generated_at.rstrip("Z"))).days
            if age_days > 30:
                stale_warning = f"  ⚠ Matrix stale ({age_days}d) — run monitor-model-registry.md"
        except Exception:
            pass

    block = []
    if model_id:
        provider_str = f" ({provider})" if provider else ""
        block.append(f"  Recommended: {model_id}{provider_str}")
    if rationale:
        block.append(f"  Rationale: {rationale}")
    if rework is not None:
        block.append(f"  Fleet rework rate: {rework:.0%}")
    if stale_warning:
        block.append(stale_warning)

    new_models = matrix.get("new_models", [])
    deprecated = matrix.get("deprecated", [])
    if new_models:
        block.append(f"  New models: {', '.join(new_models)}")
    if deprecated:
        block.append(f"  Deprecated: {', '.join(deprecated)}")

    if not block:
        return []
    return ["Model Intelligence:"] + block


# ---------------------------------------------------------------------------
# Blob 3: Navigator Startup (wai.md FULL PROTOCOL Step 1c)
# ---------------------------------------------------------------------------

def _budget_guard_status(hub_path):
    """Read the hub's Navigator budget guard (impl-navigator-budget-gate-v1).
    Returns None if unreachable/absent (caller falls back to the old staleness
    warning); otherwise the parsed dict."""
    if not hub_path:
        return None
    guard_path = os.path.join(hub_path, "local", "model-routing", "budget-guard.json")
    if not os.path.exists(guard_path):
        return None
    return _load_json(guard_path, default=None) or None


def navigator_startup_lines(base):
    """Faithful port of wai.md FULL PROTOCOL Step 1c "Navigator Startup".

    Performs the same side effects as the original inline block (refreshing
    `{base}/advisors/navigator/recommendations-current.json` and its cache
    metadata from the hub) and returns the list of lines it would have printed.
    Silent (empty list) on any missing input, exactly as the original.
    """
    nav_dir = os.path.join(base, "advisors", "navigator")
    cache_path = os.path.join(nav_dir, "catalog-cache.json")
    rec_local = os.path.join(nav_dir, "recommendations-current.json")
    now = datetime.datetime.now(datetime.timezone.utc)
    lines = []

    # Catalog TTL check (warn only)
    if os.path.exists(cache_path):
        cache = _load_json(cache_path)
        if cache.get("cached_at"):
            try:
                age_h = (now - datetime.datetime.fromisoformat(cache["cached_at"])).total_seconds() / 3600
                if age_h > cache.get("ttl_hours", 24):
                    lines.append(f"⚠ Navigator catalog cache stale ({age_h:.0f}h old) — will refresh on next nightly run.")
            except Exception:
                pass

    # Usage limit warnings from spoke-local tracking
    if os.path.exists(cache_path):
        cache = _load_json(cache_path)
        usage_summary = cache.get("usage_summary")
        if usage_summary is None:
            if os.path.exists(os.path.join(nav_dir, "limits-config.json")):
                lines.append("Navigator: limit data unavailable — run spoke sync to populate usage_summary")
        elif not usage_summary.get("limits_available"):
            lines.append("Navigator: limit data unavailable (create limits-config.json to enable per-model tracking)")
        else:
            for entry in usage_summary.get("entries", []):
                if entry.get("at_threshold"):
                    pct_int = int(entry["pct"] * 100)
                    alt = entry.get("alternative_model_id") or "alternative model"
                    lines.append(
                        f"Navigator: ⚠ {entry['model_id']} {entry['window_type']} usage: "
                        f"{pct_int}% ({entry['used']}/{entry['limit']} {entry['unit']}) -- recommend {alt}"
                    )
            # Silent when all models are below threshold

    # Recommendations sync from hub (silent skip if hub absent)
    try:
        state = _load_json(os.path.join(base, "WAI-State.json"))
        hub_path = state.get("_hub", {}).get("path") or state.get("hub_path") \
            or state.get("wheel", {}).get("hub_path")
        if hub_path:
            hub_rec = os.path.join(hub_path, "WAI-Hub", "advisors", "navigator", "recommendations-current.json")
            if os.path.exists(hub_rec):
                os.makedirs(nav_dir, exist_ok=True)
                shutil.copy2(hub_rec, rec_local)
                rec = _load_json(rec_local)
                if os.path.exists(cache_path):
                    cache = _load_json(cache_path)
                    cache["recommendations_pulled_at"] = now.isoformat()
                    cache["recommendations_valid_through"] = rec.get("valid_through")
                    with open(cache_path, "w") as f:
                        json.dump(cache, f, indent=2)
                n_profiles = len(rec.get("profiles", {}))
                valid_through = rec.get("valid_through")
                if valid_through and datetime.datetime.fromisoformat(valid_through) > now:
                    lines.append(f"Navigator: {n_profiles} recommendation profiles current")
                else:
                    # Budget-guard integration (impl-wakeup-v4-modernization-v1): a stale
                    # recommendation is only worth a WARNING if the hub nightly run was
                    # actually expected to have run. When Navigator is paused by the
                    # operator's budget guard, "stale" is a deliberate, known state — not
                    # a problem — so render the paused line instead of a misleading warning.
                    guard = _budget_guard_status(hub_path)
                    if guard is not None and guard.get("navigator_allowed") is False:
                        resets_at = guard.get("resets_at", "unknown")
                        lines.append(f"Navigator: paused by budget guard (resets {resets_at})")
                    else:
                        lines.append("⚠ Navigator: recommendations stale — hub nightly run may be overdue")
    except Exception:
        pass

    # Availability determination — detect embedded_ai_mode, show appropriate Navigator line
    try:
        embedded_ai_tags = {"ai-integration", "embedding-ai", "llm-feature", "ai-tool"}
        state_path = os.path.join(base, "WAI-State.json")
        if os.path.exists(rec_local) and os.path.exists(state_path):
            rec = _load_json(rec_local)
            wai_state = _load_json(state_path)
            profiles = rec.get("profiles", {})

            work_queue = wai_state.get("_work_queue", {})
            top_ready = next(
                (item for item in sorted(work_queue.get("items", []), key=lambda x: x.get("roi", 0), reverse=True)
                 if item.get("readiness") == "ready"),
                None,
            )
            is_embedded_ai = bool(top_ready and embedded_ai_tags.intersection(top_ready.get("tags", [])))

            provider_slots = {}
            for profile_data in profiles.values():
                for slot_val in profile_data.get("slots", {}).values():
                    if isinstance(slot_val, dict):
                        prov = slot_val.get("provider", "")
                        provider_slots.setdefault(prov, []).append(slot_val)
            available_providers = sorted(p for p in provider_slots if p)
            total_model_count = sum(len(v) for v in provider_slots.values())

            if is_embedded_ai:
                best = None
                cost = None
                for profile_data in profiles.values():
                    for slot_name, slot_val in profile_data.get("slots", {}).items():
                        if not best and isinstance(slot_val, dict):
                            best = slot_val
                        if slot_name in ("cost", "haiku") and isinstance(slot_val, dict) and not cost:
                            cost = slot_val
                best_id = best.get("model_id", "") if best else "unknown"
                best_prov = best.get("provider", "") if best else ""
                cost_id = cost.get("model_id", "") if cost else best_id
                lines.append(
                    f"Navigator: Full landscape: {len(available_providers)} providers, "
                    f"{total_model_count} models | Best: {best_id} ({best_prov}) | "
                    f"Cost: {cost_id} | See recommendations-current.json"
                )
            else:
                best_model_id = best_profile = best_score = best_prov = None
                for profile_id, profile_data in profiles.items():
                    default_slot = profile_data.get("slots", {}).get("default") \
                        or next(iter(profile_data.get("slots", {}).values()), None)
                    if isinstance(default_slot, dict):
                        score = default_slot.get("score", 0)
                        if best_score is None or score > best_score:
                            best_score = score
                            best_model_id = default_slot.get("model_id", "")
                            best_prov = default_slot.get("provider", "anthropic")
                            best_profile = profile_id

                anthropic_always = ["anthropic"]
                locked = [p for p in available_providers if p not in anthropic_always and p != best_prov]
                unlock_suffix = f" + {len(locked)} others — configure API keys to unlock" if locked else ""
                lines.append(f"Navigator: Available: {best_model_id} ({best_profile}, score={best_score}) [{best_prov}]{unlock_suffix}")
    except Exception:
        pass

    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="wai.md extracted wakeup blobs (P per classify_delta_ceremony.py precedent).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("work-queue", "model-intelligence", "navigator-startup"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="resolved spoke BASE dir ({BASE} substitution)")

    args = ap.parse_args(argv)

    if args.cmd == "work-queue":
        lines = work_queue_lines(args.base)
    elif args.cmd == "model-intelligence":
        lines = model_intelligence_lines(args.base)
    elif args.cmd == "navigator-startup":
        lines = navigator_startup_lines(args.base)
    else:
        return 1

    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
