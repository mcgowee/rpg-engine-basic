<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { page } from '$app/state';
	import { toast as globalToast } from '$lib/toast.svelte';
	import Icon from '$lib/components/Icon.svelte';

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
	let bookId = $state<number | null>(null);
	let bookTitle = $state('');
	let loading = $state(true);
	let generating = $state(false);
	let saving = $state(false);
	let editing = $state(false);
	let editProse = $state('');
	let error = $state('');

	// Saved books for this story
	let savedBooks = $state<{ id: number; title: string; updated_at: string }[]>([]);

	let sections = $derived(prose ? prose.split(/\n---\n|\n\n---\n\n/).map(s => s.trim()).filter(Boolean) : []);

	type CharPortrait = { key: string; label: string; portrait: string };
	let charPortraits = $derived.by((): CharPortrait[] => {
		const out: CharPortrait[] = [];
		for (const [key, val] of Object.entries(characters)) {
			if (!val || typeof val !== 'object') continue;
			const portrait = typeof val.portrait === 'string' ? val.portrait : '';
			if (portrait) {
				out.push({ key, label: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), portrait });
			}
		}
		return out;
	});

	onMount(async () => {
		if (!storyId) { error = 'Invalid story ID'; loading = false; return; }

		try {
			// Load story data and saved books in parallel
			const [storyR, booksR] = await Promise.all([
				fetch(`/api/stories/${storyId}/book-data`, { credentials: 'include' }),
				fetch('/api/books', { credentials: 'include' }),
			]);

			if (!storyR.ok) {
				error = storyR.status === 404 ? 'Story not found' : `Failed to load (${storyR.status})`;
				loading = false;
				return;
			}

			const data = await storyR.json();
			title = data.title ?? '';
			genre = data.genre ?? '';
			opening = data.opening ?? '';
			coverImage = data.cover_image ?? '';
			playerName = data.player_name ?? '';
			characters = data.characters ?? {};
			history = Array.isArray(data.history) ? data.history : [];
			bookTitle = title;

			if (booksR.ok) {
				const allBooks = await booksR.json();
				savedBooks = (Array.isArray(allBooks) ? allBooks : [])
					.filter((b: Record<string, unknown>) => b.story_id === storyId)
					.map((b: Record<string, unknown>) => ({
						id: Number(b.id),
						title: String(b.title ?? ''),
						updated_at: String(b.updated_at ?? ''),
					}));
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
				bookId = null; // New unsaved prose
			} else {
				error = j.error ?? 'Generation failed';
			}
		} catch {
			error = 'Network error';
		} finally {
			generating = false;
		}
	}

	async function save() {
		if (!prose.trim() || !storyId) return;
		saving = true;
		try {
			if (bookId) {
				const r = await fetch(`/api/books/${bookId}`, {
					method: 'PUT', credentials: 'include',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ title: bookTitle, prose }),
				});
				if (r.ok) globalToast('Book saved', 'success');
			} else {
				const r = await fetch('/api/books', {
					method: 'POST', credentials: 'include',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ story_id: storyId, title: bookTitle, prose }),
				});
				const j = await r.json().catch(() => ({}));
				if (r.ok && j.id) {
					bookId = j.id;
					savedBooks = [...savedBooks, { id: j.id, title: bookTitle, updated_at: new Date().toISOString() }];
					globalToast('Book saved', 'success');
				}
			}
		} catch {
			globalToast('Failed to save', 'error');
		} finally {
			saving = false;
		}
	}

	async function loadBook(id: number) {
		try {
			const r = await fetch(`/api/books/${id}`, { credentials: 'include' });
			if (r.ok) {
				const j = await r.json();
				prose = j.prose ?? '';
				bookId = j.id;
				bookTitle = j.title ?? title;
				coverImage = j.cover_image ?? coverImage;
			}
		} catch { /* ignore */ }
	}

	async function deleteBook(id: number) {
		if (!confirm('Delete this saved book?')) return;
		try {
			const r = await fetch(`/api/books/${id}`, { method: 'DELETE', credentials: 'include' });
			if (r.ok) {
				savedBooks = savedBooks.filter(b => b.id !== id);
				if (bookId === id) { bookId = null; prose = ''; }
				globalToast('Book deleted', 'success');
			}
		} catch { /* ignore */ }
	}

	function startEdit() {
		editProse = prose;
		editing = true;
	}

	function cancelEdit() {
		editing = false;
	}

	function applyEdit() {
		prose = editProse;
		editing = false;
	}

	function formatDate(s: string) {
		try { return new Date(s).toLocaleString(); } catch { return s; }
	}
</script>

<svelte:head>
	<title>{bookTitle || 'Story Book'} — RPG Engine</title>
</svelte:head>

<article class="book">
	{#if loading}
		<div class="book-center"><span class="spinner"></span> Loading story data…</div>
	{:else if error && !prose}
		<div class="book-center">
			<p class="err">{error}</p>
			<p><a href="/stories">← Back to stories</a></p>
		</div>
	{:else if !prose}
		{#if coverImage}
			<div class="book-cover"><img src="/images/covers/{coverImage}" alt="" /></div>
		{/if}
		<div class="book-header">
			<h1>{title}</h1>
			{#if genre}<p class="book-genre">{genre}</p>{/if}
			{#if history.length > 0}
				<p class="book-meta">{history.length} turn{history.length === 1 ? '' : 's'} played</p>
			{/if}
		</div>

		{#if savedBooks.length > 0}
			<div class="saved-books">
				<h2>Saved Books</h2>
				{#each savedBooks as sb (sb.id)}
					<div class="saved-row">
						<button type="button" class="saved-link" onclick={() => loadBook(sb.id)}>
							{sb.title}
						</button>
						<span class="saved-date">{formatDate(sb.updated_at)}</span>
						<button type="button" class="btn sm" onclick={() => deleteBook(sb.id)}>
							<Icon name="trash" size={12} />
						</button>
					</div>
				{/each}
			</div>
		{/if}

		<div class="book-generate">
			{#if history.length === 0}
				<p>No play history yet. Play the story first, then come back to create a book.</p>
				<a href="/play?story_id={storyId}" class="btn primary">Play Story</a>
			{:else}
				<p>Transform your play session into a polished short story. The AI will rewrite the game transcript into narrative prose.</p>
				<button type="button" class="btn primary generate-btn" disabled={generating} onclick={() => generate()}>
					{#if generating}<span class="spinner"></span> Writing your story…{:else}<Icon name="book" size={16} /> Create Story Book{/if}
				</button>
			{/if}
			{#if error}<p class="err">{error}</p>{/if}
		</div>
	{:else if editing}
		<!-- Edit mode -->
		<div class="book-header">
			<input type="text" class="title-input" bind:value={bookTitle} />
		</div>
		<div class="edit-area">
			<textarea class="edit-prose" bind:value={editProse} rows="30"></textarea>
			<p class="hint">Sections are separated by --- on its own line.</p>
			<div class="edit-actions">
				<button type="button" class="btn primary" onclick={applyEdit}>Apply Changes</button>
				<button type="button" class="btn" onclick={cancelEdit}>Cancel</button>
			</div>
		</div>
	{:else}
		<!-- Reading mode -->
		{#if coverImage}
			<div class="book-cover"><img src="/images/covers/{coverImage}" alt="" /></div>
		{/if}

		<div class="book-header" transition:fade={{ duration: 200 }}>
			<h1>{bookTitle}</h1>
			{#if genre}<p class="book-genre">{genre}</p>{/if}
		</div>

		{#if charPortraits.length > 0}
			<div class="book-characters">
				<p class="book-characters-label">Characters</p>
				<div class="book-characters-grid">
					{#each charPortraits as cp (cp.key)}
						<div class="book-char">
							<img src="/images/portraits/{cp.portrait}" alt={cp.label} />
							<span class="book-char-name">{cp.label}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div class="book-toolbar">
			<button type="button" class="btn sm" onclick={startEdit}><Icon name="edit" size={12} /> Edit</button>
			<button type="button" class="btn sm" disabled={saving} onclick={() => save()}>
				<Icon name="save" size={12} /> {saving ? 'Saving…' : bookId ? 'Update' : 'Save'}
			</button>
			<button type="button" class="btn sm" disabled={generating} onclick={() => generate()}>
				{generating ? 'Rewriting…' : 'Regenerate'}
			</button>
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
				<a href="/stories" class="btn">Back to Stories</a>
				<a href="/play?story_id={storyId}" class="btn">Continue Playing</a>
			</div>
		</div>
	{/if}
</article>

<style>
	.book { max-width: 700px; margin: 0 auto; padding: 0 1rem 3rem; }
	.book-center { text-align: center; padding: 3rem 1rem; color: #9aa0a6; }
	.book-cover { margin: 0 -1rem 2rem; border-radius: 12px; overflow: hidden; }
	.book-cover img { width: 100%; height: auto; display: block; }
	.book-header { text-align: center; margin-bottom: 1.5rem; }
	.book-header h1 { font-size: 2.2rem; margin: 0 0 0.5rem; line-height: 1.2; }
	.book-genre { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: #8ab4f8; margin: 0 0 0.5rem; }
	.book-meta { font-size: 0.88rem; color: #9aa0a6; margin: 0; }
	.saved-books { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; margin-bottom: 1.5rem; background: #1a1d23; }
	.saved-books h2 { font-size: 1rem; margin: 0 0 0.75rem; }
	.saved-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
	.saved-link { background: none; border: none; color: #8ab4f8; font: inherit; cursor: pointer; text-decoration: underline; }
	.saved-date { font-size: 0.78rem; color: #9aa0a6; flex: 1; }
	.book-generate { text-align: center; padding: 2rem; border: 1px solid #2a2f38; border-radius: 12px; background: #1a1d23; }
	.book-generate p { color: #bdc1c6; line-height: 1.6; margin: 0 0 1.5rem; max-width: 500px; margin-left: auto; margin-right: auto; }
	.generate-btn { font-size: 1rem; padding: 0.65rem 1.5rem; }
	.book-characters { text-align: center; margin-bottom: 2rem; }
	.book-characters-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; color: #9aa0a6; margin: 0 0 0.75rem; }
	.book-characters-grid { display: flex; justify-content: center; gap: 1.5rem; flex-wrap: wrap; }
	.book-char { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; }
	.book-char img { width: 80px; height: 120px; object-fit: cover; border-radius: 8px; border: 1px solid #2a2f38; }
	.book-char-name { font-size: 0.78rem; color: #bdc1c6; }
	.book-toolbar { display: flex; gap: 0.5rem; justify-content: center; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #2a2f38; }
	.book-prose { font-size: 1.05rem; line-height: 1.75; color: #e8eaed; }
	.book-section p { margin: 0 0 1rem; text-indent: 1.5rem; }
	.book-section p:first-child { text-indent: 0; }
	.book-section p:first-child::first-letter { font-size: 2.5rem; float: left; line-height: 1; margin-right: 0.5rem; margin-top: 0.1rem; color: #8ab4f8; font-weight: 700; }
	.section-divider { border: none; text-align: center; margin: 2rem 0; color: #5f6368; }
	.section-divider::after { content: '⁂'; font-size: 1.2rem; }
	.book-footer { text-align: center; margin-top: 3rem; padding-top: 2rem; border-top: 1px solid #2a2f38; }
	.book-end { font-size: 1.1rem; font-style: italic; color: #9aa0a6; margin: 0 0 1.5rem; }
	.book-actions { display: flex; justify-content: center; gap: 0.75rem; flex-wrap: wrap; }
	.title-input { width: 100%; font-size: 1.5rem; font-weight: 700; text-align: center; background: none; border: 1px solid #3c4043; border-radius: 8px; padding: 0.5rem; color: #e8eaed; }
	.edit-area { margin-top: 1rem; }
	.edit-prose { width: 100%; font: inherit; font-size: 0.95rem; line-height: 1.6; padding: 1rem; border-radius: 8px; min-height: 50vh; }
	.hint { font-size: 0.82rem; color: #9aa0a6; margin: 0.5rem 0; }
	.edit-actions { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; text-decoration: none; cursor: pointer; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.err { color: #f28b82; }
	a { color: #8ab4f8; }
</style>
