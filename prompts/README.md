# Prompt variants

| Prompt | Status | Sample |
|---|---|---|
| [v4.0.0](v4.0.0.md) | **latest (provisional)**. Not yet benchmarked; not the current recommendation until track-prompt-lab's bench names a winner. | [samples/v4.0.0-example.jsonl](../samples/v4.0.0-example.jsonl) |
| [closing-request](closing-request.md) | current | [samples/coding-session.jsonl](../samples/coding-session.jsonl) |
| [prep-and-request](prep-and-request.md) | current | [samples/strategy-session.jsonl](../samples/strategy-session.jsonl) |
| [active-collection](active-collection.md) | current | [samples/learning-session.jsonl](../samples/learning-session.jsonl) |

`v4.0.0.md` is a verbatim copy of track-prompt-lab `prompts/v4.0.0.md` (sha256
`08734e613a51ee41c1635eba39c8c0ee2d79394c0c81d6e2bb056449ab47e990`). Its sample is a
hand-written illustration of the v4.0.0 turn shape, not a recorded run.

Check a track file: `python3 tools/validate_track.py samples/v4.0.0-example.jsonl`
