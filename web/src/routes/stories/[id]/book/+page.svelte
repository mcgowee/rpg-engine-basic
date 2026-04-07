<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { page } from '$app/state';

	let storyId = $derived.by(() => {
		const raw = page.params.id ?? '';
		const n = Number(raw);
		return Number.isFinite(n) ? n : null;
	});

	// Story data
	let title = $state('');
	let genre = $state('');
	let opening = $state('');
	let coverImage = $state('');
	let playerName = $state('');
	let characters = $state<Record<string, Record<string, unknown>>>({});
	let history = $state<string[]>([]);

	// Book state
	let prose = $state('');
	let loading = $state(true);
	let generating = $state(false);
	let error = $state('');

	let sections = $derived(prose ? prose.split(/\n---\n|\n\n---\n\n/).map(s => s.trim()).filter(Boolean) : []);

	// Character portrait lookup
	function getPortrait(name: string): string {
		for (const [key, val] of Object.entries(characters)) {
			const label = key.replace(/_/g, ' ').toLowerCase();
			if (name.toLowerCase().includes(label) || label.includes(name.toLowerCase())) {
				return typeof val.portrait === 'string' ? val.portrait : '';
			}
		}
		return '';
	}

	onMount(async () => {
		if (!storyId) { error = 'Invalid story ID'; loading = false; return; }

		try {
			const r = await fetch(`/api/stories/${storyId}/book-data`, { credentials: 'include' });
			if (!r.ok) {
				error = r.status === 404 ? 'Story not found' : `Failed to load (${r.status})`;
				loading = false;
				return;
			}
			const data = await r.json();
			title = data.title ?? '';
			genre = data.genre ?? '';
			opening = data.opening ?? '';
			coverImage = data.cover_image ?? '';
			playerName = data.player_name ?? '';
			characters = data.characters ?? {};
			history = Array.isArray(data.history) ? data.history : [];

			if (history.length === 0) {
				error = 'No play history yet. Play the story first, then come back to create a book.';
				loading = false;
				return;
			}

			loading = false;
		} catch {
			error = 'Network error';
			loading = false;
		}
	});

	async function generate() {
		generating = true;
		error = '';
		try {
			const r = await fetch('/api/ai/generate-book', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ history, opening, title, player_name: playerName, characters }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.prose) {
				prose = j.prose;
			} else {
				error = j.error ?? 'Generation failed';
			}
		} catch {
			error = 'Network error';
		} finally {
			generating = false;
		}
	}
</script>

<svelte:head>
	<title>{title || 'Story Book'} — RPG Engine</title>
</svelte:head>

<article class="book">
	{#if loading}
		<div class="book-loading">
			<span class="spinner"></span> Loading story data…
		</div>
	{:else if error && !prose}
		<div class="book-error">
			<p class="err">{error}</p>
			<p><a href="/stories">← Back to stories</a></p>
		</div>
	{:else if !prose}
		<!-- Pre-generation view -->
		{#if coverImage}
			<div class="book-cover">
				<img src="/images/covers/{coverImage}" alt="" />
			</div>
		{/if}
		<div class="book-header">
			<h1>{title}</h1>
			{#if genre}<p class="book-genre">{genre}</p>{/if}
			<p class="book-meta">Based on a play session with {history.length} turn{history.length === 1 ? '' : 's'}</p>
		</div>

		<div class="book-generate">
			<p>Transform your play session into a polished short story. The AI will rewrite the game transcript into narrative prose, keeping all the events and dialogue.</p>
			<button type="button" class="btn primary generate-btn" disabled={generating} onclick={() => generate()}>
				{#if generating}<span class="spinner"></span> Writing your story…{:else}Create Story Book{/if}
			</button>
			{#if error}<p class="err">{error}</p>{/if}
		</div>
	{:else}
		<!-- Book view -->
		{#if coverImage}
			<div class="book-cover">
				<img src="/images/covers/{coverImage}" alt="" />
			</div>
		{/if}

		<div class="book-header" transition:fade={{ duration: 200 }}>
			<h1>{title}</h1>
			{#if genre}<p class="book-genre">{genre}</p>{/if}
		</div>

		<div class="book-prose" transition:fade={{ duration: 300 }}>
			{#each sections as section, i (i)}
				<div class="book-section">
					{#each section.split('\n') as para}
						{#if para.trim()}
							<p>{para.trim()}</p>
						{/if}
					{/each}
				</div>
				{#if i < sections.length - 1}
					<hr class="section-divider" />
				{/if}
			{/each}
		</div>

		<div class="book-footer">
			<p class="book-end">— The End —</p>
			<div class="book-actions">
				<button type="button" class="btn" onclick={() => generate()}>
					{generating ? 'Rewriting…' : 'Regenerate'}
				</button>
				<a href="/stories" class="btn">Back to Stories</a>
				<a href="/play?story_id={storyId}" class="btn">Continue Playing</a>
			</div>
		</div>
	{/if}
</article>

<style>
	.book {
		max-width: 700px;
		margin: 0 auto;
		padding: 0 1rem 3rem;
	}
	.book-loading, .book-error {
		text-align: center;
		padding: 3rem 1rem;
		color: #9aa0a6;
	}
	.book-cover {
		margin: 0 -1rem 2rem;
		border-radius: 12px;
		overflow: hidden;
	}
	.book-cover img {
		width: 100%;
		height: auto;
		display: block;
	}
	.book-header {
		text-align: center;
		margin-bottom: 2rem;
	}
	.book-header h1 {
		font-size: 2.2rem;
		margin: 0 0 0.5rem;
		line-height: 1.2;
	}
	.book-genre {
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: #8ab4f8;
		margin: 0 0 0.5rem;
	}
	.book-meta {
		font-size: 0.88rem;
		color: #9aa0a6;
		margin: 0;
	}
	.book-generate {
		text-align: center;
		padding: 2rem;
		border: 1px solid #2a2f38;
		border-radius: 12px;
		background: #1a1d23;
	}
	.book-generate p {
		color: #bdc1c6;
		line-height: 1.6;
		margin: 0 0 1.5rem;
		max-width: 500px;
		margin-left: auto;
		margin-right: auto;
	}
	.generate-btn {
		font-size: 1rem;
		padding: 0.65rem 1.5rem;
	}
	.book-prose {
		font-size: 1.05rem;
		line-height: 1.75;
		color: #e8eaed;
	}
	.book-section p {
		margin: 0 0 1rem;
		text-indent: 1.5rem;
	}
	.book-section p:first-child {
		text-indent: 0;
	}
	.book-section p:first-child::first-letter {
		font-size: 2.5rem;
		float: left;
		line-height: 1;
		margin-right: 0.5rem;
		margin-top: 0.1rem;
		color: #8ab4f8;
		font-weight: 700;
	}
	.section-divider {
		border: none;
		text-align: center;
		margin: 2rem 0;
		color: #5f6368;
	}
	.section-divider::after {
		content: '⁂';
		font-size: 1.2rem;
	}
	.book-footer {
		text-align: center;
		margin-top: 3rem;
		padding-top: 2rem;
		border-top: 1px solid #2a2f38;
	}
	.book-end {
		font-size: 1.1rem;
		font-style: italic;
		color: #9aa0a6;
		margin: 0 0 1.5rem;
	}
	.book-actions {
		display: flex;
		justify-content: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.btn {
		padding: 0.45rem 0.85rem;
		border: 1px solid #3c4043;
		background: #2a2f38;
		color: #e8eaed;
		border-radius: 8px;
		font: inherit;
		font-size: 0.85rem;
		text-decoration: none;
		cursor: pointer;
	}
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.err { color: #f28b82; }
	a { color: #8ab4f8; }
</style>
