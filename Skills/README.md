# Skills

`Skills/` is the authoritative skill architecture for this spoke.

## Rules

- Each routed capability lives in `Skills/<skill-id>/`.
- Each skill folder owns its `SKILL.md` and `command.md`.
- `Skills/index.jsonl` is the router of record.
- `Skills/index.jsonl` also owns canonical `legacy_aliases` mapping.
- Legacy files under `WAI-Spoke/commands/` are compatibility aliases only.
- `WAI-Spoke/WAI-Skills.jsonl` is a mirror-only compatibility registry for spoke-local consumers.
- Router filenames stay lowercase (`index.jsonl`); skill definition files stay uppercase (`SKILL.md`).

## Target Layout

```text
Skills/
  index.jsonl
  README.md
  SCHEMA.md
  wakeup/
    SKILL.md
    command.md
  closeout/
    SKILL.md
    command.md
  track-generate/
    SKILL.md
    command.md
  chat-to-track/
    SKILL.md
    command.md
  advisors/
    SKILL.md
    stewardship/
      SKILL.md
      advisor.json
      command.md
    complexity/
      SKILL.md
      advisor.json
      command.md
    context/
      SKILL.md
      advisor.json
      command.md
    foundation/
      SKILL.md
      advisor.json
      command.md
    signal/
      SKILL.md
      advisor.json
      command.md
    lug/
      SKILL.md
      advisor.json
      command.md
```

## Router Model

The router lists routable skills, not inheritance parents.

- Include one JSON object per line in `Skills/index.jsonl`.
- Use `skill_path` for the folder path.
- Use `skill_file` for the skill definition file; this should be `SKILL.md`.
- Use `entrypoint` for the default executable document; this should be `command.md`.
- Advisor entries should also declare `inherits_from` and `override_file`.
- Use `status` to reserve planned ids before downstream folders exist.

## Operating Model

- Change routing, activation, aliases, or inheritance metadata in `Skills/index.jsonl` first.
- Change behavior in the relevant skill folder.
- Keep `WAI-Spoke/WAI-Skills.jsonl` aligned only as a mirror of router data.
- Keep `WAI-Spoke/commands/*.md` short and compatibility-only; do not move behavior back into them.

See `Skills/SCHEMA.md` for the formal contract.
