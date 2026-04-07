<svelte:head>
	<title>Creating Stories — RPG Engine Docs</title>
</svelte:head>

<section class="docs">
	<p class="breadcrumb"><a href="/docs">Docs</a> / Creating Stories</p>
	<h1>Creating Stories</h1>
	<p class="lede">How to build your own text adventures — from simple narrator-only stories to multi-character dramas with mood tracking.</p>

	<div class="section">
		<h2>Quick Start</h2>
		<ol>
			<li>Go to <a href="/stories/create">Create Story</a></li>
			<li>Fill in a title, description, and opening text</li>
			<li>Pick a subgraph (start with <code>narrator_with_memory</code>)</li>
			<li>Save and click Play</li>
		</ol>
		<p>That's the minimum — a title, opening, and subgraph. Everything else is optional and adds depth.</p>
	</div>

	<div class="section">
		<h2>Story Editor Tabs</h2>

		<h3>Basics</h3>
		<p>The essentials that every story needs:</p>
		<dl class="field-list">
			<dt>Title</dt><dd>Name of your story. Shows up in lists and the play screen.</dd>
			<dt>Description</dt><dd>1-2 sentence pitch. Shown when browsing stories.</dd>
			<dt>Notes</dt><dd>Optional. Explain what the story demonstrates or tips for players.</dd>
			<dt>Genre</dt><dd>Category tag: mystery, thriller, drama, comedy, sci-fi, horror, fantasy.</dd>
			<dt>Opening</dt><dd>The first thing the player reads before their first turn. Second person, present tense. Sets the scene and tone.</dd>
		</dl>

		<h3>Subgraph</h3>
		<p>Which graph pipeline runs each turn. This is the most important choice — it determines what the engine does with the player's input. See <a href="/docs/engine">Engine Reference</a> for details on each subgraph.</p>
		<div class="tip">
			<strong>Which subgraph should I pick?</strong>
			<ul>
				<li><code>conversation</code> — narrator only, no memory. Good for one-shot scenes.</li>
				<li><code>narrator_with_memory</code> — narrator remembers previous turns. Good for solo exploration.</li>
				<li><code>full_conversation</code> — adds AI memory summary. Good for longer stories.</li>
				<li><code>smart_conversation</code> — adds NPCs that respond in character. Automatically skips NPC step if no characters defined.</li>
				<li><code>conversation_with_mood</code> — adds mood tracking before NPC dialogue. Best for character-driven stories.</li>
			</ul>
		</div>

		<h3>Shared Content</h3>
		<p>The narrator and player character — these shape every turn:</p>
		<dl class="field-list">
			<dt>Narrator Prompt</dt><dd>System instructions for the narrator LLM. Controls tone, style, perspective, and what to focus on. This is the single most impactful field — it shapes the entire voice of your story.</dd>
			<dt>Narrator Model</dt><dd>Which LLM model to use. Leave as "default" unless you have a specific model in mind.</dd>
			<dt>Player Name</dt><dd>Who the player is in the story world. NPCs address them by this name.</dd>
			<dt>Player Background</dt><dd>The player character's history and situation. Gives the narrator and NPCs context for how to interact.</dd>
		</dl>

		<h3>Characters</h3>
		<p>NPCs that respond in character each turn. Only used if your subgraph includes the <code>npc</code> node (<code>smart_conversation</code> or <code>conversation_with_mood</code>).</p>
		<p>Each character needs:</p>
		<dl class="field-list">
			<dt>Key</dt><dd>Snake_case identifier (e.g. <code>old_silas</code>). Used internally.</dd>
			<dt>Personality Prompt</dt><dd>Instructions for how this NPC speaks and behaves. The LLM follows this when generating their dialogue. Be specific — speech patterns, secrets, attitude, goals.</dd>
			<dt>First Line</dt><dd>What they say when the game starts. Sets their tone immediately.</dd>
			<dt>Mood Axes</dt><dd>Named emotional scales that shift each turn. See "Mood System" below.</dd>
		</dl>
	</div>

	<div class="section">
		<h2>Mood System</h2>
		<p>Characters can have one or more <strong>mood axes</strong> — named scales between two emotions. The mood node evaluates each axis every turn and adjusts it up or down.</p>

		<h3>Defining axes</h3>
		<p>Each axis has:</p>
		<dl class="field-list">
			<dt>Axis name</dt><dd>What this emotion tracks (e.g. "trust", "fear", "patience")</dd>
			<dt>Low label</dt><dd>What 1/10 means (e.g. "suspicious", "terrified", "snapping")</dd>
			<dt>High label</dt><dd>What 10/10 means (e.g. "trusting", "brave", "serene")</dd>
			<dt>Starting value</dt><dd>Where this axis begins (1-10)</dd>
		</dl>

		<h3>How it works</h3>
		<p>Each turn, for each character, for each axis, the mood node asks the LLM:</p>
		<div class="example-box">
			"Character: Old Silas. Trait: trust (currently 3/10, where 1 = suspicious and 10 = trusting). Player action: I share my own story about the sea. Should trust go UP, DOWN, or SAME?"
		</div>
		<p>The LLM returns UP, DOWN, or SAME. The value shifts by 1. The NPC node then includes all axes in the character's prompt so their response reflects their current emotional state.</p>

		<h3>Tips</h3>
		<ul>
			<li>Start with 1-2 axes per character. More axes = more LLM calls = slower turns.</li>
			<li>Choose axes that create interesting tension — "trust" vs "fear" creates a character who might trust you but is still scared.</li>
			<li>The axis labels matter — the LLM reads them literally. "hostile → friendly" evaluates differently than "guarded → open".</li>
			<li>Legacy format: a single <code>mood: 5</code> number still works if you don't need named axes.</li>
		</ul>
	</div>

	<div class="section">
		<h2>AI Generation</h2>
		<p>On the Basics tab, the <strong>AI Generate</strong> section lets you describe a story concept and have the LLM generate title, opening, narrator prompt, and player character. You can edit everything afterward.</p>
		<p>The <strong>Improve</strong> buttons next to text fields send that field to the LLM for polishing — tighter prose, better phrasing, same meaning.</p>
	</div>

	<div class="section">
		<h2>Export &amp; Import</h2>
		<p>On <a href="/stories">My Stories</a>, use <strong>Export</strong> to download a story as JSON. Use <strong>Import</strong> to load one back. This is useful for:</p>
		<ul>
			<li>Backing up stories before a database reset</li>
			<li>Sharing stories with others (send them the JSON file)</li>
			<li>Editing story data directly in a text editor</li>
		</ul>
	</div>

	<div class="section">
		<h2>Builtin Stories</h2>
		<p>These stories are seeded into every fresh database. Each demonstrates a different engine feature. Copy one to your account to experiment with it.</p>

		<div class="story-card">
			<h3>The Midnight Lighthouse</h3>
			<p class="meta">Mystery · <code>narrator_with_memory</code> · No characters</p>
			<p>Solo exploration. Demonstrates narrator + memory nodes — the simplest playable graph. The narrator describes scenes and remembers previous turns.</p>
			<p class="try"><strong>Try:</strong> Play several turns, then reference something from earlier. Copy and change the narrator prompt to shift the tone.</p>
		</div>

		<div class="story-card">
			<h3>The Blackrock Keeper</h3>
			<p class="meta">Mystery · <code>smart_conversation</code> · Old Silas</p>
			<p>Same lighthouse with an NPC. Demonstrates conditional edges — <code>route_after_narrator</code> checks if characters exist and routes to NPC or skips it.</p>
			<p class="try"><strong>Try:</strong> Copy and remove Old Silas. Play again — the same subgraph skips the NPC step entirely. That's the conditional edge at work.</p>
		</div>

		<div class="story-card">
			<h3>The Last Train</h3>
			<p class="meta">Thriller · <code>smart_conversation</code> · Diana, Gerald</p>
			<p>Two NPCs with distinct personalities on a late-night train. Demonstrates multiple characters responding independently.</p>
			<p class="try"><strong>Try:</strong> Address one character directly and see how both still respond in character. Edit a character's prompt to change their personality.</p>
		</div>

		<div class="story-card">
			<h3>The Job Interview</h3>
			<p class="meta">Drama · <code>conversation_with_mood</code> · Ms. Chen (5), Big Dave (7)</p>
			<p>Two interviewers with opposite personalities. Demonstrates mood tracking — watch sidebar numbers change based on your answers.</p>
			<p class="try"><strong>Try:</strong> Give confident vs. evasive answers. Change starting moods and replay to see how it affects the dynamic from turn one.</p>
		</div>

		<div class="story-card">
			<h3>The Interrogation</h3>
			<p class="meta">Thriller · <code>conversation_with_mood</code> · Marcus Webb (3 axes)</p>
			<p>One suspect with three mood axes: cooperativeness, anxiety, honesty. Demonstrates multi-dimensional mood tracking.</p>
			<p class="try"><strong>Try:</strong> Build trust slowly, then confront with evidence. Add a new axis like "desperation" and see how it changes responses.</p>
		</div>
	</div>

	<div class="section">
		<h2>Field Reference</h2>
		<p>What each editable field controls and what happens when you change it:</p>
		<table>
			<thead><tr><th>Field</th><th>Controls</th><th>What to try</th></tr></thead>
			<tbody>
				<tr><td>Narrator Prompt</td><td>Tone, style, and focus of all narration</td><td>Change "gothic mystery" to "comedic adventure"</td></tr>
				<tr><td>Opening</td><td>First text the player sees</td><td>Rewrite to start in a different situation</td></tr>
				<tr><td>Player Background</td><td>How narrator and NPCs perceive you</td><td>Change "veteran detective" to "nervous teenager"</td></tr>
				<tr><td>Character Prompt</td><td>NPC personality and speech patterns</td><td>Add "always speaks in rhyme" or a hidden secret</td></tr>
				<tr><td>Mood Axes</td><td>What emotions are tracked and their range</td><td>Rename "trust" to "guilt" — the LLM evaluates differently</td></tr>
				<tr><td>Subgraph</td><td>Which nodes run each turn</td><td>Switch to <code>conversation</code> — NPCs disappear</td></tr>
			</tbody>
		</table>
	</div>

	<p class="nav-links">
		<a href="/docs/playing">← Player Guide</a> · <a href="/docs/engine">Engine Reference →</a>
	</p>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.breadcrumb { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.section { margin-bottom: 2rem; }
	.section h2 { margin: 0 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.section h3 { margin: 1rem 0 0.3rem; font-size: 1rem; }
	.section p, .section li { line-height: 1.55; color: #bdc1c6; }
	.section ul, .section ol { padding-left: 1.25rem; }
	.field-list { display: grid; grid-template-columns: 8rem 1fr; gap: 0.3rem 0.75rem; font-size: 0.9rem; margin: 0.5rem 0; }
	.field-list dt { color: #9aa0a6; font-weight: 600; margin: 0; }
	.field-list dd { margin: 0; color: #bdc1c6; }
	.tip { background: #13151a; border-radius: 8px; padding: 0.75rem 1rem; margin: 0.75rem 0; }
	.tip strong { color: #8ab4f8; }
	.tip ul { margin: 0.3rem 0 0; padding-left: 1.25rem; }
	.tip li { font-size: 0.88rem; color: #bdc1c6; }
	.example-box { background: #13151a; border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 0.85rem; line-height: 1.6; margin: 0.5rem 0; color: #bdc1c6; font-style: italic; }
	.story-card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.story-card h3 { margin: 0 0 0.25rem; font-size: 1rem; }
	.story-card p { margin: 0.3rem 0; font-size: 0.88rem; color: #bdc1c6; }
	.story-card .meta { font-size: 0.82rem; color: #9aa0a6; }
	.story-card .try { font-size: 0.85rem; background: #13151a; border-radius: 6px; padding: 0.5rem 0.75rem; margin-top: 0.5rem; }
	.story-card .try strong { color: #8ab4f8; }
	.nav-links { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #2a2f38; font-size: 0.9rem; }
</style>
