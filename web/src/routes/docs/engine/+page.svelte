<script lang="ts">
	import { onMount } from 'svelte';

	type NodeDesc = {
		summary: string;
		description: string;
		llm: boolean;
		reads: string[];
		writes: string[];
	};

	type RouterDesc = {
		summary: string;
		description: string;
		returns: string[];
	};

	let nodes = $state<string[]>([]);
	let nodeDescs = $state<Record<string, NodeDesc>>({});
	let routers = $state<Record<string, string[]>>({});
	let routerDescs = $state<Record<string, RouterDesc>>({});
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const r = await fetch('/api/graph-registry', { credentials: 'include' });
			if (!r.ok) { error = `Failed to load (${r.status})`; return; }
			const data = await r.json();
			nodes = data.nodes ?? [];
			nodeDescs = data.node_descriptions ?? {};
			routers = data.routers ?? {};
			routerDescs = data.router_descriptions ?? {};
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
	<h1>Engine Reference</h1>
	<p class="lede">How nodes, routers, edges, and state work together to run a story. For graph builders who want to create custom subgraphs.</p>

	{#if loading}
		<p class="muted">Loading registry…</p>
	{:else if error}
		<p class="err">{error}</p>
	{:else}

		<div class="section">
			<h2>How a Turn Works</h2>
			<p>Every time the player sends a message, this happens:</p>
			<ol>
				<li>The player's message is stored in <code>state.message</code></li>
				<li>The engine looks up which <strong>subgraph</strong> this story uses</li>
				<li>The subgraph's <strong>entry point router</strong> runs, returning a string</li>
				<li>The entry point <strong>mapping</strong> translates that string to the first node</li>
				<li>That node runs, reads state, returns updates that get merged back</li>
				<li>The next edge (static or conditional) determines the next node</li>
				<li>Repeat until the graph reaches <code>__end__</code></li>
				<li>The final <code>state.response</code> is sent back to the player</li>
			</ol>
		</div>

		<div class="section">
			<h2>Nodes ({nodes.length} available)</h2>
			<p>Each node is a Python function that takes the game state and returns updates. Nodes are the building blocks — you wire them together in the <a href="/graphs">Graph Editor</a>.</p>

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
			<h2>Routers ({Object.keys(routers).length} available)</h2>
			<p>Routers are Python functions at decision points in the graph. They check the state and return a string. The graph's <strong>mapping</strong> translates that string to the next node.</p>
			<p>The same router can be used in different graphs with different mappings. For example, <code>route_after_narrator</code> returns <code>"npc"</code> when characters exist — but one graph maps that to the <code>npc</code> node while another maps it to <code>mood</code> first.</p>

			{#each Object.entries(routers) as [name, returns] (name)}
				{@const desc = routerDescs[name]}
				<div class="card" id={`router-${name}`}>
					<h3>{name}</h3>
					{#if desc}
						<p class="summary">{desc.summary}</p>
						<p class="detail">{desc.description}</p>
					{/if}
					<p class="returns"><strong>Returns:</strong> {returns.map(r => `"${r}"`).join(' or ')}</p>
				</div>
			{/each}
		</div>

		<div class="section">
			<h2>Edges</h2>
			<p>Edges connect nodes. There are two types:</p>

			<h3>Static edges</h3>
			<p>Always go from A to B, no questions asked. In the JSON:</p>
			<pre>{`{ "from": "narrator", "to": "condense" }`}</pre>

			<h3>Conditional edges</h3>
			<p>A router decides which node comes next. In the JSON:</p>
			<pre>{`{
  "from": "narrator",
  "router": "route_after_narrator",
  "mapping": {
    "npc": "mood",
    "condense": "condense"
  }
}`}</pre>
			<p>The router runs, returns a string (e.g. <code>"npc"</code>), the mapping translates it to the actual node (e.g. <code>"mood"</code>). This lets one graph handle different story configurations.</p>
		</div>

		<div class="section">
			<h2>Builtin Subgraphs</h2>
			<p>These are pre-built graphs you can use or clone from the <a href="/graphs">Graph Editor</a>. They're listed from simplest to most complex.</p>

			<div class="graph-card">
				<h3>conversation</h3>
				<p class="flow"><code>narrator → __end__</code></p>
				<p>Narrator only. No memory, no NPCs. Every turn is independent. Good for testing.</p>
			</div>

			<div class="graph-card">
				<h3>narrator_with_memory</h3>
				<p class="flow"><code>narrator → memory → __end__</code></p>
				<p>Adds turn recording. The narrator reads history for context between turns.</p>
			</div>

			<div class="graph-card">
				<h3>full_conversation</h3>
				<p class="flow"><code>narrator → condense → memory → __end__</code></p>
				<p>Adds AI memory summary. Condense compresses the story into ~100 words so the narrator has long-term context.</p>
			</div>

			<div class="graph-card">
				<h3>conversation_with_npc</h3>
				<p class="flow"><code>narrator → npc → condense → memory → __end__</code></p>
				<p>Adds NPC dialogue. Every character speaks every turn. No conditional skip.</p>
			</div>

			<div class="graph-card">
				<h3>smart_conversation</h3>
				<p class="flow"><code>narrator → [route_after_narrator] → npc → condense → memory → __end__</code></p>
				<p>Conditional NPC: if characters exist, route to NPC; otherwise skip to condense. One graph works for stories with or without NPCs.</p>
			</div>

			<div class="graph-card">
				<h3>conversation_with_mood</h3>
				<p class="flow"><code>narrator → [route_after_narrator] → mood → npc → condense → memory → __end__</code></p>
				<p>Adds mood tracking before NPC dialogue. Each character's mood axes shift each turn. Uses conditional edge to skip mood+NPC when no characters.</p>
			</div>
		</div>

		<div class="section">
			<h2>State Fields</h2>
			<p>The game state is a Python dict that flows through every node. Each node reads what it needs and returns a partial dict of updates.</p>
			<table>
				<thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
				<tbody>
					<tr><td><code>message</code></td><td>str</td><td>Player's current input</td></tr>
					<tr><td><code>response</code></td><td>str</td><td>Narrator response + NPC dialogue</td></tr>
					<tr><td><code>history</code></td><td>list</td><td>Turn log (written by memory node)</td></tr>
					<tr><td><code>memory_summary</code></td><td>str</td><td>Compressed story summary (written by condense node)</td></tr>
					<tr><td><code>narrator</code></td><td>dict</td><td>Narrator config: <code>prompt</code> and <code>model</code></td></tr>
					<tr><td><code>player</code></td><td>dict</td><td>Player character: <code>name</code> and <code>background</code></td></tr>
					<tr><td><code>characters</code></td><td>dict</td><td>NPCs keyed by id, each with <code>prompt</code>, <code>moods</code>, <code>model</code></td></tr>
					<tr><td><code>game_title</code></td><td>str</td><td>Story title</td></tr>
					<tr><td><code>opening</code></td><td>str</td><td>Opening text before first turn</td></tr>
					<tr><td><code>paused</code></td><td>bool</td><td>Game paused flag</td></tr>
					<tr><td><code>turn_count</code></td><td>int</td><td>Completed turns (written by memory node)</td></tr>
				</tbody>
			</table>
		</div>

		<div class="section">
			<h2>Testing Subgraphs</h2>
			<p>The <a href="/graphs">Graph Editor</a> has a built-in test runner. Save a subgraph, then use the Test section to send a message through it and see the trace — which nodes ran, what each returned, and the full state after each step.</p>
			<p>You can test with a <strong>dummy state</strong> (fake room, generic narrator) or load state from an <strong>existing story</strong> for realistic results.</p>
			<p>The test trace is the best way to understand how a graph works — you can see exactly what data flows through each node.</p>
		</div>

		<div class="section">
			<h2>Creating Custom Subgraphs</h2>
			<ol>
				<li>Go to <a href="/graphs">Graphs</a> and click <strong>New Subgraph</strong></li>
				<li>Check the nodes you want to include</li>
				<li>Set the entry point router and mapping</li>
				<li>Add static edges to connect nodes in order</li>
				<li>Optionally add conditional edges with routers for branching</li>
				<li>Use the JSON preview to verify the definition</li>
				<li>Save and test</li>
			</ol>
			<p>Every node you check must be reachable — either through the entry point or through an edge from another node. Unreachable nodes cause compilation errors.</p>
		</div>

	{/if}

	<p class="nav-links">
		<a href="/docs/stories">← Story Creator Guide</a> · <a href="/docs">Docs Home →</a>
	</p>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.breadcrumb { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.section { margin-bottom: 2.5rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section h3 { margin: 1rem 0 0.3rem; font-size: 1rem; }
	.section p, .section li { line-height: 1.55; color: #bdc1c6; }
	.section ol { padding-left: 1.25rem; }
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
	.returns { font-size: 0.85rem; color: #9aa0a6; margin: 0.3rem 0 0; }
	.graph-card { border-left: 3px solid #2a2f38; padding: 0.5rem 0 0.5rem 0.85rem; margin-bottom: 0.75rem; }
	.graph-card h3 { margin: 0 0 0.2rem; font-size: 0.95rem; }
	.graph-card p { margin: 0.2rem 0; font-size: 0.88rem; color: #bdc1c6; }
	.graph-card .flow { color: #8ab4f8; font-size: 0.85rem; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.nav-links { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #2a2f38; font-size: 0.9rem; }
</style>
