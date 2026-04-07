<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type Props = {
		mode: 'create' | 'edit';
		storyId?: number;
	};

	let { mode, storyId }: Props = $props();

	let activeTab = $state<'basics' | 'subgraph' | 'shared'>('basics');
	let loadDone = $state(false);
	let saving = $state(false);
	let errors = $state<string[]>([]);

	// Basics
	let title = $state('');
	let description = $state('');
	let genre = $state('');
	let opening = $state('');
	let subgraphName = $state('conversation');

	// Shared content
	let narratorPrompt = $state('You are the narrator for a text adventure. Describe scenes in second person. End each beat with: What do you do?');
	let narratorModel = $state('default');
	let playerName = $state('Adventurer');
	let playerBackground = $state('');

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
					narratorPrompt = s.narrator_prompt ?? '';
					narratorModel = s.narrator_model ?? 'default';
					playerName = s.player_name ?? 'Adventurer';
					playerBackground = s.player_background ?? '';
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
	</div>

	{#if activeTab === 'basics'}
		<div class="tab-content">
			<label class="field">
				<strong>Title *</strong>
				<input type="text" bind:value={title} />
			</label>

			<label class="field">
				<strong>Description</strong>
				<textarea rows="3" bind:value={description}></textarea>
			</label>

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
				<textarea rows="4" bind:value={narratorPrompt}></textarea>
				<button type="button" class="btn sm" disabled={improvingField === 'narrator_prompt' || !narratorPrompt.trim()}
					onclick={() => improve('narrator_prompt', () => narratorPrompt, (v) => narratorPrompt = v)}>
					{improvingField === 'narrator_prompt' ? 'Improving…' : 'Improve'}
				</button>
			</div>

			<label class="field">
				<strong>Narrator Model</strong>
				<input type="text" bind:value={narratorModel} placeholder="default" />
			</label>

			<label class="field">
				<strong>Player Name</strong>
				<input type="text" bind:value={playerName} />
			</label>

			<div class="field">
				<strong>Player Background</strong>
				<textarea rows="3" bind:value={playerBackground}></textarea>
				<button type="button" class="btn sm" disabled={improvingField === 'player_background' || !playerBackground.trim()}
					onclick={() => improve('player_background', () => playerBackground, (v) => playerBackground = v)}>
					{improvingField === 'player_background' ? 'Improving…' : 'Improve'}
				</button>
			</div>
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
	a { color: #0066cc; }
</style>
