<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { SUBGRAPHS_MD_STATIC } from '$lib/trainingDocs';
</script>

<svelte:head>
	<title>Subgraphs — RPG Engine Docs</title>
</svelte:head>

<section class="docs">
	<p class="breadcrumb"><a href="/docs">Docs</a> / Subgraphs</p>
	<div class="doc-hero">
		<img src="/images/graph-empty.png" alt="Graph blueprint illustration" />
	</div>
	<h1>Subgraphs</h1>
	<p class="lede">
		How the builtin pipelines differ, what each one is for, and how to pick one when you create or edit a story.
	</p>

	<div class="doc-actions">
		<a href={SUBGRAPHS_MD_STATIC} class="md-doc-btn md-doc-btn-primary">
			<Icon name="file-text" size={18} />
			<span>Open <code>SUBGRAPHS.md</code></span>
		</a>
		<a
			href="https://github.com/mcgowee/rpg-engine-basic/blob/main/docs/SUBGRAPHS.md"
			class="md-doc-btn md-doc-btn-ghost"
			target="_blank"
			rel="noopener noreferrer"
		>
			<span>View on GitHub</span>
			<Icon name="external" size={14} />
		</a>
	</div>

	<div class="section">
		<h2>What is a subgraph?</h2>
		<p>
			A <strong>subgraph</strong> is the LangGraph pipeline that runs on every turn: which <strong>nodes</strong> execute
			(narrator, mood, NPC, condense, memory, …) and in what order. You choose one per story in the Story Editor
			(<strong>Subgraph</strong> on the Subgraph tab). Builtin definitions live in <code>graphs/*.json</code>; you can
			also build custom subgraphs in the <a href="/graphs">Graph Editor</a>.
		</p>
	</div>

	<div class="section">
		<h2>Quick reference</h2>
		<div class="table-wrap">
			<table class="tbl">
				<thead>
					<tr>
						<th>Subgraph</th>
						<th>Pipeline (simplified)</th>
						<th>Conditional?</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td><code>basic_narrator</code></td>
						<td>narrator → end</td>
						<td>No</td>
					</tr>
					<tr>
						<td><code>conversation</code></td>
						<td>narrator → memory → end</td>
						<td>No</td>
					</tr>
					<tr>
						<td><code>full_conversation</code></td>
						<td>narrator → condense → memory → end</td>
						<td>No</td>
					</tr>
					<tr>
						<td><code>smart_conversation</code></td>
						<td>narrator → (npc → coda <span class="or">or</span> condense) → memory → end</td>
						<td>Yes</td>
					</tr>
					<tr>
						<td><code>full_memory</code></td>
						<td>narrator → mood → npc → condense → memory → end</td>
						<td>No</td>
					</tr>
					<tr>
						<td><code>full_story</code></td>
						<td>narrator → (mood → npc → coda <span class="or">or</span> condense) → memory → end</td>
						<td>Yes</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="hint">
			When <strong>conditional</strong> routing is on, the router <code>route_after_narrator</code> checks whether the story has
			<strong>characters</strong>. If yes, the graph continues along the NPC path (and mood where present); if no, it jumps to
			<code>condense</code> and skips nodes that only make sense with a cast.
		</p>
	</div>

	<div class="section">
		<h2>What each subgraph does</h2>
		<div class="table-wrap">
			<table class="tbl tbl-wide">
				<thead>
					<tr>
						<th>Subgraph</th>
						<th>What it does</th>
						<th>Good for</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td><code>basic_narrator</code></td>
						<td>
							Runs <strong>only</strong> the narrator each turn and ends. Fast and simple (one LLM call), but no in-graph
							memory, condense, NPCs, or mood—each turn is isolated unless something outside this graph adds history.
						</td>
						<td class="col-good-for">
							One-shots, demos, tutorials, quick experiments—anywhere you want the leanest turns and do not need in-graph memory.
						</td>
					</tr>
					<tr>
						<td><code>conversation</code></td>
						<td>
							Narrator, then <strong>memory</strong> appends the turn. Cheap (one narrator LLM per turn) and keeps raw
							history for context, but no <code>condense</code>, so no rolling AI “story so far” summary from this graph.
						</td>
						<td class="col-good-for">
							Short solo arcs, light continuity, prototyping—stories where raw history is enough and you want cheap per-turn cost.
						</td>
					</tr>
					<tr>
						<td><code>full_conversation</code></td>
						<td>
							Narrator, then <strong>condense</strong> builds a compressed summary, then <strong>memory</strong> stores the
							turn. Good for long solo arcs with a real memory summary, but two LLM calls per turn and no NPC or mood nodes.
						</td>
						<td class="col-good-for">
							Long solo campaigns, exploration, epics without a named cast—when you need a rolling summary but not NPCs or mood.
						</td>
					</tr>
					<tr>
						<td><code>smart_conversation</code></td>
						<td>
							<strong>Branches</strong> after the narrator: with characters, scene → NPC lines → <strong>narrator_coda</strong>
							(player prompt) → condense → memory; with no characters, narrator goes straight to condense → memory (skips NPC +
							coda). Flexible for solo or cast, but no mood tracking.
						</td>
						<td class="col-good-for">
							Mysteries, ensemble dialogue, heists with a crew—any NPC-heavy plot where you do not need character mood axes.
						</td>
					</tr>
					<tr>
						<td><code>full_memory</code></td>
						<td>
							<strong>Fixed</strong> chain: narrator → mood → NPC → condense → memory—no branch, no
							<code>narrator_coda</code>. Full mood + NPC + summary when you always have a cast; the path does not skip mood/NPC
							for empty casts (unlike <code>full_story</code>).
						</td>
						<td class="col-good-for">
							Relationship drama, emotional beats, fixed-party adventures—stories where the cast is always present and mood matters.
						</td>
					</tr>
					<tr>
						<td><code>full_story</code></td>
						<td>
							<strong>Branches</strong> after the narrator: with characters, mood → NPC → narrator_coda → condense → memory;
							with none, straight to condense → memory. Richest behavior with skips when there is no cast; most LLM work when the
							full path runs.
						</td>
						<td class="col-good-for">
							Full-featured games: mood + NPCs + post-scene player beat—works for solo or optional cast and scales down when no characters are defined.
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>

	<div class="section">
		<h2>One-line picker</h2>
		<ul class="picker">
			<li><strong>Minimal / tutorial:</strong> <code>basic_narrator</code></li>
			<li><strong>Solo + cheap memory:</strong> <code>conversation</code></li>
			<li><strong>Solo + long-term summary:</strong> <code>full_conversation</code></li>
			<li><strong>NPCs, no mood axes:</strong> <code>smart_conversation</code></li>
			<li><strong>Mood + NPCs, cast always:</strong> <code>full_memory</code></li>
			<li><strong>Mood + NPCs + coda, cast optional:</strong> <code>full_story</code></li>
		</ul>
	</div>

	<div class="section">
		<h2>Related</h2>
		<ul>
			<li><a href="/docs/stories">Creating Stories</a> — subgraph field and builtin story examples</li>
			<li><a href="/docs/engine">Engine Reference</a> — nodes, routers, and state</li>
			<li><a href="/graphs">Graph Editor</a> — build and test custom subgraphs</li>
		</ul>
	</div>

	<p class="nav-links">
		<a href="/docs">← Docs home</a> · <a href="/docs/engine">Engine Reference →</a>
	</p>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.breadcrumb { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.doc-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.doc-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.lede { color: #9aa0a6; margin: 0 0 1rem; line-height: 1.55; }
	.doc-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin: 0 0 1.5rem;
	}
	.md-doc-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.55rem 0.95rem;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none !important;
		transition: border-color 0.15s, background 0.15s, filter 0.15s;
	}
	.md-doc-btn-primary {
		background: #1a73e8;
		border-color: #1a73e8;
		color: #fff !important;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
	}
	.md-doc-btn-primary:hover {
		filter: brightness(1.08);
		border-color: #1a73e8;
	}
	.md-doc-btn-primary code {
		font-size: 0.85rem;
		font-weight: 600;
		color: #e8eaed !important;
		background: rgba(0, 0, 0, 0.2) !important;
	}
	.md-doc-btn-ghost {
		background: #1a1d23;
		border-color: #3c4043;
		color: #e8eaed !important;
	}
	.md-doc-btn-ghost:hover {
		border-color: #8ab4f8;
		background: #252a33;
	}
	:global([data-theme="light"]) .md-doc-btn-primary {
		background: #1a73e8;
		border-color: #1a73e8;
		color: #fff !important;
	}
	:global([data-theme="light"]) .md-doc-btn-primary code {
		color: #fff !important;
		background: rgba(255, 255, 255, 0.15) !important;
	}
	:global([data-theme="light"]) .md-doc-btn-ghost {
		background: #fff;
		border-color: #d1d5db;
		color: #1e293b !important;
	}
	:global([data-theme="light"]) .md-doc-btn-ghost:hover {
		border-color: #94a3b8;
		background: #f8fafc;
	}
	.section { margin-bottom: 2rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section p,
	.section li { line-height: 1.55; color: #bdc1c6; }
	.section ul { padding-left: 1.25rem; }
	.hint { font-size: 0.85rem; color: #9aa0a6; margin: 0.75rem 0 0; line-height: 1.5; }
	.table-wrap { overflow-x: auto; margin: 0.5rem 0; -webkit-overflow-scrolling: touch; }
	.tbl { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
	.tbl th,
	.tbl td { border: 1px solid #2a2f38; padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }
	.tbl th { background: #1a1d23; color: #9aa0a6; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; }
	.tbl code { font-size: 0.82rem; }
	.tbl-wide td:nth-child(2) { min-width: 14rem; }
	.tbl-wide .col-good-for { min-width: 12rem; }
	.or { color: #8ab4f8; font-weight: 600; font-size: 0.8rem; }
	.picker { margin: 0.25rem 0 0; }
	.picker li { margin-bottom: 0.35rem; }
	.nav-links { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #2a2f38; font-size: 0.9rem; }
	:global([data-theme="light"]) .section h2 { border-bottom-color: #dfe3e8; }
	:global([data-theme="light"]) .section p,
	:global([data-theme="light"]) .section li { color: #334155; }
	:global([data-theme="light"]) .hint { color: #64748b; }
	:global([data-theme="light"]) .tbl th { background: #f1f5f9; color: #4b5563; }
	:global([data-theme="light"]) .tbl th,
	:global([data-theme="light"]) .tbl td { border-color: #dfe3e8; }
	:global([data-theme="light"]) .nav-links { border-top-color: #dfe3e8; }
	:global([data-theme="light"]) .doc-hero { border-color: #dfe3e8; }
</style>
