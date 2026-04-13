"""Quest node — manages quest state transitions and progress tracking.

Reads quest definitions from state["quests"] (story config JSON).
Reads/writes state["_quest_state"] for runtime quest statuses.

On each turn:
  - Check locked → available transitions (required_quests, required_progression, required_location)
  - Auto-start available quests with auto_start=True
  - Check active quest progress against completion_criteria
  - Apply on_completion effects (unlock_quests, modify_characters)
  - Write _quest_narrator_hint on status changes
  - Write _active_quests list for UI

Quest definition lives in state["quests"]:
  {
    "quest_id": {
      "title": "...",
      "quest_type": "main|side|character|location|collection",
      "required_quests": [...],
      "required_progression": {"char_key": min_stage_index},
      "required_location": "loc_key",
      "available_when": {"location": "...", "progression": {...}},
      "completion_type": "progression|task|composite",
      "completion_criteria": {...},
      "auto_start": true,
      "can_abandon": false,
      "is_repeatable": false,
      "on_completion": {"unlock_quests": [...], "modify_characters": {...}},
      "rewards": {...}
    }
  }

Runtime state lives in _quest_state:
  {
    "quest_id": {
      "status": "locked|available|active|completed|failed|abandoned|expired",
      "started_turn": 15,
      "progress_data": {},
      "milestones_reached": []
    }
  }
"""

import logging

logger = logging.getLogger(__name__)


def quest_node(state: dict) -> dict:
    """Manage quest state transitions and progress tracking."""
    quest_definitions = state.get("quests") or {}
    if not quest_definitions:
        return {}

    quest_state = dict(state.get("_quest_state") or {})
    location_state = state.get("_location_state") or {}
    progression_state = state.get("_progression_state") or {}
    current_location = location_state.get("current_location")
    turn_count = state.get("turn_count", 0)

    # Initialize state for any new quests
    for quest_id in quest_definitions:
        if quest_id not in quest_state:
            quest_state[quest_id] = {
                "status": "locked",
                "started_turn": None,
                "progress_data": {},
                "milestones_reached": [],
            }

    quest_hints = []

    for quest_id, quest_def in quest_definitions.items():
        qs = quest_state[quest_id]
        current_status = qs["status"]

        # locked → available
        if current_status == "locked":
            if _check_quest_available(quest_def, quest_state, progression_state, current_location):
                qs["status"] = "available"
                title = quest_def.get("title", quest_id)
                logger.info("Quest available: %s", quest_id)
                quest_hints.append(f"A new quest is now available: {title}.")

        # available → active (auto_start)
        if qs["status"] == "available" and quest_def.get("auto_start", False):
            qs["status"] = "active"
            qs["started_turn"] = turn_count
            title = quest_def.get("title", quest_id)
            logger.info("Quest auto-started: %s", quest_id)
            start_dialogue = quest_def.get("start_dialogue", "")
            hint = f"Quest started: {title}."
            if start_dialogue:
                hint += f" {start_dialogue}"
            quest_hints.append(hint)

        # active → completed
        if qs["status"] == "active":
            if _check_quest_completion(quest_def, state, qs):
                qs["status"] = "completed"
                title = quest_def.get("title", quest_id)
                logger.info("Quest completed: %s", quest_id)
                completion_dialogue = quest_def.get("completion_dialogue", "")
                hint = f"Quest completed: {title}!"
                if completion_dialogue:
                    hint += f" {completion_dialogue}"
                quest_hints.append(hint)
                _apply_quest_completion_effects(quest_def, quest_state, state)

    active_quests = [
        {"id": qid, "title": quest_definitions[qid].get("title", qid)}
        for qid, qs in quest_state.items()
        if qs["status"] in ("available", "active") and qid in quest_definitions
    ]

    result = {
        "_quest_state": quest_state,
        "_active_quests": active_quests,
    }
    if quest_hints:
        result["_quest_narrator_hint"] = " ".join(quest_hints)
        logger.info("Quest hints: %s", result["_quest_narrator_hint"])

    return result


def _check_quest_available(quest_def, quest_state, progression_state, current_location):
    """Check if a locked quest should become available."""
    for req_id in quest_def.get("required_quests", []):
        if quest_state.get(req_id, {}).get("status") != "completed":
            return False

    for char_key, min_stage in quest_def.get("required_progression", {}).items():
        if progression_state.get(char_key, {}).get("stage_index", 0) < min_stage:
            return False

    req_loc = quest_def.get("required_location")
    if req_loc and current_location != req_loc:
        return False

    available_when = quest_def.get("available_when", {})
    if available_when:
        if not _evaluate_conditions(available_when, progression_state, current_location):
            return False

    return True


def _check_quest_completion(quest_def, state, quest_state_data):
    """Check if an active quest's completion criteria are met."""
    completion_type = quest_def.get("completion_type", "task")
    criteria = quest_def.get("completion_criteria", {})

    if completion_type == "progression":
        return _check_progression_completion(criteria, state.get("_progression_state") or {})
    elif completion_type == "task":
        return _check_task_completion(criteria, state)
    elif completion_type == "composite":
        return _check_composite_completion(criteria, state, quest_state_data)
    return False


def _check_progression_completion(criteria, progression_state):
    """Check if a character has reached the target stage."""
    char_key = criteria.get("character")
    target_stage = criteria.get("target_stage", 0)
    maintain_for_turns = criteria.get("maintain_for_turns", 0)
    if not char_key:
        return False
    char_prog = progression_state.get(char_key, {})
    return (
        char_prog.get("stage_index", 0) >= target_stage
        and char_prog.get("turns_in_stage", 0) >= maintain_for_turns
    )


def _check_task_completion(criteria, state):
    """Check if a location task has been completed."""
    location_state = state.get("_location_state") or {}
    current_location = location_state.get("current_location")
    required_location = criteria.get("location")
    count = criteria.get("count", 1)

    if required_location and current_location != required_location:
        return False

    completed_tasks = location_state.get("completed_tasks", [])
    task_id = criteria.get("task_id")
    if task_id:
        return completed_tasks.count(task_id) >= count
    return len(completed_tasks) >= count


def _check_composite_completion(criteria, state, quest_state_data):
    """Check composite AND/OR criteria."""
    if "and" in criteria:
        return all(_check_single_criterion(c, state, quest_state_data) for c in criteria["and"])
    if "or" in criteria:
        return any(_check_single_criterion(c, state, quest_state_data) for c in criteria["or"])
    return False


def _check_single_criterion(criterion, state, quest_state_data):
    """Check a single criterion within composite criteria."""
    if "progression" in criterion:
        return _check_progression_completion(criterion["progression"], state.get("_progression_state") or {})
    if "task" in criterion:
        return _check_task_completion(criterion["task"], state)
    return False


def _evaluate_conditions(conditions, progression_state, current_location):
    """Evaluate available_when conditions dict."""
    if "location" in conditions and current_location != conditions["location"]:
        return False
    for char_key, min_stage in conditions.get("progression", {}).items():
        if progression_state.get(char_key, {}).get("stage_index", 0) < min_stage:
            return False
    return True


def _apply_quest_completion_effects(quest_def, quest_state, state):
    """Apply on_completion side effects."""
    on_completion = quest_def.get("on_completion", {})

    # Unlock quests
    for qid in on_completion.get("unlock_quests", []):
        if qid in quest_state and quest_state[qid]["status"] == "locked":
            quest_state[qid]["status"] = "available"
            logger.info("Quest unlocked by completion: %s", qid)

    # Advance character progression stages
    progression_state = state.get("_progression_state") or {}
    for char_key, changes in on_completion.get("modify_characters", {}).items():
        if "advance_stage" in changes and char_key in progression_state:
            progression_state[char_key]["stage_index"] = (
                progression_state[char_key].get("stage_index", 0) + changes["advance_stage"]
            )
            logger.info("Quest advanced %s stage by %d", char_key, changes["advance_stage"])
