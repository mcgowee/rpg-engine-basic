"""Automated play session — sends messages to a story and logs all output.

Usage:
    python scripts/autoplay.py --story-id 5 --turns 5
    python scripts/autoplay.py --story-id 5 --messages "I look around" "I talk to the old man" "I ask about the lighthouse"
    python scripts/autoplay.py --story-id 5 --turns 10 --output results/test1.json

Logs every turn: prompt sent, narrator response, NPC dialogue, mood changes,
memory summary, timing. Useful for comparing models and tuning prompts.
"""

import argparse
import json
import os
import sys
import time

# Add parent dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Default messages if none provided
DEFAULT_MESSAGES = [
    "I look around carefully.",
    "I approach the nearest person.",
    "I ask them what's going on.",
    "I examine something interesting nearby.",
    "I decide to take action.",
    "I investigate further.",
    "I try something unexpected.",
    "I press for more information.",
    "I consider my options and act.",
    "I make my move.",
]

FLASK_URL = "http://localhost:5051"


def api(method, path, data=None, cookies=None):
    """Simple HTTP client for Flask API."""
    import urllib.request
    url = f"{FLASK_URL}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if cookies:
        headers["Cookie"] = cookies
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        resp_cookies = resp.headers.get("Set-Cookie", "")
        return json.loads(resp.read()), resp.status, resp_cookies
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code, ""
        except:
            return {"error": body}, e.code, ""


def main():
    parser = argparse.ArgumentParser(description="Automated play session")
    parser.add_argument("--story-id", type=int, required=True, help="Story ID to play")
    parser.add_argument("--turns", type=int, default=5, help="Number of turns to play")
    parser.add_argument("--messages", nargs="+", help="Custom messages (one per turn)")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--user", default="autoplay", help="Username (default: autoplay)")
    parser.add_argument("--password", default="autoplay123", help="Password")
    parser.add_argument("--flask-url", default=FLASK_URL, help="Flask API URL")
    parser.add_argument("--new-game", action="store_true", help="Force start a new game (ignore existing saves)")
    args = parser.parse_args()

    global FLASK_URL
    FLASK_URL = args.flask_url

    messages = args.messages or DEFAULT_MESSAGES[:args.turns]
    if len(messages) < args.turns:
        # Cycle messages if not enough
        while len(messages) < args.turns:
            messages.extend(DEFAULT_MESSAGES)
        messages = messages[:args.turns]

    print(f"=== Autoplay: story_id={args.story_id}, turns={args.turns} ===")
    print(f"Flask: {FLASK_URL}")
    print()

    # Register/login
    cookies = ""
    data, status, c = api("POST", "/register", {"uid": args.user, "password": args.password})
    if status == 201:
        cookies = c
        print(f"Registered as {args.user}")
    elif status == 409:
        data, status, c = api("POST", "/login", {"uid": args.user, "password": args.password})
        if status == 200:
            cookies = c
            print(f"Logged in as {args.user}")
        else:
            print(f"Login failed: {data}")
            sys.exit(1)

    # Start game
    if args.new_game:
        data, status, _ = api("POST", "/play/start", {"story_id": args.story_id}, cookies)
        if status != 200:
            print(f"Start failed: {data}")
            sys.exit(1)
        opening = data.get("response", "")
        print(f"\n--- Opening ---")
        print(opening[:300])
    else:
        # Try status first
        data, status, _ = api("GET", f"/play/status?story_id={args.story_id}", cookies=cookies)
        if status == 404:
            data, status, _ = api("POST", "/play/start", {"story_id": args.story_id}, cookies)
            if status != 200:
                print(f"Start failed: {data}")
                sys.exit(1)
            opening = data.get("response", "")
        else:
            opening = data.get("response", "")
        print(f"\n--- Opening ---")
        print(opening[:300])

    # Play turns
    results = {
        "story_id": args.story_id,
        "model": "",
        "subgraph": "",
        "turns": [],
        "total_time": 0,
    }

    total_start = time.time()

    for i, msg in enumerate(messages[:args.turns]):
        print(f"\n--- Turn {i + 1}/{args.turns} ---")
        print(f"Player: {msg}")

        turn_start = time.time()
        data, status, _ = api("POST", "/play/chat", {"story_id": args.story_id, "message": msg}, cookies)
        turn_time = time.time() - turn_start

        if status != 200:
            print(f"  ERROR: {data}")
            results["turns"].append({"message": msg, "error": str(data), "time": turn_time})
            continue

        response = data.get("response", "")
        turn_count = data.get("turn_count", 0)
        game_title = data.get("game_title", "")
        memory_summary = data.get("memory_summary", "")
        characters = data.get("characters", {})
        subgraph = data.get("subgraph_name", "")

        if not results["subgraph"]:
            results["subgraph"] = subgraph
        if not results["model"]:
            results["model"] = "default"

        # Extract mood info
        mood_info = {}
        for char_key, char_data in characters.items():
            if isinstance(char_data, dict):
                moods = char_data.get("moods", [])
                if moods:
                    mood_info[char_key] = {a["axis"]: a["value"] for a in moods if isinstance(a, dict)}
                elif "mood" in char_data:
                    mood_info[char_key] = {"mood": char_data["mood"]}

        turn_data = {
            "turn": i + 1,
            "message": msg,
            "response": response,
            "response_length": len(response),
            "turn_count": turn_count,
            "memory_summary": memory_summary,
            "moods": mood_info,
            "time_seconds": round(turn_time, 2),
        }
        results["turns"].append(turn_data)

        # Print summary
        print(f"  Response ({len(response)} chars, {turn_time:.1f}s):")
        # Show first 200 chars
        print(f"  {response[:200]}...")
        if mood_info:
            print(f"  Moods: {json.dumps(mood_info)}")
        if memory_summary:
            print(f"  Memory: {memory_summary[:100]}...")

    total_time = time.time() - total_start
    results["total_time"] = round(total_time, 2)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Completed {len(results['turns'])} turns in {total_time:.1f}s")
    turn_times = [t["time_seconds"] for t in results["turns"] if "error" not in t]
    if turn_times:
        print(f"Avg turn time: {sum(turn_times) / len(turn_times):.1f}s")
        print(f"Min: {min(turn_times):.1f}s, Max: {max(turn_times):.1f}s")
    resp_lengths = [t["response_length"] for t in results["turns"] if "error" not in t]
    if resp_lengths:
        print(f"Avg response length: {sum(resp_lengths) // len(resp_lengths)} chars")

    # Save results
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.output}")
    else:
        # Default output path
        output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
        os.makedirs(output_dir, exist_ok=True)
        ts = int(time.time())
        output_path = os.path.join(output_dir, f"autoplay_story{args.story_id}_{ts}.json")
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
