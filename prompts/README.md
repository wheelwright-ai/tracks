# Prompt variants

Which prompt to use, newest first. "Current" means the prompt lab's bench named it the winner. Nothing is current yet.

| Variant | File | Version | Status | Sample |
|---------|------|---------|--------|--------|
| WAI Track (full system prompt) | [`v4.0.0.md`](v4.0.0.md) | 4.0.0 | **latest, provisional**: not yet benchmarked by track-prompt-lab, so no winner is claimed | [`../samples/v4-session.jsonl`](../samples/v4-session.jsonl) |
| Closing request | [`closing-request.md`](closing-request.md) | v0.24 | recommended for a finished chat (see the README) | [`../samples/coding-session.jsonl`](../samples/coding-session.jsonl) |
| Prep and request | [`prep-and-request.md`](prep-and-request.md) | n/a | available | [`../samples/strategy-session.jsonl`](../samples/strategy-session.jsonl) |
| Active collection | [`active-collection.md`](active-collection.md) | n/a | available | [`../samples/learning-session.jsonl`](../samples/learning-session.jsonl) |

`v4.0.0.md` is a byte-for-byte copy of `prompts/v4.0.0.md` in track-prompt-lab. It is a full session-protocol prompt (chat and harness tiers), longer than the three single-purpose prompts. This table will mark one variant **current** once the bench names a winner.

Check any sample or your own file:

```bash
python3 tools/validate_track.py samples/*.jsonl
```

The v4 sample is written in the library's spec format (`spec/track-format.md`) so the validator can check it; it is an illustration, not a bench output.
