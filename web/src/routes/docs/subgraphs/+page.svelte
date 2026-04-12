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
			(progression, narrator, character_agent, response_builder, mood, expression_picker, scene_image, condense, memory) and in what order. You choose one per
			story in the Story Editor (<strong>Subgraph</strong> tab). Builtin definitions live in <code>graphs/*.json</code>; you can
			also build custom subgraphs in the <a href="/graphs">Graph Editor</a>. Graphs use <code>__start__</code> /
			<code>__end__</code> edges only — there are no routers.
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
					</tr>
				</thead>
				<tbody>
					<tr>
						<td><code>narrator_chat</code></td>
						<td>narrator → character_agent → response_builder → mood → expression_picker → scene_image → condense → memory → end</td>
					</tr>
					<tr>
						<td><code>narrator_chat_classic</code></td>
						<td>narrator → character_agent → response_builder → mood → scene_image → condense → memory → end</td>
					</tr>
					<tr>
						<td><code>narrator_chat_progression</code></td>
						<td>progression → narrator → … (same as narrator_chat) → end</td>
					</tr>
					<tr>
						<td><code>narrator_chat_lite</code></td>
						<td>narrator → character_agent → response_builder → memory → end</td>
					</tr>
					<tr>
						<td><code>chat_direct</code></td>
						<td>character_agent → response_builder → memory → end</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="hint">
			Legacy subgraph names in older databases are rewritten on migrate to <code>narrator_chat</code> (with characters) or
			<code>narrator_chat_lite</code> (without).
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
						<td><code>narrator_chat</code></td>
						<td>
							Full pipeline: narrator prose, per-character dialogue + action, bubble assembly, mood axes, LLM portrait variant
							picking, optional sidebar scene image, condense summary, structured memory.
						</td>
						<td class="col-good-for">
							Default for rich campaigns — character voices, mood tracking, expression-matched portraits, long-term summary, gallery-driven scene art.
						</td>
					</tr>
					<tr>
						<td><code>narrator_chat_classic</code></td>
						<td>
							Same as <code>narrator_chat</code> but without <code>expression_picker</code> — uses the character's default
							<code>portrait</code> field instead of LLM-selected variants.
						</td>
						<td class="col-good-for">
							Full pipeline feel with fewer LLM calls; good when portrait variants are not configured.
						</td>
					</tr>
					<tr>
						<td><code>narrator_chat_progression</code></td>
						<td>
							Prepends <code>progression</code> to the full <code>narrator_chat</code> stack. Evaluates stage gates
							(turn count, mood thresholds, optional criteria) and injects stage directives for NPCs and the narrator.
						</td>
						<td class="col-good-for">
							Stories with NPC-driven relationship or plot arcs that advance through defined stages.
						</td>
					</tr>
					<tr>
						<td><code>narrator_chat_lite</code></td>
						<td>
							Narrator + character agents + bubbles + memory. Skips mood, condense, expression_picker, and scene_image for
							fewer LLM calls and simpler turns.
						</td>
						<td class="col-good-for">
							Fast playtests, tutorials, or stories where you do not need mood compression or automatic scene picks.
						</td>
					</tr>
					<tr>
						<td><code>chat_direct</code></td>
						<td>
							No narrator node: characters respond directly; response_builder still produces bubbles; memory records the turn.
						</td>
						<td class="col-good-for">
							Pure dialogue-first setups where you do not want a separate narrator voice.
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>

	<div class="section">
		<h2>One-line picker</h2>
		<ul class="picker">
			<li><strong>Full experience (with portrait variants):</strong> <code>narrator_chat</code></li>
			<li><strong>Full experience (static portraits):</strong> <code>narrator_chat_classic</code></li>
			<li><strong>Stage-gated arcs:</strong> <code>narrator_chat_progression</code></li>
			<li><strong>Faster turns:</strong> <code>narrator_chat_lite</code></li>
			<li><strong>No narrator:</strong> <code>chat_direct</code></li>
		</ul>
	</div>

	<div class="section">
		<h2>Related</h2>
		<ul>
			<li><a href="/docs/stories">Creating Stories</a> — subgraph field, Gallery tab, portrait variants</li>
			<li><a href="/docs/engine">Engine Reference</a> — nodes and state</li>
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
