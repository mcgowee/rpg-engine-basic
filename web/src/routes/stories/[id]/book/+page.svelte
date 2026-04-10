<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { SvelteSet } from 'svelte/reactivity';
	import { page } from '$app/state';
	import { toast as globalToast } from '$lib/toast.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { coverImagePosition } from '$lib/coverDisplay';

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
	type StoryImage = { filename: string; image_id?: number | null; prompt?: string; created_at?: string };
	let storyImages = $state<StoryImage[]>([]);
	let playerName = $state('');
	let tone = $state('');
	let characters = $state<Record<string, Record<string, unknown>>>({});
	let history = $state<unknown[]>([]);

	// Book state
	let prose = $state('');
	type SceneMeta = { turn: number; scene_image?: string; active_portraits?: Record<string, string>; portraits?: Record<string, string> };
	let sceneMeta = $state<SceneMeta[]>([]);
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

	// Extract scene images from history
	let sceneImages = $derived.by((): string[] => {
		const imgs: string[] = [];
		for (const h of history) {
			const s = String(h);
			if (s.startsWith('[SCENE_IMAGE:') && s.endsWith(']')) {
				imgs.push(s.slice(13, -1));
			}
		}
		return imgs;
	});

	let coverLoadFailed = $state(false);
	let genreCoverLoadFailed = $state(false);
	let brokenPortraits = new SvelteSet<string>();
	let brokenScenes = new SvelteSet<string>();
	let brokenStoryImages = new SvelteSet<string>();

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

	let topStoryImages = $derived.by((): StoryImage[] => {
		if (storyImages.length === 0) return [];
		return [...storyImages].sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? ''))).slice(0, 6);
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
			tone = data.tone ?? '';
			opening = data.opening ?? '';
			coverImage = data.cover_image ?? '';
			storyImages = normalizeStoryImages(data.story_images);
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
				body: JSON.stringify({ history, opening, title, player_name: playerName, characters, genre, tone }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.prose) {
				prose = j.prose;
				sceneMeta = Array.isArray(j.scenes) ? j.scenes : [];
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

	function normalizedGenre(value: string): string {
		return value.trim().toLowerCase();
	}

	function genreFallbackCoverSrc(): string {
		const g = normalizedGenre(genre);
		return g ? `/images/genre-${g}.png` : '';
	}

	function storyCoverSrc(): string {
		return `/images/covers/${coverImage}`;
	}

	function storyImageSrc(filename: string): string {
		return `/images/story/${filename}`;
	}

	function storyImageKey(img: StoryImage, idx: number): string {
		return `${idx}:${img.filename}:${img.created_at ?? ''}`;
	}

	function portraitSrc(path: string): string {
		return `/images/portraits/${path}`;
	}

	function isPortraitBroken(path: string): boolean {
		return brokenPortraits.has(path);
	}

	function markPortraitBroken(path: string): void {
		if (brokenPortraits.has(path)) return;
		brokenPortraits.add(path);
	}

	function clearPortraitBroken(path: string): void {
		if (!brokenPortraits.has(path)) return;
		brokenPortraits.delete(path);
	}

	function isSceneBroken(path: string): boolean {
		return brokenScenes.has(path);
	}

	function markSceneBroken(path: string): void {
		if (brokenScenes.has(path)) return;
		brokenScenes.add(path);
	}

	function clearSceneBroken(path: string): void {
		if (!brokenScenes.has(path)) return;
		brokenScenes.delete(path);
	}

	function normalizeStoryImages(value: unknown): StoryImage[] {
		if (!Array.isArray(value)) return [];
		const out: StoryImage[] = [];
		for (const item of value) {
			if (!item || typeof item !== 'object') continue;
			const raw = item as Record<string, unknown>;
			const filename = String(raw.filename ?? '').trim();
			if (!filename) continue;
			const imageId = raw.image_id == null ? null : Number(raw.image_id);
			out.push({
				filename,
				image_id: Number.isFinite(imageId) ? imageId : null,
				prompt: String(raw.prompt ?? ''),
				created_at: String(raw.created_at ?? ''),
			});
		}
		return out;
	}

	function isStoryImageBroken(key: string): boolean {
		return brokenStoryImages.has(key);
	}

	function markStoryImageBroken(key: string): void {
		if (brokenStoryImages.has(key)) return;
		brokenStoryImages.add(key);
	}

	function clearStoryImageBroken(key: string): void {
		if (!brokenStoryImages.has(key)) return;
		brokenStoryImages.delete(key);
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
			<div class="book-cover">
				{#if !coverLoadFailed}
					<img
						src={storyCoverSrc()}
						alt=""
						loading="lazy"
						decoding="async"
						style:object-position={coverImagePosition(coverImage)}
						onerror={() => coverLoadFailed = true}
					/>
				{:else if genreFallbackCoverSrc() && !genreCoverLoadFailed}
					<img src={genreFallbackCoverSrc()} alt="" loading="lazy" decoding="async" class="fallback-cover" onerror={() => genreCoverLoadFailed = true} />
				{:else}
					<div class="image-placeholder cover-placeholder">
						<Icon name="image" size={24} />
						<span>Cover unavailable</span>
					</div>
				{/if}
			</div>
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
			<div class="book-cover">
				{#if !coverLoadFailed}
					<img
						src={storyCoverSrc()}
						alt=""
						loading="lazy"
						decoding="async"
						style:object-position={coverImagePosition(coverImage)}
						onerror={() => coverLoadFailed = true}
					/>
				{:else if genreFallbackCoverSrc() && !genreCoverLoadFailed}
					<img src={genreFallbackCoverSrc()} alt="" loading="lazy" decoding="async" class="fallback-cover" onerror={() => genreCoverLoadFailed = true} />
				{:else}
					<div class="image-placeholder cover-placeholder">
						<Icon name="image" size={24} />
						<span>Cover unavailable</span>
					</div>
				{/if}
			</div>
		{/if}

		<div class="book-header" transition:fade={{ duration: 200 }}>
			<h1>{bookTitle}</h1>
			{#if genre}<p class="book-genre">{genre}</p>{/if}
		</div>

		{#if topStoryImages.length > 0}
			<div class="book-story-gallery">
				<p class="book-story-gallery-label">Story Gallery</p>
				<div class="book-story-gallery-grid">
					{#each topStoryImages as img, idx (storyImageKey(img, idx))}
						{@const key = storyImageKey(img, idx)}
						<div class="book-story-thumb">
							{#if !isStoryImageBroken(key)}
								<img
									src={storyImageSrc(img.filename)}
									alt="Story gallery image {idx + 1}"
									loading="lazy"
									decoding="async"
									onerror={() => markStoryImageBroken(key)}
									onload={() => clearStoryImageBroken(key)}
								/>
							{:else}
								<div class="image-placeholder story-image-placeholder">
									<Icon name="image" size={16} />
									<span>Image unavailable</span>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if charPortraits.length > 0}
			<div class="book-characters">
				<p class="book-characters-label">Characters</p>
				<div class="book-characters-grid">
					{#each charPortraits as cp (cp.key)}
						<div class="book-char">
							{#if !isPortraitBroken(cp.portrait)}
								<img
									src={portraitSrc(cp.portrait)}
									alt={cp.label}
									loading="lazy"
									decoding="async"
									onerror={() => markPortraitBroken(cp.portrait)}
									onload={() => clearPortraitBroken(cp.portrait)}
								/>
							{:else}
								<div class="image-placeholder portrait-placeholder">
									<Icon name="user" size={18} />
									<span>No portrait</span>
								</div>
							{/if}
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
				{@const meta = sceneMeta[i]}
				<div class="book-scene-block">
					{#if meta?.scene_image}
						<div class="book-scene-img">
							<img
								src={meta.scene_image.startsWith('/') ? meta.scene_image : `/images/scenes/${meta.scene_image}`}
								alt="Scene {i + 1}"
								loading="lazy"
								decoding="async"
							/>
						</div>
					{/if}

					<div class="book-section">
						{#if meta?.portraits || meta?.active_portraits}
							<div class="book-scene-portraits">
								{#each Object.entries(meta.active_portraits ?? meta.portraits ?? {}) as [name, portrait]}
									<div class="book-scene-char">
										<img
											src={`/images/portraits/${portrait}`}
											alt={name}
											loading="lazy"
											decoding="async"
											class="book-char-portrait"
										/>
										<span class="book-char-label">{name}</span>
									</div>
								{/each}
							</div>
						{/if}

						{#each section.split('\n') as para}
							{#if para.trim()}
								<p>{para.trim()}</p>
							{/if}
						{/each}
					</div>
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
	.book-cover { margin: 0 -1rem 2rem; border-radius: 12px; overflow: hidden; border: 1px solid #2a2f38; background: #161a20; aspect-ratio: 16 / 6.5; }
	.book-cover img { width: 100%; height: 100%; object-fit: cover; object-position: center; display: block; }
	.book-cover img.fallback-cover { opacity: 0.95; }
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
	.book-story-gallery { margin: 0 auto 1.25rem; max-width: 660px; }
	.book-story-gallery-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; color: #9aa0a6; margin: 0 0 0.55rem; text-align: center; }
	.book-story-gallery-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.45rem; }
	.book-story-thumb { border: 1px solid #2a2f38; border-radius: 8px; overflow: hidden; background: #161a20; aspect-ratio: 16 / 10; }
	.book-story-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.story-image-placeholder { font-size: 0.68rem; }
	.book-characters-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; color: #9aa0a6; margin: 0 0 0.75rem; }
	.book-characters-grid { display: flex; justify-content: center; gap: 1.5rem; flex-wrap: wrap; }
	.book-char { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; }
	.book-char img { width: 80px; aspect-ratio: 2 / 3; height: auto; object-fit: cover; border-radius: 8px; border: 1px solid #2a2f38; display: block; }
	.book-char-name { font-size: 0.78rem; color: #bdc1c6; }
	.book-scene-block { margin-bottom: 0.5rem; }
	.book-scene-img { margin: 1.5rem -1rem 1rem; }
	.book-scene-img img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; height: auto; border-radius: 8px; display: block; border: 1px solid #2a2f38; }
	.book-scene-portraits { display: flex; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
	.book-scene-char { display: flex; align-items: center; gap: 0.4rem; }
	.book-char-portrait { width: 36px; height: 54px; object-fit: cover; border-radius: 4px; border: 1px solid #2a2f38; }
	.book-char-label { font-size: 0.75rem; color: #9aa0a6; font-style: italic; }
	.image-placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.35rem;
		color: #7f8896;
		background: linear-gradient(180deg, #1b2028 0%, #171b22 100%);
	}
	.cover-placeholder { font-size: 0.86rem; }
	.portrait-placeholder {
		width: 80px;
		aspect-ratio: 2 / 3;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		font-size: 0.7rem;
	}
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
	:global([data-theme="light"]) .saved-books,
	:global([data-theme="light"]) .book-generate { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .book-toolbar,
	:global([data-theme="light"]) .book-footer { border-color: #dfe3e8; }
	:global([data-theme="light"]) .book-prose { color: #1f2937; }
	:global([data-theme="light"]) .book-char-name { color: #334155; }
	:global([data-theme="light"]) .title-input { color: #1f2937; border-color: #d1d5db; }
	:global([data-theme="light"]) .btn { background: #f8fafc; border-color: #d1d5db; color: #1f2937; }
	:global([data-theme="light"]) .btn:hover { border-color: #9ca3af; }
</style>
