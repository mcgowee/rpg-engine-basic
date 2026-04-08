"""Analyze autoplay results — quality checks, timing, mood tracking, and issues.

Usage:
    python scripts/analyze_results.py results/autoplay_story10_*.json
    python scripts/analyze_results.py results/*.json --compare
"""

import argparse
import json
import os
import sys


def analyze_single(filepath: str) -> dict:
    """Analyze a single results file."""
    with open(filepath) as f:
        data = json.load(f)

    turns = data.get("turns", [])
    if not turns:
        return {"file": filepath, "error": "No turns"}

    report = {
        "file": os.path.basename(filepath),
        "story_id": data.get("story_id"),
        "subgraph": data.get("subgraph"),
        "total_time": data.get("total_time"),
        "num_turns": len(turns),
    }

    # Timing
    times = [t["time_seconds"] for t in turns if "error" not in t]
    if times:
        report["avg_time"] = round(sum(times) / len(times), 2)
        report["min_time"] = min(times)
        report["max_time"] = max(times)

    # Response quality metrics
    lengths = [t["response_length"] for t in turns if "error" not in t]
    if lengths:
        report["avg_response_length"] = sum(lengths) // len(lengths)
        report["min_response_length"] = min(lengths)
        report["max_response_length"] = max(lengths)

    # Issues detection
    issues = []

    for i, turn in enumerate(turns):
        if "error" in turn:
            issues.append(f"Turn {i+1}: ERROR — {turn['error']}")
            continue

        resp = turn.get("response", "")
        msg = turn.get("message", "")

        # Check for LLM errors in response
        if "[System error" in resp or "[The AI request failed" in resp:
            issues.append(f"Turn {i+1}: LLM error in response")

        # Check for empty response
        if len(resp.strip()) < 20:
            issues.append(f"Turn {i+1}: Very short response ({len(resp)} chars)")

        # Check for response too long (might be rambling)
        if len(resp) > 3000:
            issues.append(f"Turn {i+1}: Very long response ({len(resp)} chars) — model may be rambling")

        # Check for narrator speaking as NPC (shouldn't if graph has NPC node)
        # Look for quoted speech with attribution
        if "What do you do?" not in resp and "what do you do" not in resp.lower():
            pass  # Not always an issue — coda handles this

        # Check for repetition between turns
        if i > 0:
            prev_resp = turns[i-1].get("response", "")
            if prev_resp and resp:
                # Simple overlap check — first 100 chars
                overlap = resp[:100] == prev_resp[:100]
                if overlap:
                    issues.append(f"Turn {i+1}: Response starts identically to previous turn (possible repetition)")

        # Check for player message echoed in response
        if msg.lower() in resp.lower() and len(msg) > 10:
            issues.append(f"Turn {i+1}: Player message echoed in response")

    report["issues"] = issues

    # Mood tracking
    mood_changes = {}
    for i, turn in enumerate(turns):
        moods = turn.get("moods", {})
        for char, axes in moods.items():
            if char not in mood_changes:
                mood_changes[char] = {"axes": {}, "initial": {}}
            for axis, value in axes.items():
                if axis not in mood_changes[char]["axes"]:
                    mood_changes[char]["initial"][axis] = value
                    mood_changes[char]["axes"][axis] = [value]
                else:
                    mood_changes[char]["axes"][axis].append(value)

    # Check if moods actually changed
    mood_report = {}
    for char, data in mood_changes.items():
        char_report = {}
        for axis, values in data["axes"].items():
            initial = data["initial"][axis]
            final = values[-1]
            changed = any(v != initial for v in values)
            char_report[axis] = {
                "initial": initial,
                "final": final,
                "changed": changed,
                "values": values,
            }
            if not changed:
                issues.append(f"Mood '{axis}' for {char} never changed across {len(values)} turns")
        mood_report[char] = char_report
    report["mood_tracking"] = mood_report

    # Memory summary growth
    summaries = [t.get("memory_summary", "") for t in turns]
    summary_lengths = [len(s) for s in summaries]
    if summary_lengths:
        report["memory_summary_growth"] = summary_lengths
        if all(s == 0 for s in summary_lengths):
            issues.append("Memory summary never populated — condense may not be running")
        elif summary_lengths[-1] < summary_lengths[-2] if len(summary_lengths) > 1 else False:
            issues.append("Memory summary shrank — condense may be losing information")

    report["issues"] = issues
    report["issue_count"] = len(issues)

    return report


def print_report(report: dict):
    """Pretty-print a single analysis report."""
    print(f"\n{'=' * 70}")
    print(f"File: {report.get('file', '?')}")
    print(f"Story: {report.get('story_id')} | Subgraph: {report.get('subgraph')}")
    print(f"Turns: {report.get('num_turns')} | Total time: {report.get('total_time')}s")
    print(f"{'=' * 70}")

    if "error" in report:
        print(f"  ERROR: {report['error']}")
        return

    print(f"\nTiming:")
    print(f"  Avg: {report.get('avg_time', '?')}s | Min: {report.get('min_time', '?')}s | Max: {report.get('max_time', '?')}s")

    print(f"\nResponse length:")
    print(f"  Avg: {report.get('avg_response_length', '?')} chars | Min: {report.get('min_response_length', '?')} | Max: {report.get('max_response_length', '?')}")

    if report.get("mood_tracking"):
        print(f"\nMood tracking:")
        for char, axes in report["mood_tracking"].items():
            print(f"  {char}:")
            for axis, info in axes.items():
                arrow = "→" if info["changed"] else "="
                values_str = " → ".join(str(v) for v in info["values"])
                print(f"    {axis}: {info['initial']} {arrow} {info['final']}  ({values_str})")

    if report.get("memory_summary_growth"):
        growth = report["memory_summary_growth"]
        print(f"\nMemory summary growth: {' → '.join(str(g) for g in growth)} chars")

    issues = report.get("issues", [])
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print(f"\nNo issues detected ✓")


def compare_reports(reports: list):
    """Compare multiple reports side by side."""
    print(f"\n{'=' * 70}")
    print(f"COMPARISON: {len(reports)} results")
    print(f"{'=' * 70}")

    headers = ["Metric"] + [r.get("file", "?")[:25] for r in reports]
    rows = [
        ["Story ID"] + [str(r.get("story_id", "?")) for r in reports],
        ["Subgraph"] + [str(r.get("subgraph", "?"))[:20] for r in reports],
        ["Turns"] + [str(r.get("num_turns", "?")) for r in reports],
        ["Total time (s)"] + [str(r.get("total_time", "?")) for r in reports],
        ["Avg turn (s)"] + [str(r.get("avg_time", "?")) for r in reports],
        ["Avg response (chars)"] + [str(r.get("avg_response_length", "?")) for r in reports],
        ["Issues"] + [str(r.get("issue_count", 0)) for r in reports],
    ]

    col_widths = [max(len(str(row[i])) for row in [headers] + rows) + 2 for i in range(len(headers))]
    fmt = " | ".join(f"{{:{w}}}" for w in col_widths)

    print(fmt.format(*headers))
    print("-+-".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt.format(*row))


def main():
    parser = argparse.ArgumentParser(description="Analyze autoplay results")
    parser.add_argument("files", nargs="+", help="Result JSON files to analyze")
    parser.add_argument("--compare", action="store_true", help="Show comparison table")
    args = parser.parse_args()

    reports = []
    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue
        report = analyze_single(filepath)
        reports.append(report)
        if not args.compare:
            print_report(report)

    if args.compare and len(reports) > 1:
        compare_reports(reports)
    elif args.compare and len(reports) == 1:
        print_report(reports[0])


if __name__ == "__main__":
    main()
