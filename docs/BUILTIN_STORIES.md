# Builtin stories

These JSON files under `stories/` are imported on first-time DB seed (`db.py::seed_builtin_stories`) for the synthetic `system` user and are usually **public**. Each row demonstrates a different **subgraph** or cast size.

**Maintain this table** when you add, rename, or change a builtin story file.

Optional **`cover_image`** in each JSON: filename under `web/static/images/covers/` (e.g. `story_meet_cute.png`). On startup, **`sync_builtin_story_covers_from_disk()`** copies those filenames into the DB for the `system` user’s stories (matched by title).

| Story | File | Genre | Subgraph | NPCs | Notes |
|-------|------|-------|----------|-----:|-------|
| The Midnight Lighthouse | `midnight_lighthouse.json` | mystery | `conversation` | 0 | Default-style pipeline: narrator + memory, no condense/NPC. |
| The Last Train | `the_last_train.json` | thriller | `smart_conversation` | 2 | Two NPCs on a train. |
| Meet Cute (In Theory) | `meet_cute_in_theory.json` | romance | `smart_conversation` | 2 | Rom-com café date + barista; same subgraph as Last Train, different tone (tutorial + fun). |
| Open Mic Nightmare | `open_mic_nightmare.json` | comedy | `conversation` | 0 | Pure comedy; narrator + memory for callback jokes across turns. |
| The Job Interview | `the_job_interview.json` | drama | `full_story` | 2 | Mood axes on two interviewers + narrator coda. |
| The Interrogation | `the_interrogation.json` | thriller | `full_story` | 1 | One NPC with multiple mood axes. |
| Spy Thriller: Narrator Only | `undercover_1_narrator_only.json` | thriller | `basic_narrator` | 0 | Tutorial 1/5 — no in-graph memory between turns. |
| Spy Thriller: Rolling Memory | `undercover_2_with_memory.json` | thriller | `full_conversation` | 0 | Tutorial 2/5 — condense + rolling summary. |
| Spy Thriller: Meet the Handler | `undercover_3_meet_the_handler.json` | thriller | `smart_conversation` | 1 | Tutorial 3/5 — NPC + narrator coda. |
| Spy Thriller: Trust & Tension | `undercover_4_trust_and_tension.json` | thriller | `full_memory` | 1 | Tutorial 4/5 — mood axes + fixed mood→NPC chain. |
| Spy Thriller: Full Pipeline | `undercover_5_full_story.json` | thriller | `full_story` | 2 | Tutorial 5/5 — moods, two NPCs, coda, conditional routing. |

The **Spy Thriller** series (same embassy premise, **tutorials 1–5**) walks through progressively richer graphs. All five use the same card banner: **`covers/story_spy_rolling_memory.png`**. **Meet Cute** and **Open Mic Nightmare** add romance and comedy so Browse isn’t only mystery/thriller.

**Removed from defaults (redundant):** `blackrock_keeper.json` (overlapped Tutorial 3 for `smart_conversation`); `undercover_6_embassy_gala.json` (duplicate of Tutorial 5’s `full_story` demo).

See also: [SUBGRAPHS.md](SUBGRAPHS.md), [INDEX.md](INDEX.md).
