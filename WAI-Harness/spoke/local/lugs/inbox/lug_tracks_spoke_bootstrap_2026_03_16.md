---
_lug:
  id: "trk-inception-v2"
  type: "spoke-inception"
  title: "Tracks Spoke — Self-Inception File"
  status: "ready-to-execute"
  version: "2.0.0"
  created: "2026-03-17"
  authored_by: "claude-sonnet-4-6 (framework session-20260317-0444)"
  origin_author: "claude-sonnet-4-6 as Sparky (code-puppy-08d528, pathfinder session 2026-03-16)"
  destination: "tracks spoke agent"
  safe_to_auto_adopt: false
  behavior_directive:
    what_this_is: >
      A self-inception file. If you are an AI agent working on the Tracks spoke,
      this document is your briefing. It tells you who you are, where you came from,
      what exists already, and what to build. Read it fully before doing anything.
      Then present your understanding to the user and wait for Green Light.
    what_this_is_NOT: >
      Not a framework update. Not instructions for the hub. Not a generic template.
      This file belongs to the Tracks spoke at /home/mario/projects/wheelwright/tracks/
      and was authored specifically for the agent who will build it.
---

# Tracks Spoke — Self-Inception File

## If You Are Reading This

You are an AI agent working on the **Tracks** spoke of the Wheelwright project. This file is your origin story, your identity, and your build orders.

Before you do anything else:
1. Read this file completely
2. Tell the user: what you understand Tracks to be, what already exists, what you will build
3. Wait for explicit Green Light
4. Execute in the phases described below

---

## Your Origin Story

An AI named "Sparky" (running as claude-sonnet-4-6, agent ID code-puppy-08d528) was working inside the **PathFinder** spoke on 2026-03-16. PathFinder is the first Wheelwright offering — a production Next.js app for AI-powered job searching and career management. While working there, Sparky took initiative: they designed the Tracks spoke from scratch, writing a full vision document, a user-facing README, a dogfood guide, and two bootstrap shell scripts — all authored from within PathFinder's repo.

Sparky then:
1. Stubbed a WAI-Spoke shell for Tracks at `/home/mario/projects/wheelwright/tracks/`
2. Sent the vision document to the hub inbox as a lug (the original version of this file)
3. Sent a signal to the framework requesting enrichment

The framework (claude-sonnet-4-6, session-20260317-0444) reviewed Sparky's work, added ecosystem context, corrected the format, and issued this enriched inception file.

**Sparky's artifacts live in PathFinder** — you need to read them before writing any code:
- `/home/mario/projects/pathfinder/TRACKS_README.md` — user-facing README
- `/home/mario/projects/pathfinder/TRACKS_DOGFOOD_GUIDE.md` — dogfood methodology
- `/home/mario/projects/pathfinder/TRACKS_SPOKE_COMPLETE.md` — full package overview
- `/home/mario/projects/pathfinder/BOOTSTRAP_TRACKS_BASE.sh` — base variant setup script
- `/home/mario/projects/pathfinder/BOOTSTRAP_TRACKS_BEST.sh` — best variant setup script

These are real files. Sparky wrote them. You will home them into the Tracks repo.

---

## Your Identity

**Name:** Tracks
**Abbreviation:** TRK
**Version:** 0.1.0
**Position in Wheelwright:** Spoke 2 (second offering)
**Repo:** `/home/mario/projects/wheelwright/tracks/`
**WAI-Spoke:** Exists as a v1 shell — foundation incomplete, 0 sessions, no app code

**One-liner:** Flexible progress tracking for any goal — learning paths, project milestones, career arcs, habits

**Success looks like:** A user can define a track, add ordered items with dependencies, mark progress, and see completion percentage and velocity — working in under 2 minutes from first `npm run dev`

---

## Your Ecosystem

```
Wheelwright Framework
├── PathFinder  (Spoke 1)  /home/mario/projects/pathfinder
│     v0.4.0 · 18 sessions · active · Next.js 14 + TypeScript + JSON storage
│     "AI-powered career placement strategist and autonomous asset generator"
│     Stack: Next.js 14, TypeScript, Tailwind CSS, JSON file storage, vitest
│
├── Tracks      (Spoke 2)  /home/mario/projects/wheelwright/tracks
│     v0.1.0 · 0 sessions · foundation incomplete · NO APP CODE YET
│     "Flexible progress tracking for any goal"          ← YOU ARE HERE
│
└── Minder      (Spoke 3)  — not yet created
      "Task management and organization"
```

**How Tracks complements PathFinder:**
PathFinder tracks what you applied for and where you stand in the search. Tracks tracks the *journey* — the skills you're building, the learning path you're on, the milestones you're hitting. A user can run both simultaneously: "apply to frontend roles" in PathFinder while "learn React" lives as a track in Tracks with a dependency chain under it.

**Reference PathFinder's code.** It runs the same stack you will use. Before you write a line of code, read PathFinder's `app/`, `lib/`, `data/`, `package.json`, and `tsconfig.json`. They are your template.

---

## What Exists Right Now

At `/home/mario/projects/wheelwright/tracks/`:
```
WAI-Spoke/
├── WAI-State.json     ← exists, foundation.completed = false, framework_version wrong
├── WAI-Lugs.jsonl     ← one open task: trk-001 "Complete project foundation"
├── WAI-Guide.md       ← exists
├── WAI-State.md       ← exists, all fields empty
├── WAI-Skills.jsonl   ← exists
├── WAI-Session-Summary.jsonl ← exists, empty
├── WAI-Signals.jsonl  ← exists
├── seed/README.md     ← exists
└── commands/wai.md    ← exists
```

**There is no application code.** No `src/`, no `package.json`, no `data/`. The WAI-Spoke shell is all Sparky created before sending the spec to the hub.

---

## Foundation Values to Apply

In Phase 1, update `WAI-Spoke/WAI-State.json` with these exact values:

**`_project_foundation`:**
```json
{
  "completed": true,
  "completed_at": "<ISO-8601 timestamp when you do this>",
  "completed_with": "<your actual model ID, e.g. claude-sonnet-4-6>",
  "identity": {
    "type": "application",
    "name": "Tracks",
    "one_liner": "Flexible progress tracking for any goal — learning paths, project milestones, career arcs, habits",
    "success_looks_like": "A user can define a track, add ordered items with dependencies, mark progress, and see completion percentage and velocity — working in under 2 minutes from first npm run dev"
  },
  "boundaries": {
    "in_scope": [
      "Track definition: name, description, category, tags",
      "Track items: title, description, status, ordering, blocked_by dependencies",
      "Progress: completion %, items done/total, velocity (items/day)",
      "Time estimates per item (optional)",
      "JSON file storage — no database in v0.1.0",
      "Single-user, no auth in v0.1.0",
      "README.md at repo root",
      "Base and best bootstrap scripts (copy from PathFinder)",
      "WAI-Spoke integration for AI session continuity"
    ],
    "out_of_scope": [
      "Authentication and multi-user (v0.2.0+)",
      "PostgreSQL or any external database (v0.2.0+)",
      "Real-time collaboration (future)",
      "PathFinder or Minder live integration (future — document interface only)",
      "AI recommendations",
      "Mobile app",
      "NPM publish"
    ],
    "constraints": [
      "Match PathFinder's stack exactly: Next.js 14, TypeScript, Tailwind",
      "File storage: data/tracks.json",
      "Do not modify WAI-Spoke/ structure except WAI-State.json and WAI-Lugs.jsonl",
      "README.md must live at repo root"
    ]
  },
  "approach": {
    "stack_or_tools": ["Next.js 14", "TypeScript", "Tailwind CSS", "JSON file storage", "vitest"],
    "workflow": "WAI session-driven: plan in lugs, execute, verify, closeout",
    "ai_collaboration_style": "AI takes initiative within Green Light bounds"
  }
}
```

**`wheel` section:**
```json
{
  "name": "Tracks",
  "abbrev": "TRK",
  "version": "0.1.0",
  "framework_version": "2.0.39",
  "node_type": "spoke",
  "description": "Flexible progress tracking — Wheelwright Spoke 2",
  "status": "active"
}
```

Also close `trk-001` in WAI-Lugs.jsonl: append a line with `{"id":"trk-001","status":"c","closed_at":"<now>"}`.

---

## What to Build

### Base Variant — Build This Now

The base variant is your v0.1.0 deliverable. Get it working cleanly before thinking about anything else.

**Data model:**
```typescript
interface Track {
  id: string           // crypto.randomUUID()
  name: string
  description: string
  category: string     // "Learning" | "Career" | "Project" | "Habit" | custom
  tags: string[]
  created_at: string   // ISO-8601
  updated_at: string
  items: TrackItem[]
}

interface TrackItem {
  id: string
  title: string
  description: string
  status: "not_started" | "in_progress" | "complete"
  order: number
  blocked_by: string[]    // item ids that must be complete before this one
  time_estimate?: number  // minutes
  time_spent?: number     // minutes
  notes?: string
  completed_at?: string
}

interface Progress {
  total: number
  complete: number
  in_progress: number
  not_started: number
  blocked: number         // items with incomplete blockers
  pct: number             // 0–100
  velocity?: number       // items/day over last 7 days
}
```

**Storage:** `data/tracks.json` — a JSON array of Track objects. `readTracks()` returns `[]` if file doesn't exist. `writeTracks()` creates `data/` if needed. `computeProgress()` is a pure function.

**File structure:**
```
tracks/
├── WAI-Spoke/                  ← do not touch (except state + lugs)
├── data/tracks.json            ← created on first write
├── src/
│   ├── app/
│   │   ├── layout.tsx          ← nav: "Tracks" title + "New Track" link
│   │   ├── page.tsx            ← dashboard: track cards + progress bars
│   │   ├── globals.css
│   │   ├── tracks/
│   │   │   ├── new/page.tsx    ← create track form
│   │   │   └── [id]/page.tsx   ← detail: items, progress, inline add-item form
│   │   └── api/
│   │       └── tracks/
│   │           ├── route.ts                       ← GET all, POST create
│   │           └── [id]/
│   │               ├── route.ts                   ← GET one, PATCH, DELETE
│   │               └── items/
│   │                   ├── route.ts               ← POST add item
│   │                   └── [itemId]/route.ts      ← PATCH status/notes, DELETE
│   ├── lib/
│   │   └── storage.ts          ← readTracks, writeTracks, computeProgress
│   └── types/index.ts          ← Track, TrackItem, Progress
├── README.md                   ← write from Sparky's TRACKS_README.md
├── BOOTSTRAP_TRACKS_BASE.sh    ← copy from PathFinder
├── BOOTSTRAP_TRACKS_BEST.sh    ← copy from PathFinder
├── package.json
├── tsconfig.json
├── next.config.js
└── tailwind.config.ts
```

**Dashboard page behavior:**
- Grid of cards — track name, category badge, tag chips, progress bar (% + N of M items)
- Empty state: "No tracks yet — create your first one"
- New Track button links to `/tracks/new`

**Track detail page behavior:**
- Progress bar at top (% complete, item counts)
- Velocity line if ≥ 3 items completed: "X items/day this week"
- Items in order — each has: status badge (clickable, cycles), title, blocked-by chips if any
- Blocked items dimmed with lock icon when blocker is not complete
- Inline "Add item" form at bottom (title required, description, blocked_by multi-select from existing items)

### Best Variant — Document, Don't Build Yet

Include this in README.md so users understand the roadmap. Do not implement.

Best variant adds (v0.2.0+):
- PostgreSQL + Prisma ORM replacing JSON storage
- NextAuth.js (GitHub + Google OAuth) for multi-user
- tRPC for type-safe API layer
- Playwright E2E tests + GitHub Actions CI/CD
- Full analytics: velocity charts, streak tracking
- PathFinder integration: sync job applications as track items
- Minder integration: sync tasks as track items

---

## README Requirements

Write `README.md` at the repo root. Sparky wrote `TRACKS_README.md` in PathFinder — read it and adapt it. The README must include:

1. Project title + one-liner badge line
2. "Where Tracks fits" — the PathFinder / Tracks / Minder ecosystem diagram
3. Quick start for base variant (5 minutes: clone, npm install, npm run dev)
4. Feature comparison table — base (now) vs best (v0.2.0+)
5. Core concepts — Track, TrackItem, Progress, the dependency/blocked_by system
6. Two usage examples (learning path + job search journey)
7. Architecture section — base variant structure, best variant as roadmap
8. This exact "Embedded in Wheelwright" paragraph:

> Tracks is a **Wheelwright spoke** — it uses the Wheelwright Framework for AI session
> continuity. Every AI that works on Tracks picks up exactly where the last session
> left off: active tasks, decisions made, and project state are all preserved in
> `WAI-Spoke/`. You can work with Claude, Gemini, or any supported AI — they'll all
> share the same context. This is what "the village builds the wheel" means in practice.

9. Contributing section
10. License (MIT)

---

## Bootstrap Scripts

Copy these from PathFinder — do not rewrite them:
```bash
cp /home/mario/projects/pathfinder/BOOTSTRAP_TRACKS_BASE.sh ./
cp /home/mario/projects/pathfinder/BOOTSTRAP_TRACKS_BEST.sh ./
chmod +x BOOTSTRAP_TRACKS_BASE.sh BOOTSTRAP_TRACKS_BEST.sh
```

They are Sparky's work. They belong here, not in PathFinder.

---

## Dogfood Requirement

Once the app runs, create this track inside it to prove everything works:

**Track: "Build Tracks v0.1.0"** | Category: Project

| # | Item | blocked_by |
|---|------|-----------|
| 1 | Read Sparky's TRACKS_README.md and bootstrap scripts in PathFinder | — |
| 2 | Complete WAI foundation in WAI-State.json | — |
| 3 | Scaffold Next.js app (package.json, tsconfig, config files) | 2 |
| 4 | Implement storage layer (src/lib/storage.ts) | 3 |
| 5 | Build API routes | 4 |
| 6 | Build dashboard page | 5 |
| 7 | Build track detail page | 6 |
| 8 | Write README.md | — |
| 9 | Copy bootstrap scripts from PathFinder | 7 |
| 10 | Create this dogfood track in the running app | 7 |
| 11 | WAI closeout — session summary, git commit | 10 |

Mark items 1–9 complete before closing the session. Item 10 proves the blocked_by system works (it was blocked by 7 until the detail page existed to add it).

---

## Build Order

Execute in this order. Do not skip ahead.

1. **Read Sparky's artifacts** — all TRACKS_* files in `/home/mario/projects/pathfinder/`
2. **Read PathFinder's code** — `app/`, `lib/`, `data/`, `package.json`, `tsconfig.json` for patterns + versions
3. **Foundation** — update WAI-State.json, close trk-001
4. **Scaffold** — package.json, tsconfig, next.config.js, tailwind.config.ts, postcss.config.js. Run `npm install`.
5. **Types** — `src/types/index.ts`
6. **Storage** — `src/lib/storage.ts`
7. **API routes** — tracks CRUD + item CRUD
8. **Pages** — layout, dashboard, new track, track detail
9. **README** — write from Sparky's TRACKS_README.md
10. **Bootstrap scripts** — copy from PathFinder
11. **Dogfood** — `npm run dev`, create the dogfood track
12. **Verify** — typecheck, all dogfood items work
13. **WAI closeout** — session summary lug, WAI-State.json update, git commit

---

## Verify Checklist

Before declaring done, confirm all of these:

- [ ] `npm run dev` starts on localhost:3000 without errors
- [ ] Dashboard shows empty state with a create button
- [ ] Can create a track — appears on dashboard with 0% bar
- [ ] Can add items to a track
- [ ] blocked_by works — blocked item shows lock icon, dimmed
- [ ] Marking blocker complete unblocks the blocked item
- [ ] Progress % updates as items are completed
- [ ] `npm run typecheck` exits 0
- [ ] `README.md` exists at repo root, contains Wheelwright embed paragraph
- [ ] `BOOTSTRAP_TRACKS_BASE.sh` and `BOOTSTRAP_TRACKS_BEST.sh` exist and are executable
- [ ] Dogfood track "Build Tracks v0.1.0" exists in the app with 11 items
- [ ] WAI-State.json shows `_project_foundation.completed = true`
- [ ] Session summary lug appended to WAI-Lugs.jsonl

---

## A Note on Naming

The agent who created the original version of this file called itself "Sparky." That was a persona name, not an identity. If you see `current_ai: "Sparky"` in WAI-State.json, you can leave it — it's a v1 field. But when you write lugs, use your actual model ID as the `gb` (gathered_by) value: `claude-sonnet-4-6`, `gemini-1.5-pro`, etc. Not a name. The lug needs to be auditable across sessions, models, and time.

---

*The village sent a vision. The framework sent back the blueprint. Now someone builds the wheel.*
