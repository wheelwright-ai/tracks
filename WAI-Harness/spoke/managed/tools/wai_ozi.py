#!/usr/bin/env python3
"""Ozi - Chief of Staff work queue monitor.

Ruling 12 gives Ozi the OPERATIONAL half of onboarding: a new user must reach a clean
first session without knowing any WAI vocabulary. Ruling 26 says how that arrives --
ONE ranked list of work, never a wall of findings from a dozen separate instruments.

So Ozi's queue briefing is followed here by the first-look ranking: what the harness
can act on alone, and what needs the operator, in one order, with the reason attached.
Before this existed the ranking had no consumer, which is the difference between a
mechanism and a tool sitting in a drawer.
"""

import argparse
import os
import time
from typing import Any, Dict, List

from wai_ozi_config import OziConfig
from wai_ozi_scanner import OziScanner
from wai_ozi_briefing import OziBriefing
from wai_ozi_dispatch import OziDispatch


class OziWorkQueueMonitor:
    """Thin coordinator — composes OziConfig, OziScanner, OziBriefing, OziDispatch."""

    def __init__(self, spoke_path: str = "WAI-Spoke"):
        self._config = OziConfig(spoke_path)
        self._scanner = OziScanner(self._config)
        self._briefing = OziBriefing(self._config)
        self._dispatch = OziDispatch(self._config)

    # ── Config delegation ────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._config.is_enabled()

    def session_key(self) -> str:
        return self._config.session_key()

    def load_runtime_config(self) -> Dict[str, Any]:
        return self._config.load_runtime_config()

    def save_runtime_config(self, config: Dict[str, Any]) -> None:
        self._config.save_runtime_config(config)

    def is_auto_mode_enabled(self) -> bool:
        return self._config.is_auto_mode_enabled()

    def current_owner_name(self) -> str:
        return self._config.current_owner_name()

    # ── Scanner delegation ───────────────────────────────────────────────────

    def scan_work_queue(self) -> Dict[str, List[Dict[str, Any]]]:
        return self._scanner.scan_work_queue()

    # ── Briefing delegation ──────────────────────────────────────────────────

    def generate_briefing(self, queue: Dict[str, List[Dict[str, Any]]]) -> str:
        return self._briefing.generate_briefing(queue)

    # ── Dispatch delegation ──────────────────────────────────────────────────

    def auto_dispatch_work(self, queue: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        return self._dispatch.auto_dispatch_work(queue)

    def log_changelog(self, entry: Dict[str, Any]) -> None:
        self._dispatch.log_changelog(entry)


def ranked_next_actions(root: str = ".", refresh: bool = False) -> str:
    """Ozi prioritises: the first-look findings, folded into ONE ranked list.

    Reads the saved ranking when there is one and derives it when there is not, so a
    project that has never been looked at still gets an answer on its first session
    rather than an instruction to run something first (Ruling 12).

    Degrades to a short honest line, never an exception: Ozi runs at session start,
    and a session start that can fail on a ranking is a session start that gets
    disabled (Ruling 35).
    """
    try:
        import v5_walk  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return ""
    try:
        out_dir = v5_walk.walk_dir(root)
        priorities = None
        if not refresh:
            priorities = v5_walk._read_json(os.path.join(out_dir, v5_walk.NEXT_ACTIONS))
        if not priorities:
            result = v5_walk.walk(root)
            priorities = result.pop("_priorities", {})
        lines = ["", "WHAT COMES FIRST"]

        # Ruling 39: never present an order without naming what produced it. A stance
        # gets one line saying so; no stance gets the cost-and-risk statement, because
        # the failure this prevents is a confident priority the tool cannot justify.
        spec = v5_walk.STANCES.get(priorities.get("stance"))
        if spec:
            lines.append(f"  (ordered for {spec['label']})")
        else:
            lines.append("  (ordered by cost and risk only -- nothing here knows what "
                         "this project is for)")

        needs_you = priorities.get("needs_you", [])
        mine = priorities.get("i_can_do", [])
        if not needs_you and not mine:
            lines.append("  Nothing outstanding from the last review of this project.")
        for i, f in enumerate(needs_you[:5], 1):
            lines.append(f"  {i}. [you] {f['plain']}")
        for i, f in enumerate(mine[:3], len(needs_you[:5]) + 1):
            lines.append(f"  {i}. [me]  {f['plain']}")

        # Ozi asks, once. Not a ceremony and not a gate: the ranked list above is
        # already complete and already usable, and the question sits underneath it.
        if v5_walk.should_ask_stance(root):
            lines.append("")
            lines.append(v5_walk.stance_question())
        return v5_walk.plain_guard("\n".join(lines))
    except Exception:  # noqa: BLE001
        return ""


def run_cycle(ozi: OziWorkQueueMonitor) -> int:
    queue = ozi.scan_work_queue()
    print(ozi.generate_briefing(queue))
    ranked = ranked_next_actions(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    if ranked:
        print(ranked)

    dispatched_count = 0
    if ozi.is_auto_mode_enabled():
        dispatched = ozi.auto_dispatch_work(queue)
        dispatched_count = len(dispatched)
        if dispatched:
            print("")
            print("🤖 DISPATCHED NOW")
            for lug_id in dispatched:
                print(f"  • {lug_id}")
    return dispatched_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch", action="store_true", help="poll in a loop for ready work"
    )
    args = parser.parse_args()

    ozi = OziWorkQueueMonitor()
    if not ozi.is_enabled():
        print("ℹ️  Ozi work queue monitoring is disabled")
        print("   Enable with: wai skill enable ozi-work-queue-monitor")
        return

    if args.watch:
        config = ozi.load_runtime_config()
        interval_minutes = int(config.get("poll_interval_minutes", 5))
        print(
            f"👀 Ozi watch mode active for {ozi.session_key()} ({interval_minutes} min poll)"
        )
        while True:
            run_cycle(ozi)
            time.sleep(max(1, interval_minutes) * 60)
    else:
        run_cycle(ozi)


if __name__ == "__main__":
    main()
