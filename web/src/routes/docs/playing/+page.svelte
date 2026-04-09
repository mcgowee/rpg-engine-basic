<svelte:head>
	<title>Playing Stories — RPG Engine Docs</title>
</svelte:head>

<section class="docs">
	<p class="breadcrumb"><a href="/docs">Docs</a> / Playing Stories</p>
	<div class="doc-hero">
		<img src="/images/docs-playing-hero.png" alt="RPG party exploring ruins" />
	</div>
	<h1>Playing Stories</h1>
	<p class="lede">How to find, play, and interact with stories in the RPG Engine.</p>

	<div class="section">
		<h2>Getting Started</h2>
		<p>Go to <a href="/stories/browse">Browse</a> to see public stories, or <a href="/stories">My Stories</a> if you've created or copied any. Click <strong>Play</strong> on any story to start.</p>
		<p>The game opens with the story's <strong>opening text</strong> — this sets the scene before your first turn. Type what your character does in the text box and hit Enter or Send.</p>
	</div>

	<div class="section">
		<h2>The Play Screen</h2>

		<h3>Chat Area (left)</h3>
		<p>This is where the story unfolds. You'll see two types of messages:</p>
		<ul>
			<li><strong>Your messages</strong> (blue left border) — what you typed</li>
			<li><strong>Narrator + NPC responses</strong> (green left border) — the narrator describes the scene, then any NPCs present respond in character</li>
		</ul>
		<p>The narrator doesn't control NPCs — they speak separately based on their own personality prompts. So the narrator might describe "Silas shifts uncomfortably" and then Silas actually says something in his own voice.</p>

		<h3>Sidebar (right)</h3>
		<p>The sidebar shows the current game state:</p>
		<dl class="info-list">
			<dt>Title</dt>
			<dd>The story you're playing</dd>
			<dt>Player</dt>
			<dd>Your character's name</dd>
			<dt>Turns</dt>
			<dd>How many turns you've taken</dd>
			<dt>Subgraph</dt>
			<dd>Which graph pipeline is running — see <a href="/docs/subgraphs">Subgraphs</a> for a comparison, or <a href="/docs/engine">Engine Reference</a> for nodes and routers</dd>
		</dl>
	</div>

	<div class="section">
		<h2>Characters &amp; Moods</h2>
		<p>If the story has NPCs, the sidebar shows their current emotional state. There are two formats:</p>

		<h3>Simple mood (single number)</h3>
		<p>A number from 1-10. Higher means more positive toward you. The mood shifts each turn based on how you interact with the character.</p>

		<h3>Mood axes (named scales)</h3>
		<p>Some characters have multiple emotional dimensions. For example:</p>
		<div class="example-box">
			<strong>Marcus Webb</strong><br>
			cooperativeness: 2/10 (stonewalling → cooperative)<br>
			anxiety: 6/10 (calm → panicking)<br>
			honesty: 2/10 (deceptive → truthful)
		</div>
		<p>Each axis shifts independently. You might build trust (cooperativeness goes up) while making someone more nervous (anxiety goes up) at the same time. The labels tell you what each end of the scale means.</p>
		<p>NPCs use their mood state when deciding how to respond. A terrified character talks differently than a confident one, even with the same personality prompt.</p>
	</div>

	<div class="section">
		<h2>Memory</h2>
		<p>Click <strong>Memory (AI summary)</strong> in the sidebar to see what the engine remembers about the story so far. This is a compressed summary that the narrator uses for context.</p>
		<p>
			Whether you see a rolling AI summary depends on the <a href="/docs/subgraphs">subgraph</a>.
			<code>conversation</code> keeps turn history in the graph; <code>full_conversation</code> and other graphs that
			include <code>condense</code> maintain the compressed summary the narrator uses for long-range context.
		</p>
	</div>

	<div class="section">
		<h2>Save &amp; Load</h2>
		<p>Click <strong>Save / Load</strong> in the sidebar to manage your saves. You have 5 save slots (0-4). The game auto-saves to slot 0 every turn.</p>
		<ul>
			<li><strong>Save</strong> — saves your current state to a slot</li>
			<li><strong>Load</strong> — restores a previous save (replaces your current state)</li>
		</ul>
	</div>

	<div class="section">
		<h2>Pause</h2>
		<p>Click <strong>Pause</strong> in the sidebar to freeze the game. While paused, your messages won't be processed. Click <strong>Unpause</strong> to resume.</p>
	</div>

	<div class="section">
		<h2>Copying Stories</h2>
		<p>On the <a href="/stories/browse">Browse</a> page, click <strong>Copy to My Stories</strong> to duplicate a public story into your account. You can then edit it freely without affecting the original. See <a href="/docs/stories">Creating Stories</a> for what you can change.</p>
	</div>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.breadcrumb { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.doc-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.doc-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.section { margin-bottom: 2rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section h3 { margin: 1rem 0 0.3rem; font-size: 1rem; }
	.section p, .section li { line-height: 1.55; color: #bdc1c6; }
	.section ul { padding-left: 1.25rem; }
	.info-list { display: grid; grid-template-columns: 7rem 1fr; gap: 0.25rem 0.75rem; font-size: 0.9rem; margin: 0.5rem 0; }
	.info-list dt { color: #9aa0a6; font-weight: 600; margin: 0; }
	.info-list dd { margin: 0; color: #bdc1c6; }
	.example-box { background: #13151a; border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 0.85rem; line-height: 1.6; margin: 0.5rem 0; color: #bdc1c6; }
	:global([data-theme="light"]) .section h2 { border-bottom-color: #dfe3e8; }
	:global([data-theme="light"]) .section p,
	:global([data-theme="light"]) .section li,
	:global([data-theme="light"]) .info-list dd { color: #334155; }
	:global([data-theme="light"]) .example-box { background: #f8fafc; color: #334155; border: 1px solid #dfe3e8; }
	:global([data-theme="light"]) .doc-hero { border-color: #dfe3e8; }
</style>
