<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { goto } from '$app/navigation';

	type Props = {
		mode: 'create' | 'edit';
		storyId?: number;
	};

	let { mode, storyId }: Props = $props();

	let activeTab = $state<'basics' | 'subgraph' | 'shared' | 'characters'>('basics');
	let loadDone = $state(false);
	let saving = $state(false);
	let errors = $state<string[]>([]);

	// Basics
	let title = $state('');
	let description = $state('');
	let genre = $state('');
	let opening = $state('');
	let subgraphName = $state('conversation');
	let notes = $state('');

	// Shared content
	let narratorPrompt = $state('You are the narrator for a text adventure. Describe scenes in second person. End each beat with: What do you do?');
	let narratorModel = $state('default');
	let playerName = $state('Adventurer');
	let playerBackground = $state('');

	// Characters
	type MoodAxis = { axis: string; low: string; high: string; value: number };
	type CharEntry = { key: string; prompt: string; first_line: string; model: string; moods: MoodAxis[] };
	let characterEntries = $state<CharEntry[]>([]);

	function addCharacter() {
		characterEntries = [...characterEntries, { key: '', prompt: '', first_line: '', model: 'default', moods: [{ axis: 'mood', low: 'hostile', high: 'friendly', value: 5 }] }];
	}

	function removeCharacter(idx: number) {
		characterEntries = characterEntries.filter((_, i) => i !== idx);
	}

	function charactersToDict(): Record<string, unknown> {
		const out: Record<string, unknown> = {};
		for (const c of characterEntries) {
			const k = c.key.trim();
			if (!k) continue;
			out[k] = { prompt: c.prompt, first_line: c.first_line, model: c.model, moods: c.moods };
		}
		return out;
	}

	function dictToCharEntries(d: Record<string, unknown>): CharEntry[] {
		return Object.entries(d).map(([key, val]) => {
			const v = val as Record<string, unknown>;
			let moods: MoodAxis[] = [];
			if (Array.isArray(v.moods)) {
				moods = (v.moods as Record<string, unknown>[]).map(m => ({
					axis: String(m.axis ?? 'mood'),
					low: String(m.low ?? 'low'),
					high: String(m.high ?? 'high'),
					value: Number(m.value ?? 5),
				}));
			} else if (v.mood !== undefined) {
				moods = [{ axis: 'mood', low: 'hostile', high: 'friendly', value: Number(v.mood ?? 5) }];
			}
			return {
				key,
				prompt: String(v.prompt ?? ''),
				first_line: String(v.first_line ?? ''),
				model: String(v.model ?? 'default'),
				moods,
			};
		});
	}

	// AI
	let concept = $state('');
	let generating = $state(false);
	let genError = $state('');
	let genOk = $state('');

	// Improve / Instruct
	let improvingField = $state('');
	let instructingField = $state('');
	let instructInput = $state('');

	// Suggest
	type TextSuggestion = { text: string };
	type AxisSuggestion = { axis: string; low: string; high: string };
	let suggestingField = $state('');
	let suggestions = $state<(TextSuggestion | AxisSuggestion)[]>([]);
	let suggestExtra = $state<Record<string, string>>({});

	async function fetchSuggestions(field: string, extra?: Record<string, string>, current?: string) {
		suggestingField = field;
		suggestions = [];
		suggestExtra = extra ?? {};
		try {
			const r = await fetch('/api/ai/suggest', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					field,
					context: { ...buildContext(), ...extra },
					current: current ?? '',
					count: 5,
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && Array.isArray(j.suggestions)) {
				suggestions = j.suggestions;
			}
		} catch { /* ignore */ }
		if (suggestions.length === 0) suggestingField = '';
	}

	function closeSuggest() {
		suggestingField = '';
		suggestions = [];
	}

	// Subgraphs list
	let subgraphs = $state<{ name: string; description: string }[]>([]);

	// Derived
	let charCount = $derived(characterEntries.length);
	let isAiBusy = $derived(generating || improvingField !== '');

	const GENRES = ['mystery', 'thriller', 'drama', 'comedy', 'sci-fi', 'horror', 'fantasy'];

	onMount(async () => {
		try {
			const r = await fetch('/api/subgraphs', { credentials: 'include' });
			if (r.ok) {
				const data = await r.json();
				subgraphs = (Array.isArray(data) ? data : []).map((s: Record<string, unknown>) => ({
					name: String(s.name ?? ''),
					description: String(s.description ?? ''),
				}));
			}
		} catch { /* ignore */ }

		if (mode === 'edit' && storyId) {
			try {
				const r = await fetch(`/api/stories/${storyId}`, { credentials: 'include' });
				if (r.ok) {
					const s = await r.json();
					title = s.title ?? '';
					description = s.description ?? '';
					genre = s.genre ?? '';
					opening = s.opening ?? '';
					subgraphName = s.subgraph_name ?? 'conversation';
					notes = s.notes ?? '';
					narratorPrompt = s.narrator_prompt ?? '';
					narratorModel = s.narrator_model ?? 'default';
					playerName = s.player_name ?? 'Adventurer';
					playerBackground = s.player_background ?? '';
					if (s.characters && typeof s.characters === 'object') {
						characterEntries = dictToCharEntries(s.characters);
					}
				}
			} catch { /* ignore */ }
		}

		loadDone = true;
	});

	async function save() {
		errors = [];
		if (!title.trim()) { errors = ['Title is required']; return; }
		saving = true;
		try {
			const body = {
				title: title.trim(),
				description: description.trim(),
				genre,
				opening: opening.trim(),
				subgraph_name: subgraphName,
				narrator_prompt: narratorPrompt.trim(),
				narrator_model: narratorModel.trim() || 'default',
				player_name: playerName.trim() || 'Adventurer',
				player_background: playerBackground.trim(),
				characters: charactersToDict(),
				notes: notes.trim(),
			};
			const url = mode === 'edit' ? `/api/stories/${storyId}` : '/api/stories';
			const method = mode === 'edit' ? 'PUT' : 'POST';
			const r = await fetch(url, {
				method, credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			const j = await r.json().catch(() => ({}));
			if (!r.ok) {
				const e = j.errors ?? (j.error ? [j.error] : ['Save failed']);
				errors = Array.isArray(e) ? e : [String(e)];
				return;
			}
			await goto('/stories');
		} catch {
			errors = ['Network error'];
		} finally {
			saving = false;
		}
	}

	async function generate() {
		if (!concept.trim()) return;
		generating = true;
		genError = '';
		genOk = '';
		try {
			const r = await fetch('/api/ai/generate-story', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ concept: concept.trim() }),
			});
			const j = await r.json().catch(() => ({}));
			if (!r.ok) { genError = j.error ?? 'Generation failed'; return; }
			const s = j.story ?? {};
			if (s.title) title = s.title;
			if (s.description) description = s.description;
			if (s.genre) genre = s.genre;
			if (s.opening) opening = s.opening;
			if (s.narrator_prompt) narratorPrompt = s.narrator_prompt;
			if (s.player_name) playerName = s.player_name;
			if (s.player_background) playerBackground = s.player_background;
			genOk = 'Story generated! Review and edit the fields above.';
		} catch {
			genError = 'Network error';
		} finally {
			generating = false;
		}
	}

	function buildContext(extra?: Record<string, string>): Record<string, string> {
		const ctx: Record<string, string> = {
			title, genre, narrator_prompt: narratorPrompt,
			player_name: playerName, player_background: playerBackground,
		};
		if (extra) Object.assign(ctx, extra);
		return ctx;
	}

	async function improve(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>) {
		const text = getText();
		if (!text.trim()) return;
		improvingField = field;
		try {
			const r = await fetch('/api/ai/improve-text', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ field, text: text.trim(), context: buildContext(extra) }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.text) { setText(j.text); }
		} catch { /* ignore */ }
		improvingField = '';
	}

	async function instruct(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>) {
		const text = getText();
		if (!text.trim() || !instructInput.trim()) return;
		instructingField = field;
		try {
			const r = await fetch('/api/ai/improve-text', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ field, text: text.trim(), instruction: instructInput.trim(), context: buildContext(extra) }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.text) { setText(j.text); }
		} catch { /* ignore */ }
		instructingField = '';
		instructInput = '';
	}
</script>

{#snippet aiButtons(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>)}
	{@const tips: Record<string, { improve: string; instruct: string; placeholder: string }> = {
		opening: {
			improve: 'AI rewrites: tighten prose, strengthen atmosphere, keep second person',
			instruct: 'Tell the AI what to change — e.g. "make it more suspenseful" or "add rain"',
			placeholder: 'e.g. make it darker and more mysterious',
		},
		description: {
			improve: 'AI rewrites: punchier, 1-2 sentences, no spoilers',
			instruct: 'Tell the AI what to change — e.g. "emphasize the danger"',
			placeholder: 'e.g. focus on the mystery angle',
		},
		notes: {
			improve: 'AI rewrites: clearer, more helpful, explains what the story demonstrates',
			instruct: 'Tell the AI what to add — e.g. "mention the mood system" or "add tips for new players"',
			placeholder: 'e.g. explain how the conditional edge works in this story',
		},
		narrator_prompt: {
			improve: 'AI rewrites: clearer instructions about tone, pacing, and style',
			instruct: 'Tell the AI what to change — e.g. "add a rule about short responses"',
			placeholder: 'e.g. make the narrator more humorous',
		},
		player_background: {
			improve: 'AI rewrites: more concrete and vivid, better context for the narrator',
			instruct: 'Tell the AI what to change — e.g. "make them younger" or "add a fear"',
			placeholder: 'e.g. add a reason they need this job',
		},
		character_prompt: {
			improve: 'AI rewrites: sharper personality, distinct speech patterns and quirks',
			instruct: 'Tell the AI what to change — e.g. "add a secret" or "make them speak in slang"',
			placeholder: 'e.g. give them a nervous habit',
		},
		character_first_line: {
			improve: 'AI rewrites: more natural, in-character, reveals personality instantly',
			instruct: 'Tell the AI what to change — e.g. "make it a question" or "more hostile"',
			placeholder: 'e.g. make it sound more desperate',
		},
	}}
	{@const tip = tips[field] ?? { improve: 'AI improves this text', instruct: 'Tell the AI what to change', placeholder: 'What should change?' }}
	<div class="ai-row">
		<button type="button" class="btn sm" disabled={improvingField === field || !getText().trim()}
			title={tip.improve}
			onclick={() => improve(field, getText, setText, extra)}>
			{improvingField === field ? 'Improving…' : 'Improve'}
		</button>
		{#if instructingField === field}
			<div class="instruct-row" transition:fade={{ duration: 100 }}>
				<input type="text" class="instruct-input" placeholder={tip.placeholder} bind:value={instructInput}
					title={tip.instruct}
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); instruct(field, getText, setText, extra); } }} />
				<button type="button" class="btn sm" disabled={!instructInput.trim()}
					title="Send your instruction to the AI"
					onclick={() => instruct(field, getText, setText, extra)}>Apply</button>
				<button type="button" class="btn sm"
					title="Cancel without changes"
					onclick={() => { instructingField = ''; instructInput = ''; }}>Cancel</button>
			</div>
		{:else}
			<button type="button" class="btn sm" disabled={!getText().trim()}
				title={tip.instruct}
				onclick={() => { instructingField = field; instructInput = ''; }}>
				Instruct
			</button>
		{/if}
	</div>
{/snippet}

{#snippet suggestBtn(field: string, onPick: (s: TextSuggestion | AxisSuggestion) => void, tooltip: string, extra?: Record<string, string>, current?: string)}
	<div class="suggest-wrap">
		<button type="button" class="btn sm suggest-btn"
			title={tooltip}
			disabled={suggestingField === field}
			onclick={() => fetchSuggestions(field, extra, current)}>
			{suggestingField === field ? '...' : '💡'}
		</button>
		{#if suggestingField === field && suggestions.length > 0}
			<div class="suggest-popup" transition:fade={{ duration: 100 }}>
				<div class="suggest-header">
					<strong>Suggestions</strong>
					<button type="button" class="btn sm" onclick={closeSuggest}>✕</button>
				</div>
				<ul class="suggest-list">
					{#each suggestions as s, i (i)}
						<li>
							<button type="button" class="suggest-item" onclick={() => { onPick(s); closeSuggest(); }}>
								{#if 'text' in s}
									{s.text}
								{:else if 'axis' in s}
									<span class="axis-preview">{s.axis}</span>
									<span class="axis-range">{s.low} → {s.high}</span>
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
{/snippet}

<h1>{mode === 'edit' ? 'Edit story' : 'Create story'}</h1>
<p><a href="/stories">← Back to stories</a></p>

{#if !loadDone}
	<p class="muted">Loading…</p>
{:else}
	<div class="tabs">
		<button type="button" class:active={activeTab === 'basics'} onclick={() => activeTab = 'basics'}>Basics</button>
		<button type="button" class:active={activeTab === 'subgraph'} onclick={() => activeTab = 'subgraph'}>Subgraph</button>
		<button type="button" class:active={activeTab === 'shared'} onclick={() => activeTab = 'shared'}>Shared Content</button>
		<button type="button" class:active={activeTab === 'characters'} onclick={() => activeTab = 'characters'}>Characters</button>
	</div>

	{#if activeTab === 'basics'}
		<div class="tab-content">
			<div class="field">
				<div class="field-head">
					<strong>Title *</strong>
					{@render suggestBtn('title', (s) => { if ('text' in s) title = s.text; }, 'Suggest titles based on your story')}
				</div>
				<input type="text" bind:value={title} />
			</div>

			<div class="field">
				<strong>Description</strong>
				<span class="hint">Short catalog pitch — 1-2 sentences that make players want to try it.</span>
				<textarea rows="3" bind:value={description}></textarea>
				{@render aiButtons('description', () => description, (v) => description = v)}
			</div>

			<div class="field">
				<strong>Notes</strong>
				<span class="hint">Optional. Explain what this story demonstrates, tips for players, or design notes.</span>
				<textarea rows="2" bind:value={notes}></textarea>
				{@render aiButtons('notes', () => notes, (v) => notes = v)}
			</div>

			<label class="field">
				<strong>Genre</strong>
				<select bind:value={genre}>
					<option value="">— select —</option>
					{#each GENRES as g}<option value={g}>{g}</option>{/each}
				</select>
			</label>

			<div class="field">
				<strong>Opening</strong>
				<span class="hint">Second person, present tense. What the player reads first.</span>
				<textarea rows="4" bind:value={opening}></textarea>
				{@render aiButtons('opening', () => opening, (v) => opening = v)}
			</div>

			<fieldset class="ai-section">
				<legend>AI Generate</legend>
				<span class="hint">Describe your story concept and the AI will generate title, opening, narrator style, and player character. You can edit everything afterward.</span>
				<textarea rows="3" placeholder="Describe your story idea…" bind:value={concept}></textarea>
				<button type="button" class="btn" disabled={generating || !concept.trim()} onclick={() => generate()}>
					{generating ? 'Generating…' : 'Generate'}
				</button>
				{#if genError}<p class="err" transition:fade={{ duration: 150 }}>{genError}</p>{/if}
				{#if genOk}<p class="ok" transition:fade={{ duration: 150 }}>{genOk}</p>{/if}
			</fieldset>
		</div>
	{/if}

	{#if activeTab === 'subgraph'}
		<div class="tab-content">
			<label class="field">
				<strong>Subgraph</strong>
				<span class="hint">The graph pipeline that runs each turn when the player sends a message.</span>
				<select bind:value={subgraphName}>
					{#each subgraphs as sg}
						<option value={sg.name}>{sg.name} — {sg.description || 'no description'}</option>
					{/each}
				</select>
			</label>
			<p class="hint">Manage subgraphs in the <a href="/graphs">Graph Editor</a>.</p>
		</div>
	{/if}

	{#if activeTab === 'shared'}
		<div class="tab-content">
			<div class="field">
				<strong>Narrator Prompt</strong>
				<span class="hint">System instructions for the narrator LLM: tone, pacing, second person, how to end beats. This shapes the voice of your story.</span>
				<textarea rows="4" bind:value={narratorPrompt}></textarea>
				{@render aiButtons('narrator_prompt', () => narratorPrompt, (v) => narratorPrompt = v)}
			</div>

			<label class="field">
				<strong>Narrator Model</strong>
				<span class="hint">Leave as "default" to use the server's configured model.</span>
				<input type="text" bind:value={narratorModel} placeholder="default" />
			</label>

			<div class="field">
				<div class="field-head">
					<strong>Player Name</strong>
					{@render suggestBtn('player_name', (s) => { if ('text' in s) playerName = s.text; }, 'Suggest names that fit the genre and setting')}
				</div>
				<span class="hint">Who the player is in the story world.</span>
				<input type="text" bind:value={playerName} />
			</div>

			<div class="field">
				<strong>Player Background</strong>
				<span class="hint">Player character history and situation — concrete, playable, gives the narrator context for the story.</span>
				<textarea rows="3" bind:value={playerBackground}></textarea>
				{@render aiButtons('player_background', () => playerBackground, (v) => playerBackground = v)}
			</div>
		</div>
	{/if}

	{#if activeTab === 'characters'}
		<div class="tab-content">
			{#if characterEntries.length === 0}
				<p class="muted">No characters yet. Add one to bring NPCs into the story.</p>
			{/if}

			{#each characterEntries as char, idx (idx)}
				<fieldset class="char-card">
					<legend>Character {idx + 1}</legend>

					<label class="field">
						<strong>Key *</strong>
						<span class="hint">Snake_case identifier (e.g. bartender, old_tom)</span>
						<input type="text" bind:value={char.key} placeholder="e.g. bartender" />
					</label>

					<div class="field">
						<strong>Personality Prompt *</strong>
						<span class="hint">Instructions for how this NPC speaks and behaves.</span>
						<textarea rows="3" bind:value={char.prompt} placeholder="You are a grumpy bartender who's seen too much..."></textarea>
						{@render aiButtons('character_prompt', () => char.prompt, (v) => char.prompt = v, { character_key: char.key })}
					</div>

					<div class="field">
						<strong>First Line</strong>
						<span class="hint">What they say at the start of the game. Should match their personality.</span>
						<input type="text" bind:value={char.first_line} placeholder="What'll it be?" />
						{@render aiButtons('character_first_line', () => char.first_line, (v) => char.first_line = v, { character_key: char.key, character_prompt: char.prompt })}
					</div>

					<div class="field">
						<div class="field-head">
							<strong>Mood Axes</strong>
							{@render suggestBtn(
								'mood_axis_new',
								(s) => { if ('axis' in s) char.moods = [...char.moods, { axis: s.axis, low: s.low, high: s.high, value: 5 }]; },
								'Suggest new mood axes based on this character',
								{ character_key: char.key, character_prompt: char.prompt, existing_axes: char.moods.map(a => a.axis).join(', ') }
							)}
						</div>
						<span class="hint">Each axis is a scale between two emotions. The mood node adjusts these each turn.</span>
						{#each char.moods as axis, ai (ai)}
							<div class="axis-row">
								<input type="text" bind:value={axis.axis} placeholder="axis name" class="axis-input" />
								<input type="text" bind:value={axis.low} placeholder="low label" class="axis-input" />
								<span class="axis-arrow">←→</span>
								<input type="text" bind:value={axis.high} placeholder="high label" class="axis-input" />
								<input type="number" min="1" max="10" bind:value={axis.value} class="axis-value" />
								{@render suggestBtn(
									'mood_axis_refine',
									(s) => { if ('axis' in s) { axis.axis = s.axis; axis.low = s.low; axis.high = s.high; } },
									'Suggest better labels for this axis',
									{ character_key: char.key, character_prompt: char.prompt },
									`${axis.axis}|${axis.low}|${axis.high}`
								)}
								<button type="button" class="btn sm danger" onclick={() => { char.moods = char.moods.filter((_, i) => i !== ai); }}>×</button>
							</div>
						{/each}
						<button type="button" class="btn sm" onclick={() => { char.moods = [...char.moods, { axis: '', low: '', high: '', value: 5 }]; }}>Add axis</button>
					</div>

					<button type="button" class="btn sm danger" onclick={() => removeCharacter(idx)}>Remove character</button>
				</fieldset>
			{/each}

			<button type="button" class="btn" onclick={() => addCharacter()}>Add character</button>
		</div>
	{/if}

	{#if errors.length > 0}
		<div class="err-box">{#each errors as e}<p class="err">{e}</p>{/each}</div>
	{/if}

	<div class="actions">
		<button type="button" class="btn primary" disabled={saving} onclick={() => save()}>
			{saving ? 'Saving…' : 'Save story'}
		</button>
		<a href="/stories">Cancel</a>
	</div>
{/if}

<style>
	.tabs { display: flex; gap: 0; margin-bottom: 1rem; border-bottom: 2px solid #2a2f38; }
	.tabs button { padding: 0.5rem 1rem; border: 1px solid #2a2f38; border-bottom: none; background: #1a1d23; color: #9aa0a6; cursor: pointer; font: inherit; border-radius: 8px 8px 0 0; margin-bottom: -2px; }
	.tabs button.active { background: #0f1114; color: #e8eaed; border-bottom: 2px solid #0f1114; font-weight: 600; }
	.tab-content { max-width: 700px; }
	.field { display: block; margin-bottom: 1rem; }
	.field strong { display: block; margin-bottom: 0.25rem; }
	.field input, .field textarea, .field select { width: 100%; box-sizing: border-box; }
	.hint { display: block; font-size: 0.82rem; color: #9aa0a6; margin-bottom: 0.3rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; margin-top: 0.3rem; }
	.ai-section { border: 1px solid #2a2f38; padding: 1rem; border-radius: 8px; margin-top: 1.5rem; background: #1a1d23; }
	.ai-section textarea { width: 100%; box-sizing: border-box; margin-bottom: 0.5rem; }
	.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2f38; }
	.err { color: #f28b82; margin: 0.25rem 0; }
	.err-box { margin-top: 1rem; }
	.ok { color: #81c995; margin: 0.25rem 0; }
	.muted { color: #9aa0a6; }
	.char-card { border: 1px solid #2a2f38; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; background: #1a1d23; }
	.axis-row { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
	.axis-input { width: 6rem; }
	.axis-value { width: 3.5rem; }
	.axis-arrow { color: #9aa0a6; font-size: 0.85rem; }
	.danger { color: #f28b82; border-color: #c5221f; }
	.field-head { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.25rem; }
	.field-head strong { margin-bottom: 0; }
	.ai-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; margin-top: 0.35rem; }
	.instruct-row { display: flex; align-items: center; gap: 0.35rem; flex: 1; min-width: 14rem; }
	.instruct-input { flex: 1; font-size: 0.85rem; padding: 0.3rem 0.5rem; }
	.suggest-wrap { position: relative; display: inline-block; }
	.suggest-btn { font-size: 0.9rem; padding: 0.15rem 0.4rem; line-height: 1; min-width: unset; }
	.suggest-popup { position: absolute; top: 100%; left: 0; z-index: 100; min-width: 16rem; max-width: 22rem; background: #1a1d23; border: 1px solid #3c4043; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); margin-top: 0.25rem; }
	.suggest-header { display: flex; align-items: center; justify-content: space-between; padding: 0.4rem 0.65rem; border-bottom: 1px solid #2a2f38; }
	.suggest-header strong { font-size: 0.82rem; color: #9aa0a6; }
	.suggest-list { list-style: none; margin: 0; padding: 0.25rem 0; }
	.suggest-item { display: block; width: 100%; text-align: left; background: none; border: none; color: #e8eaed; padding: 0.45rem 0.65rem; font: inherit; font-size: 0.88rem; cursor: pointer; line-height: 1.4; }
	.suggest-item:hover { background: #2a2f38; }
	.axis-preview { font-weight: 600; margin-right: 0.35rem; }
	.axis-range { color: #9aa0a6; font-size: 0.82rem; }
</style>
