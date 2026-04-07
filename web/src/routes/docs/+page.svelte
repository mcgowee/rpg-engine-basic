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
	<title>Docs — RPG Engine</title>
</svelte:head>

<section class="docs">
	<h1>Engine Reference</h1>
	<p class="lede">How nodes, routers, and graphs work together to run a story.</p>

	{#if loading}
		<p class="muted">Loading…</p>
	{:else if error}
		<p class="err">{error}</p>
	{:else}

		<div class="section">
			<h2>How It Works</h2>
			<p>Each turn follows this flow:</p>
			<ol class="flow">
				<li>Player types a message</li>
				<li>The <strong>subgraph</strong> runs — a sequence of nodes connected by edges</li>
				<li>Each <strong>node</strong> reads the game state, does its work, and returns updates</li>
				<li><strong>Routers</strong> decide which path to take at conditional edges</li>
				<li>The final state (with the narrator's response) is returned to the player</li>
			</ol>
			<p>
				Subgraphs are defined as JSON — you pick which nodes to include and how to wire them.
				Different stories can use different subgraphs. Build and test them in the
				<a href="/graphs">Graph Editor</a>.
			</p>
		</div>

		<div class="section">
			<h2>Nodes ({nodes.length} available)</h2>
			<p>Nodes are the building blocks. Each one does one job.</p>

			{#each nodes as name (name)}
				{@const desc = nodeDescs[name]}
				<div class="card" id={`node-${name}`}>
					<h3>{name} {#if desc?.llm}<span class="badge llm">LLM</span>{:else}<span class="badge engine">Engine</span>{/if}</h3>
					{#if desc}
						<p class="summary">{desc.summary}</p>
						<p class="detail">{desc.description}</p>
						<div class="state-info">
							<p><strong>Reads:</strong> {desc.reads.join(', ')}</p>
							<p><strong>Writes:</strong> {desc.writes.join(', ')}</p>
						</div>
					{:else}
						<p class="muted">No description available.</p>
					{/if}
				</div>
			{/each}
		</div>

		<div class="section">
			<h2>Routers ({Object.keys(routers).length} available)</h2>
			<p>Routers are decision points. They look at the game state and return a string that tells the graph which node to run next. The graph's <strong>mapping</strong> translates that string to an actual node.</p>

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
			<h2>Example Graphs</h2>
			<p>These are the builtin subgraphs. You can clone or create your own in the <a href="/graphs">Graph Editor</a>.</p>

			<div class="example">
				<h3>conversation</h3>
				<p>Simplest graph. <code>narrator → __end__</code>. No memory, no NPCs. Every turn is independent.</p>
			</div>

			<div class="example">
				<h3>narrator_with_memory</h3>
				<p><code>narrator → memory → __end__</code>. Narrator remembers previous turns via history.</p>
			</div>

			<div class="example">
				<h3>full_conversation</h3>
				<p><code>narrator → condense → memory → __end__</code>. Adds rolling memory summary for long-term context.</p>
			</div>

			<div class="example">
				<h3>smart_conversation</h3>
				<p><code>narrator → [conditional] → npc → condense → memory → __end__</code>.
				Uses <code>route_after_narrator</code> to skip NPC if no characters exist. One graph handles stories with or without NPCs.</p>
			</div>

			<div class="example">
				<h3>conversation_with_mood</h3>
				<p><code>narrator → [conditional] → mood → npc → condense → memory → __end__</code>.
				Adds mood tracking before NPC dialogue. Mood axes shift each turn based on player actions.</p>
			</div>
		</div>

		<div class="section">
			<h2>State Fields</h2>
			<p>The game state flows through every node. Each node reads what it needs and returns updates.</p>
			<table class="state-table">
				<thead>
					<tr><th>Field</th><th>Type</th><th>Description</th></tr>
				</thead>
				<tbody>
					<tr><td><code>message</code></td><td>string</td><td>The player's current input</td></tr>
					<tr><td><code>response</code></td><td>string</td><td>The narrator's response (+ NPC dialogue appended)</td></tr>
					<tr><td><code>history</code></td><td>list</td><td>Turn log — each entry is "Player: ...\nNarrator: ..."</td></tr>
					<tr><td><code>memory_summary</code></td><td>string</td><td>Compressed story summary from condense node</td></tr>
					<tr><td><code>narrator</code></td><td>dict</td><td>Narrator config: prompt and model name</td></tr>
					<tr><td><code>player</code></td><td>dict</td><td>Player info: name and background</td></tr>
					<tr><td><code>characters</code></td><td>dict</td><td>NPC definitions with prompts, moods, models</td></tr>
					<tr><td><code>game_title</code></td><td>string</td><td>Story title</td></tr>
					<tr><td><code>opening</code></td><td>string</td><td>Opening text shown before first turn</td></tr>
					<tr><td><code>paused</code></td><td>bool</td><td>Whether the game is paused</td></tr>
					<tr><td><code>turn_count</code></td><td>int</td><td>Number of completed turns</td></tr>
				</tbody>
			</table>
		</div>

	{/if}
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.section { margin-bottom: 2.5rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.25rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section p { line-height: 1.55; color: #bdc1c6; }
	.flow { line-height: 1.6; color: #bdc1c6; }
	.card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.card h3 { margin: 0 0 0.3rem; font-size: 1rem; }
	.badge { font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 12px; vertical-align: middle; margin-left: 0.4rem; font-weight: 600; letter-spacing: 0.03em; }
	.badge.llm { background: #2a1a3a; color: #c58af9; }
	.badge.engine { background: #1a3a3a; color: #4dd0e1; }
	.summary { margin: 0 0 0.4rem; font-weight: 600; font-size: 0.92rem; color: #e8eaed; }
	.detail { margin: 0 0 0.5rem; font-size: 0.88rem; color: #9aa0a6; line-height: 1.5; }
	.state-info { font-size: 0.82rem; color: #9aa0a6; }
	.state-info p { margin: 0.15rem 0; }
	.returns { font-size: 0.85rem; color: #9aa0a6; margin: 0.3rem 0 0; }
	.example { border-left: 3px solid #2a2f38; padding: 0.4rem 0 0.4rem 0.75rem; margin-bottom: 0.75rem; }
	.example h3 { margin: 0 0 0.2rem; font-size: 0.95rem; }
	.example p { margin: 0; font-size: 0.88rem; color: #bdc1c6; line-height: 1.45; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
</style>
