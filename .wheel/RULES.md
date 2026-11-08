# Wheel rules

These rules apply to every session working in this project.

1. Begin your first reply in a session with the line "Wheel rules loaded." alone on its own line, then a blank line, then your answer.
2. Never certify your own work. A separate session checks it.
3. Never discard uncommitted work, drop tables or delete project files with rm. The guard hook enforces this. Stash first, move files to the trash folder, ask the owner about data.
4. Commit only your own changes. Never run `git add -A` or `git add .` blindly; name the files. Never force-push and never skip hooks.
5. Keep tests green. Run them before you say a task is done, and say plainly if you could not.
6. Record what you did in the commit message: what changed, and why.
7. Ask the owner before anything hard to undo or outward-facing: pushing, publishing, deleting, sending, spending, changing shared settings.
8. Do not put secrets in any tracked file.
9. Keep the lugs, this project's work items (.wheel/backlog.jsonl; shown in .wheel/ROADMAP.md and .wheel/BACKLOG.md). Every write names who makes it with --by. When the owner asks for new work, add a lug: python3 .wheel/hooks/lug.py add TITLE --value 1-5 --effort 1-5 --kind owner|autopilot --source "the owner's words or this session" --initiative I-### --check "how done will be proven" --reason WHY --by WHO. It sorts by value and effort; compare it with its neighbours and, if your judgment differs, place it with --above/--below ID and say why. Every open lug belongs to one initiative (lug.py link ID I-###); an initiative serves one agreed goal and is written to the template (lug.py initiative add: outcome, why now, scope in and out, a checkable done when), and its lugs get no autopilot budget until the owner signs it off. Move a lug's status as work proceeds (ready, doing, checking, done, or dropped/blocked) with lug.py status ID STATUS --reason WHY --by WHO, and put the lug id in your commit messages. A separate session closes autopilot lugs. Run lug.py lint and lug.py verify before you finish.
