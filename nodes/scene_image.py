"""Scene image node — matches the current turn against a gallery of pre-made images.

Runs after expression_picker. Portrait selection is handled by the
expression_picker node; this node only handles scene gallery matching.

Writes:
  _scene_image: {url, caption} — the matched scene image for the sidebar
  _shown_images: list of one-time image IDs already shown
"""

import logging

logger = logging.getLogger(__name__)


def scene_image_node(state: dict) -> dict:
    """Match scene images from the gallery against the current turn text."""
    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}
    story = state.get("story") or {}
    memory_summary = (state.get("memory_summary") or "").strip()

    # Combine all text from this turn for matching
    turn_text = narrator_text.lower()
    for resp in char_responses.values():
        if isinstance(resp, dict):
            turn_text += " " + (resp.get("dialogue") or "").lower()
            turn_text += " " + (resp.get("action") or "").lower()

    results = {}

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
