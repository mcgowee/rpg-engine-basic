<svelte:head>
	<title>Creating Stories — RPG Engine Docs</title>
</svelte:head>

<section class="docs">
	<p class="breadcrumb"><a href="/docs">Docs</a> / Creating Stories</p>
	<div class="doc-hero">
		<img src="/images/docs-stories-hero.png" alt="Story creator writing a magical adventure" />
	</div>
	<h1>Creating Stories</h1>
	<p class="lede">How to build your own text adventures — from simple narrator-only stories to multi-character dramas with mood tracking.</p>

	<div class="section">
		<h2>Quick Start</h2>
		<ol>
			<li>Go to <a href="/stories/create">Create Story</a></li>
			<li>Fill in a title, description, and opening text</li>
			<li>Pick a subgraph (start with <code>conversation</code> — default)</li>
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
		<p>
			Which graph pipeline runs each turn. This is the most important choice — it determines what the engine does with the player's input.
			See <a href="/docs/subgraphs">Subgraphs</a> for a full comparison of builtins, or <a href="/docs/engine">Engine Reference</a> for nodes and routers.
		</p>
		<div class="tip">
			<strong>Which subgraph should I pick?</strong>
			<ul>
				<li><code>basic_narrator</code> — narrator only. Best for minimal or one-shot stories.</li>
				<li><code>conversation</code> — narrator + <code>memory</code> (no NPC/condense). Good default; use <code>full_conversation</code> for a rolling AI summary on long arcs.</li>
				<li><code>full_conversation</code> — adds condense + memory summary. Good for longer stories.</li>
				<li><code>smart_conversation</code> — adds NPCs that respond in character. Automatically skips NPC step if no characters defined.</li>
				<li><code>full_memory</code> — narrator → mood → NPC → condense → memory (no narrator coda; linear flow).</li>
				<li><code>full_story</code> — mood + NPC + narrator coda + condense + memory; skips mood/NPC/coda when no characters. Best default for character-driven stories with mood axes.</li>
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
		<p>NPCs that respond in character each turn. Only used if your subgraph includes the <code>npc</code> node (<code>smart_conversation</code> or <code>full_story</code> — or <code>full_memory</code> and similar).</p>
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

	<div class="section" id="builtin-stories">
		<h2>Builtin Stories</h2>
		<p>
			These stories are seeded into every fresh database from <code>stories/*.json</code>. Each demonstrates a different engine feature.
			Copy one to your account to experiment with it. The table lists every seed; below it, a few stories have longer “things to try” notes.
		</p>

		<div class="table-wrap">
			<table class="tbl tbl-stories">
				<thead>
					<tr>
						<th>Story</th>
						<th>Genre</th>
						<th>Subgraph</th>
						<th>NPCs</th>
						<th class="tbl-notes">Notes</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td>The Midnight Lighthouse</td>
						<td>mystery</td>
						<td><code>conversation</code></td>
						<td>0</td>
						<td>Narrator + memory; default-style solo arc.</td>
					</tr>
					<tr>
						<td>The Last Train</td>
						<td>thriller</td>
						<td><code>smart_conversation</code></td>
						<td>2</td>
						<td>Two distinct NPC voices.</td>
					</tr>
					<tr>
						<td>Meet Cute (In Theory)</td>
						<td>romance</td>
						<td><code>smart_conversation</code></td>
						<td>2</td>
						<td>Rom-com café; same two-NPC tutorial as Last Train, warmer tone.</td>
					</tr>
					<tr>
						<td>Open Mic Nightmare</td>
						<td>comedy</td>
						<td><code>conversation</code></td>
						<td>0</td>
						<td>Pure comedy; narrator + memory for callbacks (no NPCs).</td>
					</tr>
					<tr>
						<td>The Job Interview</td>
						<td>drama</td>
						<td><code>full_story</code></td>
						<td>2</td>
						<td>Mood axes + narrator coda.</td>
					</tr>
					<tr>
						<td>The Interrogation</td>
						<td>thriller</td>
						<td><code>full_story</code></td>
						<td>1</td>
						<td>Multiple mood axes on one character.</td>
					</tr>
					<tr>
						<td>Spy Thriller: Narrator Only</td>
						<td>thriller</td>
						<td><code>basic_narrator</code></td>
						<td>0</td>
						<td>Tutorial 1/5 — narrator only, no in-graph memory.</td>
					</tr>
					<tr>
						<td>Spy Thriller: Rolling Memory</td>
						<td>thriller</td>
						<td><code>full_conversation</code></td>
						<td>0</td>
						<td>Tutorial 2/5 — condense + rolling AI summary.</td>
					</tr>
					<tr>
						<td>Spy Thriller: Meet the Handler</td>
						<td>thriller</td>
						<td><code>smart_conversation</code></td>
						<td>1</td>
						<td>Tutorial 3/5 — NPC dialogue + narrator coda.</td>
					</tr>
					<tr>
						<td>Spy Thriller: Trust &amp; Tension</td>
						<td>thriller</td>
						<td><code>full_memory</code></td>
						<td>1</td>
						<td>Tutorial 4/5 — mood axes + fixed mood→NPC chain.</td>
					</tr>
					<tr>
						<td>Spy Thriller: Full Pipeline</td>
						<td>thriller</td>
						<td><code>full_story</code></td>
						<td>2</td>
						<td>Tutorial 5/5 — full_story; coda + conditional routing.</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="hint">
			<strong>Fun &amp; tutorials:</strong> <strong>Meet Cute (In Theory)</strong> — PG rom-com, two NPCs (same <code>smart_conversation</code> idea as <strong>The Last Train</strong>). <strong>Open Mic Nightmare</strong> — pure <strong>comedy</strong>, solo, <code>conversation</code> so jokes can callback across turns.
			<strong>Spy Thriller tutorials (1–5):</strong> same embassy gala premise — <strong>Narrator Only</strong> → <strong>Rolling Memory</strong> → <strong>Meet the Handler</strong> → <strong>Trust &amp; Tension</strong> → <strong>Full Pipeline</strong>
			(subgraphs <code>basic_narrator</code> → <code>full_conversation</code> → <code>smart_conversation</code> → <code>full_memory</code> → <code>full_story</code>).
			<a href="https://github.com/mcgowee/rpg-engine-basic/blob/main/docs/BUILTIN_STORIES.md" target="_blank" rel="noopener noreferrer"
				>Repo table with filenames</a
			>
			— keep in sync when adding seeds.
		</p>

		<h3>Examples (things to try)</h3>

		<div class="story-card">
			<h3>The Midnight Lighthouse</h3>
			<p class="meta">Mystery · <code>conversation</code> · No characters</p>
			<p>Solo exploration. Uses the default <code>conversation</code> graph (narrator + memory). The narrator describes scenes and remembers previous turns.</p>
			<p class="try"><strong>Try:</strong> Play several turns, then reference something from earlier. Copy and change the narrator prompt to shift the tone.</p>
		</div>

		<div class="story-card">
			<h3>The Last Train</h3>
			<p class="meta">Thriller · <code>smart_conversation</code> · Diana, Gerald</p>
			<p>Two NPCs with distinct personalities on a late-night train. Demonstrates multiple characters responding independently.</p>
			<p class="try"><strong>Try:</strong> Address one character directly and see how both still respond in character. To see <code>route_after_narrator</code> skip the NPC path, copy <strong>Spy Thriller: Meet the Handler</strong>, delete its characters in the editor, and play — same subgraph, fewer nodes run.</p>
		</div>

		<div class="story-card">
			<h3>Meet Cute (In Theory)</h3>
			<p class="meta">Romance · <code>smart_conversation</code> · Jamie, Riley</p>
			<p>
				A dating-app brunch in a busy café: your date (Jamie) and a barista (Riley) who won’t let the moment be boring. Same engine path as <em>The Last Train</em>, but built for laughs and chemistry instead of suspense.
			</p>
			<p class="try"><strong>Try:</strong> Play for banter first — then copy the story and crank the narrator prompt toward full farce or full earnest romance to see how tone shifts.</p>
		</div>

		<div class="story-card">
			<h3>Open Mic Nightmare</h3>
			<p class="meta">Comedy · <code>conversation</code> · No characters</p>
			<p>
				A doomed five-minute stand-up set: hostile host, pitying crowd, escalating absurdity. No NPCs — comedy comes from the narrator and your choices, with memory so running gags can land.
			</p>
			<p class="try"><strong>Try:</strong> Reference an earlier bit on a later turn and watch the narrator pick it up. Tighten or loosen the narrator prompt to swing from dry wit to full cartoon.</p>
		</div>

		<div class="story-card">
			<h3>The Job Interview</h3>
			<p class="meta">Drama · <code>full_story</code> · Ms. Chen (5), Big Dave (7)</p>
			<p>Two interviewers with opposite personalities. Demonstrates mood tracking — watch sidebar numbers change based on your answers.</p>
			<p class="try"><strong>Try:</strong> Give confident vs. evasive answers. Change starting moods and replay to see how it affects the dynamic from turn one.</p>
		</div>

		<div class="story-card">
			<h3>The Interrogation</h3>
			<p class="meta">Thriller · <code>full_story</code> · Marcus Webb (3 axes)</p>
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
	.doc-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.doc-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
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
	.table-wrap { overflow-x: auto; margin: 0.75rem 0 1rem; -webkit-overflow-scrolling: touch; }
	.tbl { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	.tbl th,
	.tbl td { border: 1px solid #2a2f38; padding: 0.45rem 0.55rem; text-align: left; vertical-align: top; }
	.tbl th { background: #1a1d23; color: #9aa0a6; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; }
	.tbl code { font-size: 0.82rem; }
	.tbl-stories .tbl-notes { min-width: 11rem; }
	.hint { font-size: 0.85rem; color: #9aa0a6; margin: 0.75rem 0 1.25rem; line-height: 1.5; }
	.hint a { font-weight: 600; }
	.nav-links { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #2a2f38; font-size: 0.9rem; }
	:global([data-theme="light"]) .section h2,
	:global([data-theme="light"]) .nav-links { border-bottom-color: #dfe3e8; border-top-color: #dfe3e8; }
	:global([data-theme="light"]) .section p,
	:global([data-theme="light"]) .section li,
	:global([data-theme="light"]) .field-list dd,
	:global([data-theme="light"]) .story-card p { color: #334155; }
	:global([data-theme="light"]) .tip,
	:global([data-theme="light"]) .example-box,
	:global([data-theme="light"]) .story-card .try { background: #f8fafc; border: 1px solid #dfe3e8; }
	:global([data-theme="light"]) .story-card { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .doc-hero { border-color: #dfe3e8; }
	:global([data-theme="light"]) .tbl th { background: #f1f5f9; color: #4b5563; }
	:global([data-theme="light"]) .tbl th,
	:global([data-theme="light"]) .tbl td { border-color: #dfe3e8; }
	:global([data-theme="light"]) .hint { color: #64748b; }
</style>
