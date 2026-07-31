"""Drop-in deterministic detectors for the TasteGraph compliance oracle.

WHY A PACKAGE AND NOT MORE FUNCTIONS IN THE ORACLE. Coverage is meant to grow,
and growing it is naturally parallel work -- one preference, one detector, one
pair of tests. With every detector living in a single module, two authors adding
two detectors edit the same lines and collide. One file per detector makes the
growth path conflict-free, which is the difference between coverage that rises
and coverage that stalls at whatever one person wrote in one sitting.

CONTRACT. Each module exports:

    PREF_ID        str   the preference id it measures
    CLOSING_ONLY   bool  True to evaluate only the final substantial block
    EXTENDS        str   OPTIONAL — the id of a preference that already has a
                         detector, when this module is a SECOND proof for the
                         same preference rather than a new one
    detect(text, pref) -> list[{"evidence": str, "note": str}]

WHY `EXTENDS` EXISTS. One preference can need more than one proof, and the two
proofs are often different shapes: `wai-track-statusline-fidelity` has a built-in
that judges each statusline alone plus an extension that compares statuslines
across turns. Without `EXTENDS`, the second proof has nowhere to go — the loader
refuses to shadow the built-in, and a fresh PREF_ID names a preference the graph
does not contain, so the oracle would never call it. An extension is routed onto
the base preference's verdict instead: its findings count against the operator's
one real preference, which is the only thing the score is allowed to mean.

`detect` returns one dict per PROVEN violation, pointing at the offending
characters, and an empty list otherwise. It must be a pure deterministic function
of the text. No model judges anything here -- a detector that needs judgement is
a preference this tool should report UNMEASURABLE instead, and saying so is the
honest outcome, not a failure.
"""
import importlib
import pkgutil


def load():
    """Discover every detector module. Returns {pref_id: (fn, closing_only)}.

    Modules declaring `EXTENDS` are NOT in that mapping — they are second proofs
    for a preference that already has a detector, and are published separately as
    `load.extensions` ({base_pref_id: [fn, ...]}) for the oracle to run alongside
    the base detector.

    A broken module must not take the oracle down with it: the whole point is
    that measurement keeps happening. Import failures are skipped and surfaced by
    `errors()` rather than raised.
    """
    found, extensions, errs = {}, {}, []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_") or mod.name.startswith("test_"):
            continue
        try:
            m = importlib.import_module(f"{__name__}.{mod.name}")
            pid = getattr(m, "PREF_ID", None)
            fn = getattr(m, "detect", None)
            base = getattr(m, "EXTENDS", None)
            if pid and callable(fn):
                if base:
                    extensions.setdefault(base, []).append(fn)
                else:
                    found[pid] = (fn, bool(getattr(m, "CLOSING_ONLY", False)))
            else:
                errs.append(f"{mod.name}: missing PREF_ID or detect()")
        except Exception as exc:  # noqa: BLE001 - a bad plugin must not be fatal
            errs.append(f"{mod.name}: {type(exc).__name__}: {exc}")
    load.errors = errs
    load.extensions = extensions
    return found


load.errors = []
load.extensions = {}
