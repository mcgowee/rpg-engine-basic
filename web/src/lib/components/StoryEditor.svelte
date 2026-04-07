<script lang="ts">
	import { onMount } from 'svelte';
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

	// Improve
	let improvingField = $state('');

	// Subgraphs list
	let subgraphs = $state<{ name: string; description: string }[]>([]);

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

	async function improve(field: string, getText: () => string, setText: (v: string) => void) {
		const text = getText();
		if (!text.trim()) return;
		improvingField = field;
		try {
			const r = await fetch('/api/ai/improve-text', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ field, text: text.trim() }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.text) { setText(j.text); }
		} catch { /* ignore */ }
		improvingField = '';
	}
</script>

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
			<label class="field">
				<strong>Title *</strong>
				<input type="text" bind:value={title} />
			</label>

			<div class="field">
				<strong>Description</strong>
				<span class="hint">Short catalog pitch — 1-2 sentences that make players want to try it.</span>
				<textarea rows="3" bind:value={description}></textarea>
			</div>

			<div class="field">
				<strong>Notes</strong>
				<span class="hint">Optional. Explain what this story demonstrates, tips for players, or design notes.</span>
				<textarea rows="2" bind:value={notes}></textarea>
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
				<button type="button" class="btn sm" disabled={improvingField === 'opening' || !opening.trim()}
					onclick={() => improve('opening', () => opening, (v) => opening = v)}>
					{improvingField === 'opening' ? 'Improving…' : 'Improve'}
				</button>
			</div>

			<fieldset class="ai-section">
				<legend>AI Generate</legend>
				<span class="hint">Describe your story concept and the AI will generate title, opening, narrator style, and player character. You can edit everything afterward.</span>
				<textarea rows="3" placeholder="Describe your story idea…" bind:value={concept}></textarea>
				<button type="button" class="btn" disabled={generating || !concept.trim()} onclick={() => generate()}>
					{generating ? 'Generating…' : 'Generate'}
				</button>
				{#if genError}<p class="err">{genError}</p>{/if}
				{#if genOk}<p class="ok">{genOk}</p>{/if}
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
				<button type="button" class="btn sm" disabled={improvingField === 'narrator_prompt' || !narratorPrompt.trim()}
					onclick={() => improve('narrator_prompt', () => narratorPrompt, (v) => narratorPrompt = v)}>
					{improvingField === 'narrator_prompt' ? 'Improving…' : 'Improve'}
				</button>
			</div>

			<label class="field">
				<strong>Narrator Model</strong>
				<span class="hint">Leave as "default" to use the server's configured model.</span>
				<input type="text" bind:value={narratorModel} placeholder="default" />
			</label>

			<label class="field">
				<strong>Player Name</strong>
				<span class="hint">Who the player is in the story world.</span>
				<input type="text" bind:value={playerName} />
			</label>

			<div class="field">
				<strong>Player Background</strong>
				<span class="hint">Player character history and situation — concrete, playable, gives the narrator context for the story.</span>
				<textarea rows="3" bind:value={playerBackground}></textarea>
				<button type="button" class="btn sm" disabled={improvingField === 'player_background' || !playerBackground.trim()}
					onclick={() => improve('player_background', () => playerBackground, (v) => playerBackground = v)}>
					{improvingField === 'player_background' ? 'Improving…' : 'Improve'}
				</button>
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
					</div>

					<label class="field">
						<strong>First Line</strong>
						<span class="hint">What they say at the start of the game.</span>
						<input type="text" bind:value={char.first_line} placeholder="What'll it be?" />
					</label>

					<div class="field">
						<strong>Mood Axes</strong>
						<span class="hint">Each axis is a scale between two emotions. The mood node adjusts these each turn.</span>
						{#each char.moods as axis, ai (ai)}
							<div class="axis-row">
								<input type="text" bind:value={axis.axis} placeholder="axis name" class="axis-input" />
								<input type="text" bind:value={axis.low} placeholder="low label" class="axis-input" />
								<span class="axis-arrow">←→</span>
								<input type="text" bind:value={axis.high} placeholder="high label" class="axis-input" />
								<input type="number" min="1" max="10" bind:value={axis.value} class="axis-value" />
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
	.tabs { display: flex; gap: 0; margin-bottom: 1rem; border-bottom: 2px solid #ccc; }
	.tabs button { padding: 0.5rem 1rem; border: 1px solid #ccc; border-bottom: none; background: #f5f5f5; cursor: pointer; font: inherit; border-radius: 4px 4px 0 0; margin-bottom: -2px; }
	.tabs button.active { background: #fff; border-bottom: 2px solid #fff; font-weight: 600; }
	.tab-content { max-width: 700px; }
	.field { display: block; margin-bottom: 1rem; }
	.field strong { display: block; margin-bottom: 0.25rem; }
	.field input, .field textarea, .field select { width: 100%; font: inherit; padding: 0.4rem 0.5rem; border: 1px solid #aaa; border-radius: 4px; box-sizing: border-box; }
	.field textarea { resize: vertical; }
	.hint { display: block; font-size: 0.85rem; color: #666; margin-bottom: 0.3rem; }
	.btn { padding: 0.4rem 0.75rem; cursor: pointer; border: 1px solid #999; background: #fff; border-radius: 4px; font: inherit; }
	.btn.primary { background: #1a1a8c; color: #fff; border-color: #1a1a8c; }
	.btn:disabled { opacity: 0.65; cursor: not-allowed; }
	.btn.sm { font-size: 0.85rem; padding: 0.2rem 0.5rem; margin-top: 0.3rem; }
	.ai-section { border: 1px solid #ddd; padding: 1rem; border-radius: 4px; margin-top: 1.5rem; }
	.ai-section legend { font-weight: 600; }
	.ai-section textarea { width: 100%; font: inherit; padding: 0.4rem 0.5rem; border: 1px solid #aaa; border-radius: 4px; box-sizing: border-box; margin-bottom: 0.5rem; }
	.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #ddd; }
	.err { color: #b00020; margin: 0.25rem 0; }
	.err-box { margin-top: 1rem; }
	.ok { color: #1b5e20; margin: 0.25rem 0; }
	.muted { color: #666; }
	.char-card { border: 1px solid #ddd; padding: 1rem; border-radius: 4px; margin-bottom: 1rem; }
	.char-card legend { font-weight: 600; }
	.axis-row { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
	.axis-input { width: 6rem; font: inherit; padding: 0.3rem 0.4rem; border: 1px solid #aaa; border-radius: 4px; }
	.axis-value { width: 3.5rem; font: inherit; padding: 0.3rem 0.4rem; border: 1px solid #aaa; border-radius: 4px; }
	.axis-arrow { color: #888; font-size: 0.85rem; }
	.danger { color: #b00020; border-color: #b00020; }
	a { color: #0066cc; }
</style>
