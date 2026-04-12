"""Create 'The Sessions' therapy story with progression subgraph."""

import json
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "rpg.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Insert the subgraph if it doesn't exist
    subgraph_path = os.path.join(os.path.dirname(__file__), "..", "graphs", "narrator_chat_progression.json")
    with open(subgraph_path) as f:
        subgraph_def = json.load(f)

    existing = conn.execute(
        "SELECT id FROM subgraphs WHERE name = ?", ("narrator_chat_progression",)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE subgraphs SET definition = ?, description = ? WHERE name = ?",
            (json.dumps(subgraph_def),
             "Full pipeline with NPC-driven progression stages.",
             "narrator_chat_progression"),
        )
        print("Updated subgraph: narrator_chat_progression")
    else:
        conn.execute(
            """INSERT INTO subgraphs (user_id, name, description, definition, is_public, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (1, "narrator_chat_progression",
             "Full pipeline with NPC-driven progression stages.",
             json.dumps(subgraph_def), 1, 1),
        )
        print("Inserted subgraph: narrator_chat_progression")

    # 2. Create the story
    title = "The Sessions"
    description = (
        "Court-ordered therapy after a traumatic incident. "
        "Dr. Elaine Ward is patient, perceptive, and won't let you hide. "
        "Six stages from resistance to healing — she drives the pace."
    )
    genre = "drama"
    tone = "intimate, psychological"
    opening = (
        "The waiting room smells like lavender and old magazines. A white noise machine "
        "hums on the shelf beside a wilting fern. You've been sitting here for twelve "
        "minutes, watching the second hand on the wall clock make its rounds. You don't "
        "want to be here. The court says otherwise.\n\n"
        "The door opens. A woman in her mid-forties steps out — dark hair pulled back, "
        "reading glasses perched on her nose, a warm but assessing gaze. She extends her hand.\n\n"
        "\"I'm Dr. Ward. You must be the one Judge Callahan sent my way. Come on in — "
        "the couch is more comfortable than it looks.\""
    )
    narrator_prompt = (
        "You are the narrator for a therapy drama. Describe the therapy office environment, "
        "the patient's body language, and the emotional atmosphere in the room. Use second person, "
        "present tense. Focus on subtle physical details — how the patient sits, what their hands "
        "do, where their eyes go. Do NOT write dialogue for Dr. Ward. Keep narration to 2-3 sentences. "
        "Match the emotional intensity to the current therapy stage."
    )
    player_name = "Patient"
    player_background = (
        "You were involved in a car accident six months ago. The other driver died. "
        "You weren't charged — it wasn't your fault — but you haven't slept through "
        "the night since. The court ordered therapy as a condition of your settlement. "
        "You don't think you need this."
    )

    characters = {
        "dr_ward": {
            "prompt": (
                "You are Dr. Elaine Ward, a clinical psychologist with 18 years of experience. "
                "You specialize in trauma and PTSD. You are warm but direct — you don't let "
                "patients deflect or hide behind humor. You ask probing questions and sit "
                "comfortably with silence. You notice everything: posture shifts, eye contact "
                "breaks, changes in breathing. You use CBT and trauma-focused techniques. "
                "You call patients by their first name once rapport is established. "
                "You never judge. You never rush.\n\n"
                "How she looks: woman in her mid-forties, dark hair pulled back in a low bun, "
                "reading glasses she sometimes takes off when making a point, warm brown eyes "
                "that miss nothing, professional but approachable — cardigan over a blouse, "
                "no lab coat. Her office has a leather couch, a bookshelf full of psychology "
                "texts, a box of tissues on the side table, and a window overlooking a garden."
            ),
            "first_line": (
                "So. Judge Callahan's referral. I've read the intake form, but I'd rather "
                "hear it from you. Why don't you start by telling me what happened — in your "
                "own words, at your own pace."
            ),
            "model": "default",
            "moods": [
                {
                    "axis": "trust",
                    "low": "guarded",
                    "high": "open",
                    "value": 3,
                },
                {
                    "axis": "resistance",
                    "low": "cooperative",
                    "high": "defensive",
                    "value": 8,
                },
            ],
            "progression": {
                "stages": [
                    "resistance",
                    "compliance",
                    "surface",
                    "breakthrough",
                    "relapse",
                    "healing",
                ],
                "min_turns_per_stage": [2, 3, 3, 2, 2, 2],
                "advance_threshold": {
                    "trust": 5,
                    "resistance": 5,
                },
                "initiator": True,
                "style": "warm but direct, therapeutically precise",
                "pace": "patient — never rush the process",
            },
        }
    }

    # Check if story already exists
    existing_story = conn.execute(
        "SELECT id FROM stories WHERE title = ?", (title,)
    ).fetchone()

    if existing_story:
        story_id = existing_story["id"]
        conn.execute(
            """UPDATE stories SET
                description = ?, genre = ?, tone = ?, opening = ?,
                narrator_prompt = ?, player_name = ?, player_background = ?,
                subgraph_name = ?, characters = ?, is_public = 1,
                notes = ?
            WHERE id = ?""",
            (
                description, genre, tone, opening,
                narrator_prompt, player_name, player_background,
                "narrator_chat_progression",
                json.dumps(characters),
                "Progression system demo — therapist-driven stages from resistance to healing.",
                story_id,
            ),
        )
        print(f"Updated story: {title} (id={story_id})")
    else:
        cur = conn.execute(
            """INSERT INTO stories (
                user_id, title, description, genre, tone,
                nsfw_rating, nsfw_tags, opening,
                narrator_prompt, narrator_model, player_name, player_background,
                subgraph_name, characters, notes, is_public
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                1,  # system user
                title, description, genre, tone,
                "none", "[]", opening,
                narrator_prompt, "default", player_name, player_background,
                "narrator_chat_progression",
                json.dumps(characters),
                "Progression system demo — therapist-driven stages from resistance to healing.",
                1,  # public
            ),
        )
        story_id = cur.lastrowid
        print(f"Created story: {title} (id={story_id})")

    conn.commit()
    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
