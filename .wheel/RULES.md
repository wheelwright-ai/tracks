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
9. Keep the backlog (.wheel/backlog.jsonl, shown in .wheel/BACKLOG.md). When the owner asks for new work, add it: python3 .wheel/hooks/backlog.py add TITLE --value 1-5 --effort 1-5 --kind owner|autopilot --source "the owner's words or this session" --check "how done will be proven" --reason WHY. It sorts by value and effort; compare it with its neighbours and, if your judgment differs, place it with --above/--below ID and say why. Move its status as work proceeds (ready, doing, checking, done, or dropped/blocked) with backlog.py status ID STATUS --reason WHY, and put the item id in your commit messages. A separate session closes autopilot items.
