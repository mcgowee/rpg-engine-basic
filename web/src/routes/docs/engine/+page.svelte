<script lang="ts">
	import { onMount } from 'svelte';

	type NodeDesc = {
		summary: string;
		description: string;
		llm: boolean;
		reads: string[];
		writes: string[];
	};

	let nodes = $state<string[]>([]);
	let nodeDescs = $state<Record<string, NodeDesc>>({});
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const r = await fetch('/api/graph-registry', { credentials: 'include' });
			if (!r.ok) { error = `Failed to load (${r.status})`; return; }
			const data = await r.json();
			nodes = data.nodes ?? [];
			nodeDescs = data.node_descriptions ?? {};
		} catch {
			error = 'Network error';
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>Engine Reference — RPG Engine Docs</title>
</svelte:head>

<section class="docs">
	<p class="breadcrumb"><a href="/docs">Docs</a> / Engine Reference</p>
	<div class="doc-hero">
		<img src="/images/docs-engine-hero.png" alt="LangGraph-style pipeline: narrator, characters, bubbles, memory" />
	</div>
	<h1>Engine Reference</h1>
	<p class="lede">How nodes, edges, and state work together each turn. For authors designing or cloning custom subgraphs.</p>
	<p class="see-also">
		<strong>Choosing a builtin pipeline?</strong>
		<a href="/docs/subgraphs">Subgraphs guide</a> — compares the three shipped subgraphs.
	</p>

	{#if loading}
		<p class="muted">Loading registry…</p>
	{:else if error}
		<p class="err">{error}</p>
	{:else}

		<div class="section">
			<h2>How a Turn Works</h2>
			<p>Every time the player sends a message:</p>
			<ol>
				<li>The message is stored in <code>state.message</code>.</li>
				<li>The engine loads the story’s <strong>subgraph</strong> from the registry.</li>
				<li>LangGraph follows <strong>edges</strong> from <code>__start__</code> through each node until <code>__end__</code>.</li>
				<li>Each node reads the state dict and returns partial updates that get merged.</li>
				<li><code>response_builder</code> produces <code>_bubbles</code> for the play UI (narrator + character bubbles).</li>
				<li>The client receives <code>response</code>, <code>bubbles</code>, optional <code>scene_image</code>, moods, and memory fields.</li>
			</ol>
		</div>

		<div class="section">
			<h2>Nodes ({nodes.length} available)</h2>
			<p>Each node is a Python function registered in <code>NODE_REGISTRY</code>. Wire them in the <a href="/graphs">Graph Editor</a> with <code>__start__</code> / <code>__end__</code> edges.</p>

			{#each nodes as name (name)}
				{@const desc = nodeDescs[name]}
				<div class="card" id={`node-${name}`}>
					<div class="card-head">
						<h3>{name}</h3>
						{#if desc?.llm}<span class="badge llm">LLM</span>{:else}<span class="badge engine">Engine</span>{/if}
					</div>
					{#if desc}
						<p class="summary">{desc.summary}</p>
						<p class="detail">{desc.description}</p>
						<div class="state-io">
							<p><strong>Reads:</strong> {desc.reads.map(f => `state.${f}`).join(', ')}</p>
							<p><strong>Writes:</strong> {desc.writes.map(f => `state.${f}`).join(', ')}</p>
						</div>
					{:else}
						<p class="muted">No description available.</p>
					{/if}
				</div>
			{/each}
		</div>

		<div class="section">
			<h2>Edges</h2>
			<p>Edges are static only. The first edge must leave <code>__start__</code>; the last must reach <code>__end__</code>.</p>
			<pre>{`{ "from": "__start__", "to": "narrator" }
{ "from": "narrator", "to": "character_agent" }
{ "from": "memory", "to": "__end__" }`}</pre>
		</div>

		<div class="section">
			<h2>Builtin subgraphs</h2>
			<p>Shipped JSON under <code>graphs/</code> — compare tradeoffs on the <a href="/docs/subgraphs">Subgraphs</a> page.</p>

			<div class="graph-card">
				<h3>narrator_chat</h3>
				<p class="flow">
					<code>narrator → character_agent → response_builder → scene_image → mood → condense → memory → __end__</code>
				</p>
				<p>Full pipeline: bubbles, sidebar scene image when configured, mood axes, rolling summary.</p>
			</div>

			<div class="graph-card">
				<h3>narrator_chat_lite</h3>
				<p class="flow">
					<code>narrator → character_agent → response_builder → memory → __end__</code>
				</p>
				<p>Faster turns — no mood, condense, or scene_image node.</p>
			</div>

			<div class="graph-card">
				<h3>chat_direct</h3>
				<p class="flow">
					<code>character_agent → response_builder → memory → __end__</code>
				</p>
				<p>No narrator node; characters respond directly with memory still recorded.</p>
			</div>
		</div>

		<div class="section">
			<h2>State fields</h2>
			<p>The game state is a Python dict merged across nodes. Common keys:</p>
			<table>
				<thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
				<tbody>
					<tr><td><code>message</code></td><td>str</td><td>Player’s current input</td></tr>
					<tr><td><code>response</code></td><td>str</td><td>Combined text (bubbles flattened) for plain-text clients</td></tr>
					<tr><td><code>_bubbles</code></td><td>list</td><td>UI payload: narrator + character bubbles from <code>response_builder</code></td></tr>
					<tr><td><code>_narrator_text</code></td><td>str</td><td>Last narrator beat (internal)</td></tr>
					<tr><td><code>_character_responses</code></td><td>dict</td><td>Per-character dialogue + action (internal)</td></tr>
					<tr><td><code>history</code></td><td>list</td><td>Structured turns (memory node)</td></tr>
					<tr><td><code>memory_summary</code></td><td>str</td><td>Rolling summary (condense)</td></tr>
					<tr><td><code>narrator</code></td><td>dict</td><td><code>prompt</code>, <code>model</code></td></tr>
					<tr><td><code>player</code></td><td>dict</td><td><code>name</code>, <code>background</code></td></tr>
					<tr><td><code>characters</code></td><td>dict</td><td>Cast: prompts, moods, portraits, rules</td></tr>
					<tr><td><code>game_title</code></td><td>str</td><td>Story title</td></tr>
					<tr><td><code>opening</code></td><td>str</td><td>Shown before first turn</td></tr>
					<tr><td><code>paused</code></td><td>bool</td><td>Pause flag</td></tr>
					<tr><td><code>turn_count</code></td><td>int</td><td>Completed turns</td></tr>
				</tbody>
			</table>
		</div>

		<div class="section">
			<h2>Testing subgraphs</h2>
			<p>The <a href="/graphs">Graph Editor</a> can run a saved subgraph against a dummy state or a real story and show the trace (nodes run and state after each step).</p>
		</div>

		<div class="section">
			<h2>Creating custom subgraphs</h2>
			<ol>
				<li>Open <a href="/graphs">Graphs</a> → <strong>New Subgraph</strong>.</li>
				<li>Select nodes from the registry checklist.</li>
				<li>Add edges from <code>__start__</code> through your chain to <code>__end__</code>.</li>
				<li>Use the JSON preview, save, and test.</li>
			</ol>
			<p>Every selected node must be reachable from <code>__start__</code>; unreachable nodes fail compilation.</p>
		</div>

	{/if}

	<p class="nav-links">
		<a href="/docs/stories">← Story Creator Guide</a> · <a href="/docs">Docs Home →</a>
	</p>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.breadcrumb { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.doc-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.doc-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.see-also { margin: -0.5rem 0 1.25rem; padding: 0.65rem 0.85rem; border-radius: 8px; border: 1px solid #2a2f38; background: #1a1d23; font-size: 0.9rem; color: #bdc1c6; line-height: 1.5; }
	.see-also strong { color: #e8eaed; }
	:global([data-theme="light"]) .see-also { background: #f8fafc; border-color: #dfe3e8; color: #334155; }
	:global([data-theme="light"]) .see-also strong { color: #111827; }
	.section { margin-bottom: 2.5rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section h3 { margin: 1rem 0 0.3rem; font-size: 1rem; }
	.section p, .section li { line-height: 1.55; color: #bdc1c6; }
	.section ol { padding-left: 1.25rem; }
	.section pre { font-size: 0.82rem; overflow-x: auto; padding: 0.75rem; background: #13151a; border: 1px solid #2a2f38; border-radius: 8px; color: #c9d1d9; }
	.card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.card-head { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
	.card h3 { margin: 0; font-size: 1rem; }
	.badge { font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 12px; font-weight: 600; letter-spacing: 0.03em; }
	.badge.llm { background: #2a1a3a; color: #c58af9; }
	.badge.engine { background: #1a3a3a; color: #4dd0e1; }
	.summary { margin: 0 0 0.4rem; font-weight: 600; font-size: 0.92rem; color: #e8eaed; }
	.detail { margin: 0 0 0.5rem; font-size: 0.88rem; color: #9aa0a6; line-height: 1.5; }
	.state-io { font-size: 0.82rem; color: #9aa0a6; }
	.state-io p { margin: 0.15rem 0; }
	.graph-card { border-left: 3px solid #2a2f38; padding: 0.5rem 0 0.5rem 0.85rem; margin-bottom: 0.75rem; }
	.graph-card h3 { margin: 0 0 0.2rem; font-size: 0.95rem; }
	.graph-card p { margin: 0.2rem 0; font-size: 0.88rem; color: #bdc1c6; }
	.graph-card .flow { color: #8ab4f8; font-size: 0.85rem; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.nav-links { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #2a2f38; font-size: 0.9rem; }
	:global([data-theme="light"]) .section h2,
	:global([data-theme="light"]) .nav-links { border-bottom-color: #dfe3e8; border-top-color: #dfe3e8; }
	:global([data-theme="light"]) .section p,
	:global([data-theme="light"]) .section li,
	:global([data-theme="light"]) .detail,
	:global([data-theme="light"]) .state-io,
	:global([data-theme="light"]) .graph-card p { color: #334155; }
	:global([data-theme="light"]) .card { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .summary { color: #111827; }
	:global([data-theme="light"]) .doc-hero { border-color: #dfe3e8; }
	:global([data-theme="light"]) .section pre { background: #f8fafc; border-color: #dfe3e8; color: #1e293b; }
</style>
