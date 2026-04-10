"""Scene image node — matches the current turn against a gallery of pre-made images.

Also picks the best character portrait variant based on mood + scene context.
Runs after response_builder so it can read the full turn output.

Writes:
  _scene_image: {url, caption} — the matched scene image for the sidebar
  _active_portraits: {char_key: "variant_url"} — current portrait per character
  _shown_images: list of one-time image IDs already shown
"""

import logging

logger = logging.getLogger(__name__)


def scene_image_node(state: dict) -> dict:
    """Match scene images and character portrait variants."""
    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}
    characters = state.get("characters") or {}
    story = state.get("story") or {}
    memory_summary = (state.get("memory_summary") or "").strip()

    # Combine all text from this turn for matching
    turn_text = narrator_text.lower()
    for resp in char_responses.values():
        if isinstance(resp, dict):
            turn_text += " " + (resp.get("dialogue") or "").lower()
            turn_text += " " + (resp.get("action") or "").lower()

    results = {}

    # --- Scene image matching ---
    gallery = story.get("scene_images") or []
    shown_images = list(state.get("_shown_images") or [])

    if gallery:
        best_match = None
        best_score = 0

        for img in gallery:
            if not isinstance(img, dict):
                continue
            img_id = img.get("id", "")

            # Skip one-time images already shown
            if img.get("one_time") and img_id in shown_images:
                continue

            score = _score_scene_match(turn_text, img, memory_summary)
            if score > best_score:
                best_score = score
                best_match = img

        # Threshold — only show if match is strong enough
        if best_match and best_score >= 2:
            results["_scene_image"] = {
                "url": best_match.get("url", ""),
                "caption": best_match.get("caption", ""),
                "id": best_match.get("id", ""),
            }
            if best_match.get("one_time"):
                shown_images.append(best_match["id"])
            results["_shown_images"] = shown_images
            logger.info("Scene image matched: %s (score=%s)", best_match.get("id"), best_score)

    # --- Character portrait matching ---
    portrait_updates = {}

    for char_key, char in characters.items():
        if not isinstance(char, dict):
            continue

        portraits = char.get("portraits")
        if not isinstance(portraits, dict) or not portraits:
            continue

        rules = char.get("portrait_rules")
        if not isinstance(rules, list):
            continue

        # Get current mood values
        moods = {}
        for axis in (char.get("moods") or []):
            if isinstance(axis, dict) and "axis" in axis and "value" in axis:
                moods[axis["axis"]] = axis["value"]

        # Get character's dialogue/action this turn for context
        char_resp = char_responses.get(char_key, {})
        char_text = turn_text
        if isinstance(char_resp, dict):
            char_text += " " + (char_resp.get("dialogue") or "").lower()
            char_text += " " + (char_resp.get("action") or "").lower()

        best_portrait = _pick_portrait(portraits, rules, moods, char_text)
        if best_portrait:
            portrait_updates[char_key] = best_portrait

    if portrait_updates:
        results["_active_portraits"] = portrait_updates
        logger.info("Portrait updates: %s", {k: v for k, v in portrait_updates.items()})

    return results


def _score_scene_match(turn_text: str, image: dict, memory_summary: str = "") -> float:
    """Score how well a scene image matches the current turn text."""
    score = 0.0

    # Tag matching — each matching tag = +1
    for tag in (image.get("tags") or []):
        if isinstance(tag, str) and tag.lower() in turn_text:
            score += 1.0

    # Trigger phrase — strong match
    trigger = (image.get("trigger") or "").strip().lower()
    if trigger:
        # Check for full trigger phrase
        if trigger in turn_text:
            score += 3.0
        elif trigger in memory_summary.lower():
            score += 1.0
        else:
            # Partial match — check individual words
            trigger_words = trigger.split()
            matches = sum(1 for w in trigger_words if w in turn_text)
            if matches >= len(trigger_words) * 0.6:
                score += 2.0

    # Priority bonus (0-10 scale, normalized)
    score += (image.get("priority") or 0) / 10.0

    return score


def _pick_portrait(
    portraits: dict,
    rules: list,
    moods: dict,
    turn_text: str,
) -> str | None:
    """Pick the best portrait variant based on rules, moods, and turn text."""
    best_variant = None
    best_score = 0

    for rule in rules:
        if not isinstance(rule, dict):
            continue

        variant = rule.get("use", "")
        if not variant or variant not in portraits:
            continue

        score = 0

        # Mood range matching
        mood_ranges = rule.get("mood", {})
        if isinstance(mood_ranges, dict) and mood_ranges:
            all_match = True
            for axis, range_val in mood_ranges.items():
                current = moods.get(axis)
                if current is None:
                    all_match = False
                    break
                if isinstance(range_val, list) and len(range_val) == 2:
                    if not (range_val[0] <= current <= range_val[1]):
                        all_match = False
                        break
                    # Bonus for how strongly it matches
                    mid = (range_val[0] + range_val[1]) / 2
                    score += 1.0 + (1.0 - abs(current - mid) / 5.0)
            if not all_match:
                continue

        # Tag matching
        tags = rule.get("tags", [])
        if isinstance(tags, list) and tags:
            tag_matches = sum(1 for t in tags if isinstance(t, str) and t.lower() in turn_text)
            if tag_matches > 0:
                score += tag_matches
            elif mood_ranges:
                pass  # Mood already matched, tags are optional bonus
            else:
                continue  # Tags required if no mood rules

        # Priority from rule
        score += (rule.get("priority") or 0) / 10.0

        if score > best_score:
            best_score = score
            best_variant = portraits[variant]

    return best_variant
