"""B-003: spec and validator agree. Run: python3 -m unittest tests/test_validator.py"""
import copy, glob, json, os, re, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import validate_track as v

START = {"event": "session_start", "ts": "2026-03-17T13:04:00Z", "session_id": "x", "provider": "Claude",
         "model": "m", "mode": "active-collection", "continues": None}
POINT = {"turn": 1, "ts": "2026-03-17T13:05:00Z", "phase": "planning", "focus": "f", "action": "a",
         "thinking": "One. Two. Three."}
END = {"event": "session_end", "ts": "2026-03-17T13:06:00Z", "total_turns": 1, "summary": "s", "unresolved_count": 0}

def mut(base, **kw):
    d = copy.deepcopy(base)
    for k, val in kw.items():
        if val is DEL: d.pop(k, None)
        else: d[k] = val
    return d
DEL = object()

# rule id -> (lines, filename)
BROKEN = {
    "NAME-1": ([START, POINT, END], "bad-name.jsonl"),
    "STRUCT-1": (["not json", POINT], None),
    "STRUCT-2": ([POINT, END], None),
    "STRUCT-3": ([START, END, POINT], None),
    "START-1": ([mut(START, model=DEL), POINT], None),
    "START-2": ([mut(START, mode="bogus"), POINT], None),
    "START-3": ([mut(START, continues="WAI_Track-x.jsonl", continuation_gap_hours=3), POINT], None),
    "END-1": ([START, POINT, mut(END, summary=DEL)], None),
    "END-2": ([START, POINT, mut(END, total_turns=5)], None),
    "POINT-1": ([START, mut(POINT, action=DEL)], None),
    "POINT-2": ([START, mut(POINT, turn=2)], None),
    "POINT-3": ([START, mut(POINT, phase="napping")], None),
    "POINT-4": ([START, mut(POINT, thinking="Only one.")], None),
    "POINT-5": ([START, mut(POINT, ts="yesterday")], None),
    "COND-1": ([START, mut(POINT, fossils=["nope"])], None),
    "COND-2": ([START, mut(POINT, context_health={"usage_estimate": 0.3})], None),
}

def write(lines, name=None):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name or "WAI_Track-20260317-1304-Claude-m.jsonl")
    with open(p, "w") as f:
        for l in lines:
            f.write((l if isinstance(l, str) else json.dumps(l)) + "\n")
    return p

class T(unittest.TestCase):
    def test_every_rule_has_a_broken_fixture(self):
        self.assertEqual(set(BROKEN), set(v.RULES))

    def test_every_rule_is_in_the_spec(self):
        spec = open(os.path.join(ROOT, "spec", "track-format.md")).read()
        for rid in v.RULES:
            self.assertRegex(spec, r"\| %s \|" % re.escape(rid))
        self.assertEqual(set(re.findall(r"^\| ([A-Z]+-\d) \|", spec, re.M)), set(v.RULES))

    def test_good_fixture_passes(self):
        self.assertEqual(v.validate(write([START, POINT, END]), check_name=True), [])

    def test_broken_fixtures_fail_naming_the_rule(self):
        for rid, (lines, name) in BROKEN.items():
            with self.subTest(rule=rid):
                errs = v.validate(write(lines, name), check_name=(rid == "NAME-1"))
                self.assertIn(rid, [r for r, _ in errs])

    def test_all_samples_pass(self):
        samples = glob.glob(os.path.join(ROOT, "samples", "*.jsonl"))
        self.assertTrue(samples)
        for s in samples:
            with self.subTest(sample=s):
                self.assertEqual(v.validate(s), [])

if __name__ == "__main__":
    unittest.main()
