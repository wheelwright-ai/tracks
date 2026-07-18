"""Tests for herald_poll.py — the active cross-spoke comms daemon (MVP).

Uses a MOCK spawn_command_template so no real `claude -p` session is launched
(no cost, deterministic). Verifies: send→inbox, poll→spawn→responded, TTL expiry,
non-zero spawn leaves message pending for retry, and cross-spoke send delivery.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)
import herald_poll as H  # noqa: E402


def make_spoke(tmp, wheel_id):
    root = os.path.join(tmp, wheel_id)
    local = os.path.join(root, "WAI-Harness", "spoke", "local")
    os.makedirs(local, exist_ok=True)
    json.dump({"wheel_id": wheel_id}, open(os.path.join(local, "WAI-State.json"), "w"))
    return root


def set_spawn(root, template):
    cfg = H.load_config(root)
    cfg["spawn_command_template"] = template
    cfg["enabled"] = True
    H.save_config(root, cfg)


class HeraldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = make_spoke(self.tmp, "mywheel")

    def test_status_oneline_three_states(self):
        # inactive: not enabled, no pid
        self.assertTrue(H.status_oneline(self.root).startswith("inactive"))
        # enabled-idle: enabled, no live pid
        cfg = H.load_config(self.root); cfg["enabled"] = True; H.save_config(self.root, cfg)
        self.assertTrue(H.status_oneline(self.root).startswith("enabled-idle"))
        # running: a live pid present
        open(H._pid_path(self.root), "w").write(str(os.getpid()))
        line = H.status_oneline(self.root)
        self.assertTrue(line.startswith("running"))
        self.assertIn("queued", line)  # stable contract includes the inbox count

    def test_send_then_poll_responds(self):
        # mock spawn: succeed (exit 0)
        set_spawn(self.root, "true")
        msg = H._new_message("mywheel", "basher", "canon-sync", "apply v1.2",
                             "Apply the carve-out.", {"lug_id": "x"}, 0, None)
        dirs = H._dirs(self.root)
        json.dump(msg, open(os.path.join(dirs["inbox"], msg["id"] + ".json"), "w"))

        res = H.poll_once(self.root)
        self.assertEqual(res["responded"], 1, res)
        self.assertEqual(res["pending_seen"], 1)
        # message moved to processed, response captured, counters updated
        self.assertTrue(os.path.exists(os.path.join(dirs["processed"], msg["id"] + ".json")))
        self.assertFalse(os.path.exists(os.path.join(dirs["inbox"], msg["id"] + ".json")))
        self.assertTrue(os.path.exists(os.path.join(dirs["responses"], msg["id"] + ".json")))
        cfg = H.load_config(self.root)
        self.assertEqual(cfg["spawns_succeeded"], 1)
        self.assertIsNotNone(cfg["last_poll_at"])

    def test_ttl_expiry_not_spawned(self):
        set_spawn(self.root, "false")  # would fail if spawned
        dirs = H._dirs(self.root)
        msg = H._new_message("mywheel", "basher", "consult", "stale", "old", None, 0, None)
        msg["expires_at"] = "2000-01-01T00:00:00+00:00"  # long past
        json.dump(msg, open(os.path.join(dirs["inbox"], msg["id"] + ".json"), "w"))

        res = H.poll_once(self.root)
        self.assertEqual(res["expired"], 1, res)
        self.assertEqual(res["responded"], 0)
        self.assertTrue(os.path.exists(os.path.join(dirs["expired"], msg["id"] + ".json")))

    def test_failed_spawn_left_pending(self):
        set_spawn(self.root, "false")  # exit 1
        dirs = H._dirs(self.root)
        msg = H._new_message("mywheel", "basher", "consult", "q", "do x", None, 0, None)
        path = os.path.join(dirs["inbox"], msg["id"] + ".json")
        json.dump(msg, open(path, "w"))

        res = H.poll_once(self.root)
        self.assertEqual(res["failed"], 1, res)
        self.assertTrue(os.path.exists(path))  # still pending for retry
        reloaded = json.load(open(path))
        self.assertEqual(reloaded["status"], "pending")
        self.assertIn("last_error", reloaded)

    def test_disabled_skips(self):
        cfg = H.load_config(self.root)
        cfg["enabled"] = False
        H.save_config(self.root, cfg)
        res = H.poll_once(self.root)
        self.assertEqual(res["skipped"], "disabled")

    def test_cross_spoke_send_delivers_to_target_inbox(self):
        target = make_spoke(self.tmp, "basher")

        class A:  # argparse-ish
            spoke_root = self.root
            to = "basher"
            target_root = target
            from_spoke = None
            kind = "canon-sync"
            subject = "apply spec v1.2.0"
            body = "Codify lug-delivery carve-out fleet-wide."
            ref = "change-basher-codify-lug-delivery-always-allowed-fleet-v1"
            ttl_seconds = 0
            thread = None

        rc = H.cmd_send(A())
        self.assertEqual(rc, 0)
        inbox = H._dirs(target)["inbox"]
        files = [f for f in os.listdir(inbox) if f.endswith(".json")]
        self.assertEqual(len(files), 1)
        m = json.load(open(os.path.join(inbox, files[0])))
        self.assertEqual(m["to_spoke"], "basher")
        self.assertEqual(m["from_spoke"], "mywheel")
        self.assertEqual(m["ref"]["lug_id"], A.ref)
        self.assertEqual(m["status"], "pending")

    def test_address_filter_ignores_other_spoke(self):
        set_spawn(self.root, "true")
        dirs = H._dirs(self.root)
        msg = H._new_message("someone-else", "basher", "x", "y", "z", None, 0, None)
        json.dump(msg, open(os.path.join(dirs["inbox"], msg["id"] + ".json"), "w"))
        res = H.poll_once(self.root)
        self.assertEqual(res["pending_seen"], 0)
        self.assertEqual(res["responded"], 0)

    # --- session-lifecycle binding ---
    def test_singleton_lock_steals_stale_blocks_live(self):
        H._dirs(self.root)
        # a stale (dead) pid lock gets stolen
        open(H._pid_path(self.root), "w").write("999999")
        self.assertTrue(H._acquire_lock(self.root))
        self.assertEqual(H._read_pid(self.root), os.getpid())
        # a live pid (ourselves, but pretend other) blocks: write a definitely-live pid
        open(H._pid_path(self.root), "w").write(str(os.getppid()))
        self.assertFalse(H._acquire_lock(self.root))

    def test_active_session_count_zero_on_empty(self):
        os.makedirs(os.path.join(H.runtime_dir(self.root), "lanes"), exist_ok=True)
        self.assertEqual(H.active_session_count(self.root), 0)

    def test_start_noop_when_disabled(self):
        # default config is opt-in (enabled:false) -> start must not launch
        class A:
            spoke_root = self.root
            interval = None
            force = False
        rc = H.cmd_start(A())
        self.assertEqual(rc, 0)
        self.assertIsNone(H._read_pid(self.root))  # no daemon launched

    def test_start_is_idempotent_when_running(self):
        cfg = H.load_config(self.root)
        cfg["enabled"] = True
        H.save_config(self.root, cfg)
        # simulate a live daemon by writing our own (alive) pid
        open(H._pid_path(self.root), "w").write(str(os.getpid()))

        class A:
            spoke_root = self.root
            interval = None
            force = False
        rc = H.cmd_start(A())
        self.assertEqual(rc, 0)  # no-op, did not spawn a second
        self.assertEqual(H._read_pid(self.root), os.getpid())

    def test_run_until_idle_self_reaps(self):
        set_spawn(self.root, "true")
        os.makedirs(os.path.join(H.runtime_dir(self.root), "lanes"), exist_ok=True)  # 0 live

        class A:
            spoke_root = self.root
            interval = 0
            max = None
            force = True
            until_idle = True
            idle_ticks = 1
        rc = H.cmd_run(A())
        self.assertEqual(rc, 0)  # exited because no live session
        self.assertIsNone(H._read_pid(self.root))  # lock released on exit

    # --- watch: central incoming/ pickup with conservative active-flag gate ---
    def _make_target_with_lugs(self, wheel_id, lugs):
        wpath = os.path.join(self.tmp, wheel_id)
        inbox = os.path.join(wpath, "WAI-Harness", "spoke", "local", "lugs", "incoming")
        os.makedirs(inbox, exist_ok=True)
        for lug in lugs:
            json.dump(lug, open(os.path.join(inbox, lug["id"] + ".json"), "w"))
        return wpath

    def _wire_registry(self, wheels):
        reg = os.path.join(self.tmp, "hub-registry.json")
        json.dump({"wheels": wheels}, open(reg, "w"))
        cfg = H.load_config(self.root)
        cfg["enabled"] = True
        cfg["spawn_command_template"] = "true"  # mock spawn, no real claude
        cfg["hub_registry_path"] = reg
        H.save_config(self.root, cfg)

    def test_watch_fires_on_inferred_priority(self):
        # NO new fields — priority/impact already on the lug drive it
        wpath = self._make_target_with_lugs("alpha", [
            {"id": "impl-high", "type": "implementation", "priority": "high", "title": "do it"},
            {"id": "impl-impact", "type": "implementation", "impact": 9, "title": "big"},
            {"id": "impl-low", "type": "implementation", "priority": "low", "title": "later"},
            {"id": "notice-fyi", "type": "notice", "title": "fyi"},  # no priority -> low
        ])
        self._wire_registry([{"wheel_id": "alpha", "path": wpath}])
        cfg = H.load_config(self.root); cfg["max_concurrent_spawns"] = 5; H.save_config(self.root, cfg)

        res = H.watch_once(self.root)
        self.assertEqual(res["fired"], 2, res)         # high priority + high impact
        self.assertGreaterEqual(res["skipped_low"], 2)  # low + notice
        fired = H._load_fired(self.root)
        self.assertIn("alpha:impl-high", fired)
        self.assertIn("alpha:impl-impact", fired)
        self.assertNotIn("alpha:impl-low", fired)

    def test_watch_hygiene_drains_backlog(self):
        # a backlog of LOW-priority lugs over threshold -> one hygiene sweep
        lugs = [{"id": f"low-{i}", "type": "task", "priority": "low", "title": f"t{i}"} for i in range(12)]
        wpath = self._make_target_with_lugs("beta", lugs)
        self._wire_registry([{"wheel_id": "beta", "path": wpath}])
        cfg = H.load_config(self.root)
        cfg["hygiene_backlog_threshold"] = 10
        H.save_config(self.root, cfg)

        res = H.watch_once(self.root)
        self.assertEqual(res["fired"], 0)            # none are timely
        self.assertEqual(res["hygiene_fired"], 1, res)  # one sweep for the backlog
        self.assertIn("beta:__hygiene__", H._load_fired(self.root))
        # cooldown: a second immediate watch does not re-fire hygiene
        self.assertEqual(H.watch_once(self.root)["hygiene_fired"], 0)

    def test_watch_idempotent_no_refire(self):
        wpath = self._make_target_with_lugs("beta", [
            {"id": "impl-once", "type": "implementation", "priority": "critical", "title": "x"},
        ])
        self._wire_registry([{"wheel_id": "beta", "path": wpath}])
        self.assertEqual(H.watch_once(self.root)["fired"], 1)
        second = H.watch_once(self.root)
        self.assertEqual(second["fired"], 0)
        self.assertEqual(second["already_fired"], 1)

    def test_spawn_defaults_to_sonnet_and_honors_model(self):
        out = os.path.join(self.tmp, "model.txt")
        cfg = H.load_config(self.root)
        cfg["enabled"] = True
        cfg["spawn_command_template"] = 'echo "{model}" > ' + out
        H.save_config(self.root, cfg)
        msg = {"id": "m1", "thread_id": "t1"}
        H._spawn(cfg, msg, H._dirs(self.root))                       # default
        self.assertIn("sonnet", open(out).read())
        H._spawn(cfg, msg, H._dirs(self.root), model="claude-opus-4-8")  # explicit
        self.assertIn("opus", open(out).read())

    def test_responder_protocol_closes_the_loop(self):
        lug = {"id": "impl-z", "type": "implementation", "title": "do z", "source_spoke": "mywheel"}
        p = H._responder_protocol("basher", "basher:impl-z", lug, "mywheel")
        low = p.lower()
        self.assertIn("refinement", low)          # ambiguity -> ask back
        self.assertIn("verify", low)              # test before complete
        self.assertIn("never push to main", low)  # CSRP-safe push
        self.assertIn("confirm", low)             # acknowledge originator
        self.assertIn("mywheel", p)               # knows where to report back

    def test_watch_passes_lug_model_fit(self):
        out = os.path.join(self.tmp, "wmodel.txt")
        wpath = self._make_target_with_lugs("delta", [
            {"id": "impl-m", "type": "implementation", "priority": "high",
             "title": "x", "model_fit": "claude-opus-4-8"},
        ])
        self._wire_registry([{"wheel_id": "delta", "path": wpath}])
        cfg = H.load_config(self.root)
        cfg["spawn_command_template"] = 'echo "{model}" > ' + out
        H.save_config(self.root, cfg)
        H.watch_once(self.root)
        self.assertIn("opus", open(out).read())   # lug model_fit wins over sonnet default

    def test_watch_disabled_noop(self):
        wpath = self._make_target_with_lugs("gamma", [
            {"id": "impl-x", "type": "implementation", "priority": "high", "title": "x"},
        ])
        reg = os.path.join(self.tmp, "reg.json")
        json.dump({"wheels": [{"wheel_id": "gamma", "path": wpath}]}, open(reg, "w"))
        cfg = H.load_config(self.root); cfg["hub_registry_path"] = reg; H.save_config(self.root, cfg)
        self.assertEqual(H.watch_once(self.root).get("skipped"), "disabled")


if __name__ == "__main__":
    unittest.main()
