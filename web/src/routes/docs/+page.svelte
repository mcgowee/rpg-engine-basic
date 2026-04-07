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

		<div class="section">
			<h2>Builtin Stories</h2>
			<p>These stories are seeded into every fresh database. They're public, so any user can play them. Each one demonstrates a different engine feature. Copy one to your account to edit it and see how changes affect gameplay.</p>

			<div class="story-doc">
				<h3>The Midnight Lighthouse</h3>
				<dl class="story-meta">
					<dt>Genre</dt><dd>Mystery</dd>
					<dt>Subgraph</dt><dd><code>narrator_with_memory</code></dd>
					<dt>Characters</dt><dd>None</dd>
					<dt>Demonstrates</dt><dd>Narrator + memory — the simplest playable graph</dd>
				</dl>
				<p>A solo exploration story with no NPCs. The narrator describes scenes and remembers previous turns via the memory node. Good for testing how the narrator uses history context.</p>
				<div class="try-this">
					<strong>Try this:</strong> Play several turns, then reference something you did earlier. The narrator should remember it because memory records each turn in history, and the narrator reads the last few entries.
				</div>
				<div class="try-this">
					<strong>Customize:</strong> Copy to your account, then edit the narrator prompt to change the tone (try making it humorous instead of gothic). Change the player background to see how the narrator adapts.
				</div>
			</div>

			<div class="story-doc">
				<h3>The Blackrock Keeper</h3>
				<dl class="story-meta">
					<dt>Genre</dt><dd>Mystery</dd>
					<dt>Subgraph</dt><dd><code>smart_conversation</code></dd>
					<dt>Characters</dt><dd>Old Silas (mood: 4)</dd>
					<dt>Demonstrates</dt><dd>Conditional edges — same graph skips NPC when no characters exist</dd>
				</dl>
				<p>Same lighthouse setting as Midnight Lighthouse, but with Old Silas as an NPC. Uses <code>smart_conversation</code> which has a conditional edge after the narrator: if characters exist, route to NPC; otherwise skip to condense. This story has a character, so the NPC path runs.</p>
				<div class="try-this">
					<strong>Try this:</strong> Compare playing this vs. The Midnight Lighthouse. Both use similar settings, but this one has Silas responding in character after each narrator beat. The conditional edge is what makes this work — one graph handles both scenarios.
				</div>
				<div class="try-this">
					<strong>Customize:</strong> Copy and remove Old Silas from the characters. Play again — the same <code>smart_conversation</code> subgraph now skips the NPC node entirely. That's the conditional edge in action.
				</div>
			</div>

			<div class="story-doc">
				<h3>The Last Train</h3>
				<dl class="story-meta">
					<dt>Genre</dt><dd>Thriller</dd>
					<dt>Subgraph</dt><dd><code>smart_conversation</code></dd>
					<dt>Characters</dt><dd>Diana (mood: 6), Gerald (mood: 3)</dd>
					<dt>Demonstrates</dt><dd>Multiple NPCs with distinct personalities</dd>
				</dl>
				<p>Two NPCs on a late-night train, each with their own secrets and speaking style. Diana is calm and evasive; Gerald is nervous and paranoid. Both respond every turn after the narrator.</p>
				<div class="try-this">
					<strong>Try this:</strong> Address one character directly ("I turn to the nervous man") and see how both still respond but in their own way. Try being confrontational vs. sympathetic.
				</div>
				<div class="try-this">
					<strong>Customize:</strong> Copy and edit a character's prompt to change their personality. Try making Diana panicked instead of calm, or give Gerald a reason to be confident. The NPC node sends each character's prompt to the LLM independently.
				</div>
			</div>

			<div class="story-doc">
				<h3>The Job Interview</h3>
				<dl class="story-meta">
					<dt>Genre</dt><dd>Drama</dd>
					<dt>Subgraph</dt><dd><code>conversation_with_mood</code></dd>
					<dt>Characters</dt><dd>Ms. Chen (mood: 5), Big Dave (mood: 7)</dd>
					<dt>Demonstrates</dt><dd>Mood tracking with single mood number (legacy format)</dd>
				</dl>
				<p>Two interviewers with opposite personalities. The mood node runs before NPCs speak, adjusting each character's mood based on your actions. Watch the sidebar numbers change.</p>
				<div class="try-this">
					<strong>Try this:</strong> Give a confident, detailed answer and watch both moods go up. Then give a vague, evasive answer — Ms. Chen's mood drops faster than Big Dave's because her prompt makes her more critical.
				</div>
				<div class="try-this">
					<strong>Customize:</strong> Copy and change the starting moods. Set Ms. Chen to 2 (very skeptical) and Big Dave to 9 (already loves you). See how starting mood affects the NPC's tone from the first turn.
				</div>
			</div>

			<div class="story-doc">
				<h3>The Interrogation</h3>
				<dl class="story-meta">
					<dt>Genre</dt><dd>Thriller</dd>
					<dt>Subgraph</dt><dd><code>conversation_with_mood</code></dd>
					<dt>Characters</dt><dd>Marcus Webb (3 mood axes)</dd>
					<dt>Demonstrates</dt><dd>Mood axes — multiple emotional dimensions per character</dd>
				</dl>
				<p>One suspect with three emotional axes: cooperativeness (stonewalling → cooperative), anxiety (calm → panicking), and honesty (deceptive → truthful). Each axis shifts independently based on your interrogation approach.</p>
				<div class="try-this">
					<strong>Try this:</strong> Build trust slowly with empathetic questions — watch cooperativeness rise while honesty stays low. Then confront with evidence — honesty might jump but anxiety spikes. Each axis tells a different part of the story.
				</div>
				<div class="try-this">
					<strong>Customize:</strong> Copy and add a new axis like "desperation" (calm → desperate) or change the labels. The mood node asks the LLM about each axis separately, so the labels directly affect what the LLM evaluates. Try renaming "honesty" to "guilt" and see how responses change.
				</div>
			</div>
		</div>

		<div class="section">
			<h2>How to Customize a Story</h2>
			<p>Every builtin story can be copied and edited. Here's what each field does and how changing it affects gameplay:</p>

			<table class="state-table">
				<thead>
					<tr><th>Field</th><th>What it controls</th><th>What to try</th></tr>
				</thead>
				<tbody>
					<tr>
						<td><strong>Narrator Prompt</strong></td>
						<td>The system instructions the narrator LLM receives every turn. Controls tone, style, length, and what the narrator focuses on.</td>
						<td>Change "gothic mystery" to "comedic adventure" and replay. The entire feel shifts because every narrator response follows this prompt.</td>
					</tr>
					<tr>
						<td><strong>Opening</strong></td>
						<td>The first text the player sees before any turns. Sets the scene.</td>
						<td>Rewrite to start in a completely different location or situation. The narrator adapts to whatever context you establish.</td>
					</tr>
					<tr>
						<td><strong>Player Name / Background</strong></td>
						<td>Who the player is. The narrator and NPCs reference this in their prompts.</td>
						<td>Change "veteran detective" to "nervous teenager" — NPCs will treat you differently because their prompts include your background.</td>
					</tr>
					<tr>
						<td><strong>Character Prompt</strong></td>
						<td>Each NPC's personality instructions. The LLM follows this when generating their dialogue.</td>
						<td>Add specific speech patterns ("always speaks in rhyme") or secrets ("you know where the money is hidden but won't say").</td>
					</tr>
					<tr>
						<td><strong>Character First Line</strong></td>
						<td>What the NPC says when the game starts. Shown in the opening.</td>
						<td>Set the tone for the character immediately. A friendly first line vs. a hostile one changes the whole dynamic.</td>
					</tr>
					<tr>
						<td><strong>Mood / Mood Axes</strong></td>
						<td>Starting emotional state. The mood node adjusts these each turn.</td>
						<td>Start a character at mood 1 (very negative) vs. 9 (very positive) and see how their responses differ from turn one.</td>
					</tr>
					<tr>
						<td><strong>Subgraph</strong></td>
						<td>Which graph pipeline runs each turn. Determines which nodes execute and in what order.</td>
						<td>Switch a story from <code>smart_conversation</code> to <code>conversation</code> — NPCs disappear because the narrator-only graph doesn't include the NPC node.</td>
					</tr>
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
	.story-doc { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 1rem; background: #1a1d23; }
	.story-doc h3 { margin: 0 0 0.5rem; font-size: 1.05rem; }
	.story-doc p { margin: 0.4rem 0; font-size: 0.88rem; color: #bdc1c6; }
	.story-meta { margin: 0 0 0.5rem; display: grid; grid-template-columns: 7rem 1fr; gap: 0.2rem 0.5rem; font-size: 0.85rem; }
	.story-meta dt { color: #9aa0a6; font-weight: 600; margin: 0; }
	.story-meta dd { margin: 0; }
	.try-this { margin: 0.5rem 0; padding: 0.5rem 0.75rem; background: #13151a; border-radius: 6px; font-size: 0.85rem; line-height: 1.5; color: #bdc1c6; }
	.try-this strong { color: #8ab4f8; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
</style>
