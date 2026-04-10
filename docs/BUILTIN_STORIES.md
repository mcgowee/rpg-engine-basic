# Builtin stories

These JSON files under `stories/` are imported on first-time DB seed (`db.py::seed_builtin_stories`) for the synthetic `system` user and are usually **public**. Each row demonstrates a different **subgraph** or cast size.

**Maintain this table** when you add, rename, or change a builtin story file.

Optional **`cover_image`** in each JSON: filename under `web/static/images/covers/` (e.g. `story_meet_cute.png`). On startup, **`sync_builtin_story_covers_from_disk()`** copies those filenames into the DB for the `system` user’s stories (matched by title).

| Story | File | Genre | Subgraph | NPCs | Notes |
|-------|------|-------|----------|-----:|-------|
| The Midnight Lighthouse | `midnight_lighthouse.json` | mystery | `narrator_chat_lite` | 0 | Solo mystery; narrator + memory, no condense/mood. |
| The Last Train | `the_last_train.json` | thriller | `narrator_chat` | 2 | Two characters on a train; full pipeline. |
| Meet Cute (In Theory) | `meet_cute_in_theory.json` | romance | `narrator_chat` | 2 | Rom-com café + barista; same pattern as Last Train. |
| Open Mic Nightmare | `open_mic_nightmare.json` | comedy | `narrator_chat_lite` | 0 | Comedy solo; structured history for callbacks. |
| The Job Interview | `the_job_interview.json` | drama | `narrator_chat` | 2 | Mood axes on two interviewers. |
| The Interrogation | `the_interrogation.json` | thriller | `narrator_chat` | 1 | One character, multiple mood axes. |
| Spy Thriller: Narrator Only | `undercover_1_narrator_only.json` | thriller | `narrator_chat_lite` | 0 | Tutorial 1/5 — lite pipeline, no cast. |
| Spy Thriller: Rolling Memory | `undercover_2_with_memory.json` | thriller | `narrator_chat` | 0 | Tutorial 2/5 — condense + rolling summary. |
| Spy Thriller: Meet the Handler | `undercover_3_meet_the_handler.json` | thriller | `narrator_chat` | 1 | Tutorial 3/5 — narrator + one character. |
| Spy Thriller: Trust & Tension | `undercover_4_trust_and_tension.json` | thriller | `narrator_chat` | 1 | Tutorial 4/5 — mood axes + dialogue. |
| Spy Thriller: Full Pipeline | `undercover_5_full_story.json` | thriller | `narrator_chat` | 2 | Tutorial 5/5 — two characters, full pipeline. |

The **Spy Thriller** series (same embassy premise, **tutorials 1–5**) walks through progressively richer setups. All five use the same card banner: **`covers/story_spy_rolling_memory.png`**. **Meet Cute** and **Open Mic Nightmare** add romance and comedy so Browse isn’t only mystery/thriller.

**Removed from defaults (redundant):** `blackrock_keeper.json`; `undercover_6_embassy_gala.json`.

See also: [SUBGRAPHS.md](SUBGRAPHS.md), [INDEX.md](INDEX.md).
