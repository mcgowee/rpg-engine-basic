"""Generate an HTML report from autoplay results.

Usage:
    python scripts/report_html.py results/autoplay_story10_*.json
    python scripts/report_html.py results/*.json --output results/report.html
"""

import argparse
import json
import os
import sys
from html import escape


def mood_color(value: int) -> str:
    """Map mood 1-10 to a color gradient."""
    if value <= 3:
        return "#f28b82"  # red
    elif value <= 5:
        return "#f6b93b"  # yellow
    elif value <= 7:
        return "#8ab4f8"  # blue
    else:
        return "#81c995"  # green


def generate_html(results_files: list[str]) -> str:
    all_results = []
    for fp in results_files:
        with open(fp) as f:
            data = json.load(f)
            data["_file"] = os.path.basename(fp)
            all_results.append(data)

    parts = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autoplay Report</title>
<style>
    * { box-sizing: border-box; margin: 0; }
    body { font-family: system-ui, sans-serif; background: #0f1114; color: #e8eaed; padding: 2rem; max-width: 1000px; margin: 0 auto; line-height: 1.5; }
    h1 { margin-bottom: 0.5rem; }
    h2 { margin: 2rem 0 0.75rem; font-size: 1.3rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
    h3 { margin: 1.5rem 0 0.5rem; font-size: 1.1rem; }
    .meta { color: #9aa0a6; font-size: 0.88rem; margin-bottom: 1.5rem; }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; margin: 1rem 0; }
    .stat-card { background: #1a1d23; border: 1px solid #2a2f38; border-radius: 8px; padding: 0.75rem; text-align: center; }
    .stat-value { font-size: 1.5rem; font-weight: 700; color: #8ab4f8; }
    .stat-label { font-size: 0.78rem; color: #9aa0a6; margin-top: 0.2rem; }
    .turn { background: #1a1d23; border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }
    .turn-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
    .turn-num { font-weight: 700; color: #8ab4f8; }
    .turn-time { font-size: 0.8rem; color: #9aa0a6; }
    .turn-msg { background: #13151a; border-left: 3px solid #1a73e8; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; border-radius: 4px; }
    .turn-msg-label { font-size: 0.75rem; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.05em; }
    .turn-resp { background: #13151a; border-left: 3px solid #81c995; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; border-radius: 4px; white-space: pre-wrap; font-size: 0.9rem; line-height: 1.6; }
    .turn-resp-label { font-size: 0.75rem; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.05em; }
    .mood-bar { display: flex; align-items: center; gap: 0.5rem; margin: 0.2rem 0; font-size: 0.85rem; }
    .mood-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    .mood-track { display: flex; gap: 2px; }
    .mood-pip { width: 20px; height: 12px; border-radius: 2px; font-size: 0.6rem; text-align: center; line-height: 12px; color: #000; font-weight: 600; }
    .memory-box { background: #13151a; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; color: #bdc1c6; font-style: italic; margin-top: 0.5rem; }
    .memory-label { font-size: 0.75rem; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.05em; }
    .issues { margin: 1rem 0; }
    .issue { background: #2a1515; border: 1px solid #5c2020; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.35rem; font-size: 0.85rem; color: #f28b82; }
    .no-issues { background: #1a2e1a; border: 1px solid #2a5a2a; border-radius: 6px; padding: 0.5rem 0.75rem; color: #81c995; font-size: 0.85rem; }
    .timing-bar { display: flex; align-items: center; gap: 0.5rem; margin: 0.3rem 0; }
    .timing-fill { height: 16px; background: #1a73e8; border-radius: 3px; min-width: 2px; }
    .timing-label { font-size: 0.78rem; color: #9aa0a6; min-width: 4rem; }
    .mood-timeline { margin: 1rem 0; }
    .mood-timeline h4 { font-size: 0.9rem; margin-bottom: 0.35rem; }
    .mood-row { display: flex; align-items: center; gap: 0.5rem; margin: 0.25rem 0; }
    .mood-axis-name { min-width: 7rem; font-size: 0.82rem; color: #9aa0a6; }
    .separator { border: none; border-top: 1px solid #2a2f38; margin: 2rem 0; }
</style>
</head>
<body>
<h1>Autoplay Report</h1>
"""]

    parts.append(f'<p class="meta">Generated from {len(all_results)} result file(s)</p>')

    for ri, data in enumerate(all_results):
        turns = data.get("turns", [])
        filename = data.get("_file", "?")

        if ri > 0:
            parts.append('<hr class="separator">')

        parts.append(f'<h2>{escape(filename)}</h2>')
        parts.append(f'<p class="meta">Story: {data.get("story_id", "?")} · Subgraph: {escape(str(data.get("subgraph", "?")))} · {len(turns)} turns</p>')

        # Summary cards
        times = [t["time_seconds"] for t in turns if "error" not in t]
        lengths = [t["response_length"] for t in turns if "error" not in t]

        parts.append('<div class="summary-grid">')
        parts.append(f'<div class="stat-card"><div class="stat-value">{data.get("total_time", 0):.1f}s</div><div class="stat-label">Total Time</div></div>')
        if times:
            parts.append(f'<div class="stat-card"><div class="stat-value">{sum(times)/len(times):.1f}s</div><div class="stat-label">Avg Turn</div></div>')
            parts.append(f'<div class="stat-card"><div class="stat-value">{min(times):.1f}s</div><div class="stat-label">Fastest Turn</div></div>')
            parts.append(f'<div class="stat-card"><div class="stat-value">{max(times):.1f}s</div><div class="stat-label">Slowest Turn</div></div>')
        if lengths:
            parts.append(f'<div class="stat-card"><div class="stat-value">{sum(lengths)//len(lengths)}</div><div class="stat-label">Avg Response Chars</div></div>')
        parts.append('</div>')

        # Timing bars
        if times:
            max_time = max(times) if times else 1
            parts.append('<h3>Turn Timing</h3>')
            for i, t in enumerate(turns):
                if "error" in t:
                    continue
                tt = t["time_seconds"]
                width = int((tt / max_time) * 300)
                parts.append(f'<div class="timing-bar"><span class="timing-label">Turn {i+1}</span><div class="timing-fill" style="width:{width}px"></div><span class="timing-label">{tt}s</span></div>')

        # Mood timeline
        mood_data = {}
        for i, t in enumerate(turns):
            for char, axes in t.get("moods", {}).items():
                if char not in mood_data:
                    mood_data[char] = {}
                for axis, val in axes.items():
                    if axis not in mood_data[char]:
                        mood_data[char][axis] = []
                    mood_data[char][axis].append(val)

        if mood_data:
            parts.append('<h3>Mood Timeline</h3>')
            for char, axes in mood_data.items():
                parts.append(f'<div class="mood-timeline"><h4>{escape(char.replace("_", " ").title())}</h4>')
                for axis, values in axes.items():
                    parts.append(f'<div class="mood-row"><span class="mood-axis-name">{escape(axis)}</span><div class="mood-track">')
                    for v in values:
                        color = mood_color(v)
                        parts.append(f'<div class="mood-pip" style="background:{color}">{v}</div>')
                    parts.append('</div></div>')
                parts.append('</div>')

        # Issues
        issues = []
        for i, t in enumerate(turns):
            resp = t.get("response", "")
            if "error" in t:
                issues.append(f"Turn {i+1}: ERROR — {t['error']}")
            if "[System error" in resp or "[The AI request failed" in resp:
                issues.append(f"Turn {i+1}: LLM error in response")
            if len(resp.strip()) < 20 and "error" not in t:
                issues.append(f"Turn {i+1}: Very short response ({len(resp)} chars)")
            if len(resp) > 3000:
                issues.append(f"Turn {i+1}: Very long response ({len(resp)} chars)")

        # Check stuck moods
        for char, axes in mood_data.items():
            for axis, values in axes.items():
                if len(values) > 1 and len(set(values)) == 1:
                    issues.append(f"{char.replace('_',' ').title()} — {axis} never changed ({values[0]}/10 for all {len(values)} turns)")

        parts.append('<h3>Issues</h3>')
        if issues:
            parts.append('<div class="issues">')
            for issue in issues:
                parts.append(f'<div class="issue">⚠ {escape(issue)}</div>')
            parts.append('</div>')
        else:
            parts.append('<div class="no-issues">✓ No issues detected</div>')

        # Turn-by-turn detail
        parts.append('<h3>Turn-by-Turn</h3>')
        for i, t in enumerate(turns):
            parts.append('<div class="turn">')
            parts.append(f'<div class="turn-header"><span class="turn-num">Turn {i+1}</span><span class="turn-time">{t.get("time_seconds", 0)}s · {t.get("response_length", 0)} chars</span></div>')

            parts.append(f'<div class="turn-msg"><div class="turn-msg-label">Player</div>{escape(t.get("message", ""))}</div>')

            if "error" in t:
                parts.append(f'<div class="issue">ERROR: {escape(str(t["error"]))}</div>')
            else:
                parts.append(f'<div class="turn-resp"><div class="turn-resp-label">Response</div>{escape(t.get("response", ""))}</div>')

            # Moods for this turn
            moods = t.get("moods", {})
            if moods:
                for char, axes in moods.items():
                    for axis, val in axes.items():
                        color = mood_color(val)
                        parts.append(f'<div class="mood-bar"><span class="mood-dot" style="background:{color}"></span>{escape(char.replace("_"," ").title())} — {escape(axis)}: {val}/10</div>')

            # Memory
            mem = t.get("memory_summary", "")
            if mem:
                parts.append(f'<div class="memory-box"><div class="memory-label">Memory Summary</div>{escape(mem)}</div>')

            parts.append('</div>')

    parts.append('</body></html>')
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report from autoplay results")
    parser.add_argument("files", nargs="+", help="Result JSON files")
    parser.add_argument("--output", help="Output HTML file path")
    args = parser.parse_args()

    valid_files = [f for f in args.files if os.path.exists(f)]
    if not valid_files:
        print("No valid files found")
        sys.exit(1)

    html = generate_html(valid_files)

    if args.output:
        output_path = args.output
    else:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "report.html")

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report saved to {output_path}")
    print(f"Open in browser: file://{os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
