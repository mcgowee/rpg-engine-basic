<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import { SvelteSet } from 'svelte/reactivity';
	import { page } from '$app/state';
	import { toast as globalToast, toastError } from '$lib/toast.svelte';
	import Icon from '$lib/components/Icon.svelte';

	const SAVE_SLOT_COUNT = 5;

	type TranscriptEntry = {
		type: 'player' | 'narrator' | 'character' | 'scene-image';
		text: string;
		name?: string;
		action?: string;
		portrait?: string;
	};
	type SaveRow = { slot: number; timestamp: string; turns: number };

	let storyId = $state<number | null>(null);
	let bootError = $state<string | null>(null);
	let booting = $state(true);

	let transcript = $state<TranscriptEntry[]>([]);
	let gameTitle = $state('');
	let playerName = $state('');
	let subgraphName = $state('');
	type MoodAxis = { axis: string; low: string; high: string; value: number };
	type CharDisplay = { label: string; moods: MoodAxis[]; legacyMood?: number; portrait?: string };
	type StoryImage = { filename: string; image_id?: number | null; prompt?: string; created_at?: string };
	let characters = $state<CharDisplay[]>([]);
	let storyImages = $state<StoryImage[]>([]);
	let memorySummary = $state('');
	let turnCount = $state(0);
	let paused = $state(false);
	let saves = $state<SaveRow[]>([]);
	let message = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let logEl = $state<HTMLDivElement | undefined>(undefined);
	let sidebarOpen = $state(true);
	let generatingScene = $state(false);
	let brokenPortraitImages = new SvelteSet<string>();
	let brokenSceneImages = new SvelteSet<string>();
	let brokenStoryImages = new SvelteSet<string>();

	// Derived values
	let canSend = $derived(!loading && !paused && message.trim().length > 0);
	let hasCharacters = $derived(characters.length > 0);
	let recentStoryImages = $derived.by((): StoryImage[] => {
		if (storyImages.length === 0) return [];
		return [...storyImages].sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? ''))).slice(0, 4);
	});

	const slotIndices = Array.from({ length: SAVE_SLOT_COUNT }, (_, i) => i);

	function parseStoryId(raw: string | null): number | null {
		if (raw == null || raw === '') return null;
		const n = parseInt(raw, 10);
		return Number.isFinite(n) ? n : null;
	}

	async function scrollLog() {
		await tick();
		if (logEl) logEl.scrollTop = logEl.scrollHeight;
	}

	$effect(() => {
		void transcript.length;
		void scrollLog();
	});

	function toast(msg: string) {
		globalToast(msg, 'success');
	}

	async function fetchSaves(sid: number) {
		const r = await fetch(`/api/play/saves?story_id=${sid}`, { credentials: 'include' });
		if (!r.ok) return;
		const data = (await r.json().catch(() => ({}))) as { slots?: unknown[] };
		if (!Array.isArray(data.slots)) return;
		saves = data.slots.map((x) => {
			const o = x as Record<string, unknown>;
			return {
				slot: Number(o.slot),
				timestamp: String(o.timestamp ?? ''),
				turns: Number(o.turns ?? 0) || 0,
			};
		});
	}

	function applyStatus(data: Record<string, unknown>) {
		gameTitle = String(data.game_title ?? '');
		turnCount = Number(data.turn_count ?? 0) || 0;
		paused = Boolean(data.paused);
		memorySummary = String(data.memory_summary ?? '');
		if (data.player && typeof data.player === 'object') {
			playerName = String((data.player as Record<string, unknown>).name ?? '');
		}
		if (data.subgraph_name) {
			subgraphName = String(data.subgraph_name);
		}
		const chars = data.characters;
		if (chars && typeof chars === 'object' && !Array.isArray(chars)) {
			const charsObj = chars as Record<string, Record<string, unknown>>;
			const parsed: CharDisplay[] = [];
			for (const [k, v] of Object.entries(charsObj)) {
				if (!v || typeof v !== 'object') continue;
				const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
				const portrait = typeof v.portrait === 'string' ? v.portrait : '';
				const rawMoods = v.moods;
				if (Array.isArray(rawMoods) && rawMoods.length > 0) {
					parsed.push({
						label,
						portrait,
						moods: rawMoods.map((m: Record<string, unknown>) => ({
							axis: String(m.axis ?? 'mood'),
							low: String(m.low ?? 'low'),
							high: String(m.high ?? 'high'),
							value: Number(m.value ?? 5),
						})),
					});
				} else {
					parsed.push({ label, portrait, moods: [], legacyMood: Number(v.mood ?? 5) });
				}
			}
			characters = parsed;
		}
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

	async function boot() {
		bootError = null;
		booting = true;
		const id = parseStoryId(page.url.searchParams.get('story_id'));
		if (id == null) {
			bootError = 'Missing story_id. Open a story from the stories list.';
			storyId = null;
			booting = false;
			return;
		}
		storyId = id;

		try {
			try {
				const sr = await fetch(`/api/stories/${id}`, { credentials: 'include' });
				if (sr.ok) {
					const story = (await sr.json().catch(() => ({}))) as Record<string, unknown>;
					storyImages = normalizeStoryImages(story.story_images);
				}
			} catch {
				storyImages = [];
			}
			const st = await fetch(`/api/play/status?story_id=${id}`, { credentials: 'include' });
			if (st.status === 200) {
				const data = (await st.json()) as Record<string, unknown>;
				applyStatus(data);
				if (Array.isArray(data.save_slots)) {
					saves = (data.save_slots as Record<string, unknown>[]).map((o) => ({
						slot: Number(o.slot),
						timestamp: String(o.timestamp ?? ''),
						turns: Number(o.turns ?? 0) || 0,
					}));
				}
				// Rebuild transcript — opening first, then history
				const entries: TranscriptEntry[] = [];
				const opening = String(data.opening ?? data.empty_history_opening ?? '').trim();
				if (opening) {
					entries.push({ type: 'narrator', text: opening });
				}
				const hist = data.history;
				if (Array.isArray(hist) && hist.length > 0) {
					for (const h of hist) {
						const s = String(h);
						if (s.startsWith('[SCENE_IMAGE:') && s.endsWith(']')) {
							entries.push({ type: 'scene-image', text: s.slice(13, -1) });
						} else {
							const nl = s.indexOf('\n');
							if (nl > 0 && s.startsWith('Player: ')) {
								entries.push({ type: 'player', text: s.slice(8, nl).trim() });
								entries.push({ type: 'narrator', text: s.slice(nl + 1).trim() });
							} else {
								entries.push({ type: 'narrator', text: s });
							}
						}
					}
				}
				transcript = entries.length > 0 ? entries : [];
				await fetchSaves(id);
				booting = false;
				await scrollLog();
				return;
			}
			if (st.status === 404) {
				const start = await fetch('/api/play/start', {
					method: 'POST',
					credentials: 'include',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ story_id: id }),
				});
				const body = (await start.json().catch(() => ({}))) as Record<string, unknown>;
				if (!start.ok) {
					bootError = String(body.error ?? `Could not start game (${start.status})`);
					booting = false;
					return;
				}
				const opening = String(body.response ?? '').trim();
				if (body.state && typeof body.state === 'object') {
					applyStatus(body.state as Record<string, unknown>);
				}
				transcript = opening ? [{ type: 'narrator', text: opening }] : [];
				await fetchSaves(id);
				booting = false;
				await scrollLog();
				return;
			}
			if (st.status === 401) {
				bootError = 'You need to log in to play.';
				booting = false;
				return;
			}
			const j = (await st.json().catch(() => ({}))) as { error?: string };
			bootError = j.error ?? `Failed to load game (${st.status})`;
		} catch {
			bootError = 'Network error';
		}
		booting = false;
	}

	onMount(() => { void boot(); });

	async function send() {
		const sid = storyId;
		const text = message.trim();
		if (sid == null || !text || loading || paused) return;
		error = null;
		message = '';
		transcript = [...transcript, { type: 'player', text }];
		loading = true;
		try {
			const r = await fetch('/api/play/chat', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: sid, message: text }),
			});
			const data = (await r.json().catch(() => ({}))) as Record<string, unknown>;
			if (!r.ok) {
				error = String(data.error ?? `Chat failed (${r.status})`);
				const last = transcript[transcript.length - 1];
				if (last?.type === 'player' && last.text === text) {
					transcript = transcript.slice(0, -1);
				}
				message = text;
				return;
			}
			applyStatus(data);
			// Render bubbles if available, fallback to combined response
			const bubbles = data.bubbles as { type: string; text?: string; name?: string; action?: string; portrait?: string }[] | undefined;
			if (Array.isArray(bubbles) && bubbles.length > 0) {
				const newEntries: TranscriptEntry[] = [];
				for (const b of bubbles) {
					if (b.type === 'narrator' && b.text) {
						newEntries.push({ type: 'narrator', text: b.text });
					} else if (b.type === 'character') {
						newEntries.push({
							type: 'character',
							text: b.text ?? '',
							name: b.name,
							action: b.action,
							portrait: b.portrait,
						});
					}
				}
				if (newEntries.length > 0) {
					transcript = [...transcript, ...newEntries];
				}
			} else {
				const resp = String(data.response ?? '').trim();
				if (resp) {
					transcript = [...transcript, { type: 'narrator', text: resp }];
				}
			}
			await fetchSaves(sid);
		} catch {
			error = 'Network error';
			const last = transcript[transcript.length - 1];
			if (last?.type === 'player' && last.text === text) {
				transcript = transcript.slice(0, -1);
			}
			message = text;
		} finally {
			loading = false;
			await scrollLog();
		}
	}

	async function generateScene() {
		if (generatingScene || !storyId) return;
		// Find the last narrator text
		let lastNarration = '';
		for (let i = transcript.length - 1; i >= 0; i--) {
			if (transcript[i].type === 'narrator') {
				lastNarration = transcript[i].text;
				break;
			}
		}
		if (!lastNarration) return;

		generatingScene = true;
		try {
			const r = await fetch('/api/ai/generate-scene', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: storyId, scene_text: lastNarration }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.url) {
				transcript = [...transcript, { type: 'scene-image', text: `${j.url}?t=${Date.now()}` }];
				await scrollLog();
			} else {
				globalToast(j.error ?? 'Scene generation failed', 'error');
			}
		} catch {
			globalToast('Network error generating scene', 'error');
		} finally {
			generatingScene = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key !== 'Enter' || e.shiftKey) return;
		e.preventDefault();
		void send();
	}

	async function saveToSlot(slot: number) {
		const sid = storyId;
		if (sid == null) return;
		try {
			const r = await fetch('/api/play/save', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: sid, slot }),
			});
			const j = (await r.json().catch(() => ({}))) as { error?: string };
			if (!r.ok) { toast(j.error ?? 'Save failed'); return; }
			toast(`Saved to slot ${slot}`);
			await fetchSaves(sid);
		} catch { toast('Network error'); }
	}

	async function loadFromSlot(slot: number) {
		const sid = storyId;
		if (sid == null) return;
		try {
			const r = await fetch('/api/play/load', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: sid, slot }),
			});
			const j = (await r.json().catch(() => ({}))) as Record<string, unknown>;
			if (!r.ok) { toast(String(j.error ?? 'Load failed')); return; }
			toast(`Loaded slot ${slot}`);
			turnCount = Number(j.turn_count ?? 0);
			const resp = String(j.response ?? '').trim();
			transcript = resp ? [{ type: 'narrator', text: resp }] : [];
			await fetchSaves(sid);
		} catch { toast('Network error'); }
	}

	async function togglePause() {
		const sid = storyId;
		if (sid == null) return;
		const path = paused ? '/api/play/unpause' : '/api/play/pause';
		try {
			const r = await fetch(path, {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: sid }),
			});
			const j = (await r.json().catch(() => ({}))) as { paused?: boolean; error?: string };
			if (!r.ok) { toast(j.error ?? 'Failed'); return; }
			paused = Boolean(j.paused);
			toast(paused ? 'Paused' : 'Resumed');
		} catch { toast('Network error'); }
	}

	function formatTs(s: string) {
		if (!s) return '—';
		try { return new Date(s).toLocaleString(); } catch { return s; }
	}

	function portraitImageSrc(path: string): string {
		return `/images/portraits/${path}`;
	}

	function isPortraitBroken(path: string): boolean {
		return brokenPortraitImages.has(path);
	}

	function markPortraitBroken(path: string): void {
		if (brokenPortraitImages.has(path)) return;
		brokenPortraitImages.add(path);
	}

	function clearPortraitBroken(path: string): void {
		if (!brokenPortraitImages.has(path)) return;
		brokenPortraitImages.delete(path);
	}

	function isSceneBroken(path: string): boolean {
		return brokenSceneImages.has(path);
	}

	function markSceneBroken(path: string): void {
		if (brokenSceneImages.has(path)) return;
		brokenSceneImages.add(path);
	}

	function clearSceneBroken(path: string): void {
		if (!brokenSceneImages.has(path)) return;
		brokenSceneImages.delete(path);
	}

	function storyImageSrc(filename: string): string {
		return `/images/story/${filename}`;
	}

	function storyImageKey(img: StoryImage, idx: number): string {
		return `${idx}:${img.filename}:${img.created_at ?? ''}`;
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
	<title>Play — {gameTitle || 'Story'}</title>
</svelte:head>

{#if bootError}
	<section class="page narrow">
		<p class="err">{bootError}</p>
		<p><a href="/stories">← Back to stories</a></p>
	</section>
{:else if booting}
	<section class="page narrow"><p class="muted state-note">Loading game…</p></section>
{:else if storyId != null}
	<div class="layout">
		{#if hasCharacters}
			<aside class="portrait-sidebar">
				{#each characters as char (char.label)}
					<div class="portrait-card">
						{#if char.portrait && !isPortraitBroken(char.portrait)}
							<img
								src={portraitImageSrc(char.portrait)}
								alt={char.label}
								class="portrait-img"
								loading="lazy"
								decoding="async"
								onerror={() => markPortraitBroken(char.portrait ?? '')}
								onload={() => clearPortraitBroken(char.portrait ?? '')}
							/>
						{:else}
							<div class="portrait-placeholder">
								<Icon name="user" size={32} />
								<span>No portrait</span>
							</div>
						{/if}
						<span class="portrait-name">{char.label}</span>
					</div>
				{/each}
			</aside>
		{/if}
		<main class="main">
			<div class="transcript-wrap">
				<div class="transcript" bind:this={logEl}>
					{#each transcript as entry, i (i)}
						{#if entry.type === 'player'}
							<div class="row player-row">
								<div class="bubble player"><span class="prefix"><Icon name="user" size={12} /> You:</span>{entry.text}</div>
							</div>
						{:else if entry.type === 'character'}
							<div class="row character-row">
								<div class="bubble character">
									<span class="prefix"><Icon name="message-circle" size={12} /> {entry.name ?? 'Character'}:</span>
									{#if entry.action}<span class="char-action">*{entry.action}*</span>{/if}
									{entry.text}
								</div>
							</div>
						{:else if entry.type === 'scene-image'}
							<div class="row scene-row">
								{#if !isSceneBroken(entry.text)}
									<img
										src={entry.text}
										alt="Generated scene"
										class="scene-img"
										loading="lazy"
										decoding="async"
										onerror={() => markSceneBroken(entry.text)}
										onload={() => clearSceneBroken(entry.text)}
									/>
								{:else}
									<div class="scene-placeholder">
										<Icon name="image" size={20} />
										<span>Scene image unavailable</span>
									</div>
								{/if}
							</div>
						{:else}
							<div class="row narrator-row">
								<div class="bubble narrator"><span class="prefix"><Icon name="book" size={12} /> Narrator:</span>{entry.text}</div>
							</div>
						{/if}
					{/each}
				</div>
			</div>

			<div class="input-area">
				{#if paused}
					<p class="paused-note">Game is paused. Unpause in the sidebar to continue.</p>
				{/if}
				<div class="input-row">
					<textarea class="inp" rows="3" placeholder="What do you do? (Enter to send, Shift+Enter for new line)" aria-label="Player input"
						bind:value={message} disabled={loading || paused} onkeydown={onKeydown}
					></textarea>
					<button type="button" class="btn primary send"
						disabled={!canSend} onclick={() => send()}>
						{loading ? 'Thinking…' : 'Send'}
					</button>
				</div>
				<div class="input-actions">
					<button type="button" class="btn sm"
						disabled={generatingScene || transcript.length === 0}
						title="Generate an image of the current scene (requires ComfyUI)"
						onclick={() => generateScene()}>
						{#if generatingScene}<span class="spinner"></span> Generating...{:else}🎨 Scene{/if}
					</button>
					<button type="button" class="btn sm"
						title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
						onclick={() => sidebarOpen = !sidebarOpen}>
						{sidebarOpen ? '→ Hide panel' : '← Show panel'}
					</button>
				</div>
				{#if error}<p class="err inline-err" transition:fade={{ duration: 150 }}>{error}</p>{/if}
			</div>
		</main>

		{#if sidebarOpen}
		<aside class="sidebar" transition:fade={{ duration: 100 }}>

			<section class="side-block">
				<h2>Status</h2>
				<dl class="kv">
					<dt>Title</dt><dd>{gameTitle || '—'}</dd>
					{#if playerName}<dt>Player</dt><dd>{playerName}</dd>{/if}
					<dt>Turns</dt><dd>{turnCount}</dd>
					{#if subgraphName}<dt>Subgraph</dt><dd>{subgraphName}</dd>{/if}
				</dl>
			</section>

			{#if hasCharacters}
				<section class="side-block">
					<h2>Characters</h2>
					{#each characters as char (char.label)}
						<div class="char-block">
							<strong>{char.label}</strong>
							{#if char.moods.length > 0}
								<ul class="mood-list">
									{#each char.moods as axis (axis.axis)}
										<li>{axis.axis}: {axis.value}/10 <span class="mood-range">({axis.low} → {axis.high})</span></li>
									{/each}
								</ul>
							{:else if char.legacyMood !== undefined}
								<span class="mood-badge">mood: {char.legacyMood}/10</span>
							{/if}
						</div>
					{/each}
				</section>
			{/if}

			{#if recentStoryImages.length > 0}
				<section class="side-block">
					<h2>Story Gallery</h2>
					<div class="story-gallery-grid">
						{#each recentStoryImages as img, idx (storyImageKey(img, idx))}
							{@const key = storyImageKey(img, idx)}
							<div class="story-thumb">
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
									<div class="story-thumb-placeholder">
										<Icon name="image" size={16} />
										<span>Unavailable</span>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</section>
			{/if}

			<section class="side-block">
				<details>
					<summary>Memory (AI summary)</summary>
					<p class="memory-text">{memorySummary || 'No summary yet.'}</p>
				</details>
			</section>

			<section class="side-block">
				<details>
					<summary>Save / Load</summary>
					<ul class="slot-list">
						{#each slotIndices as slot}
							{@const row = saves.find((s) => s.slot === slot)}
							<li class="slot-row">
								<div class="slot-info">
									<strong>Slot {slot}</strong>
									{#if row}
										<span class="slot-meta">{row.turns} turns · {formatTs(row.timestamp)}</span>
									{:else}
										<span class="slot-meta muted">Empty</span>
									{/if}
								</div>
								<div class="slot-actions">
									<button type="button" class="btn sm" onclick={() => saveToSlot(slot)}><Icon name="save" size={12} /> Save</button>
									{#if row}
										<button type="button" class="btn sm" onclick={() => loadFromSlot(slot)}><Icon name="upload" size={12} /> Load</button>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
				</details>
			</section>

			<section class="side-block">
				<h2>Actions</h2>
				<button type="button" class="btn" onclick={() => togglePause()}>
					<Icon name={paused ? 'play' : 'pause'} size={14} /> {paused ? 'Unpause' : 'Pause'}
				</button>
				<p class="back"><a href="/stories">← Back to stories</a></p>
			</section>
		</aside>
		{/if}
	</div>
{/if}

<style>
	.page.narrow { padding: 1rem; max-width: 40rem; }
	.state-note { border: 1px dashed #3a414d; border-radius: 10px; padding: 0.75rem 0.85rem; background: #171b22; }
	.layout { display: flex; gap: 0.75rem; max-width: 1300px; margin: 0 auto; padding: 0 0.5rem 2rem; min-height: calc(100vh - 2rem); }
	.portrait-sidebar { width: 100px; flex-shrink: 0; display: flex; flex-direction: column; gap: 0.75rem; padding-top: 0.25rem; overflow-y: auto; max-height: calc(100vh - 2rem); }
	.portrait-card { text-align: center; }
	.portrait-img { width: 100%; height: 100%; object-fit: cover; border-radius: 8px; border: 1px solid #2a2f38; display: block; aspect-ratio: 2 / 3; }
	.portrait-placeholder {
		width: 100%;
		aspect-ratio: 2 / 3;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		background: linear-gradient(180deg, #1a1d23 0%, #161a20 100%);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
		color: #7f8896;
		font-size: 0.68rem;
	}
	.portrait-name { display: block; font-size: 0.72rem; color: #9aa0a6; margin-top: 0.25rem; line-height: 1.2; }
	.main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.75rem; }
	.transcript-wrap { flex: 1; min-height: 200px; border: 1px solid #2a2f38; border-radius: 10px; background: #1a1d23; overflow: hidden; box-shadow: inset 0 1px 0 rgba(255,255,255,0.02); }
	.transcript { height: min(60vh, 520px); overflow-y: auto; padding: 0.75rem; }
	.row { margin-bottom: 0.65rem; }
	.player-row { display: flex; justify-content: flex-end; }
	.narrator-row { display: flex; justify-content: flex-start; }
	.bubble { max-width: 92%; padding: 0.75rem; border-radius: 10px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; border: 1px solid #2a2f38; border-left: 3px solid; transition: border-color 0.18s ease, background-color 0.18s ease; }
	.prefix { display: block; font-weight: 700; font-size: 0.8rem; margin-bottom: 0.2rem; opacity: 0.7; }
	.bubble.player { background: #1a1d23; border-left-color: #1a73e8; }
	.bubble.narrator { background: #1a1d23; border-left-color: #81c995; }
	.bubble.character { background: #1a1d23; border-left-color: #c58af9; }
	.char-action { display: block; font-style: italic; color: #9aa0a6; font-size: 0.88rem; margin-bottom: 0.3rem; }
	:global([data-theme="light"]) .bubble.character { border-left-color: #9c27b0; }
	.scene-row { display: flex; justify-content: center; }
	.scene-img {
		width: min(100%, 760px);
		aspect-ratio: 16 / 9;
		object-fit: cover;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		display: block;
	}
	.scene-placeholder {
		width: min(100%, 760px);
		aspect-ratio: 16 / 9;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		background: linear-gradient(180deg, #1a1d23 0%, #161a20 100%);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.35rem;
		color: #7f8896;
		font-size: 0.8rem;
	}
	.input-actions { display: flex; gap: 0.35rem; margin-top: 0.4rem; }
	.input-area { border-top: 1px solid #2a2f38; padding-top: 0.75rem; }
	.paused-note { margin: 0 0 0.5rem; color: #f6b93b; font-weight: 600; border: 1px solid #624800; border-radius: 8px; padding: 0.4rem 0.55rem; background: #201a09; }
	.input-row { display: flex; gap: 0.5rem; align-items: flex-end; }
	.inp { flex: 1; min-width: 12rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; transition: border-color 0.18s ease, background-color 0.18s ease; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.send { align-self: stretch; }
	.sidebar { width: 280px; flex-shrink: 0; border: 1px solid #2a2f38; border-radius: 10px; padding: 0.65rem 0.75rem; background: #13151a; overflow-y: auto; max-height: calc(100vh - 2rem); }
	.side-block { margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid #2a2f38; }
	.side-block:last-child { border-bottom: none; }
	.side-block h2 { font-size: 0.95rem; margin: 0 0 0.5rem; }
	.kv { margin: 0; display: grid; grid-template-columns: 6rem 1fr; gap: 0.25rem 0.5rem; font-size: 0.88rem; }
	.kv dt { margin: 0; color: #9aa0a6; font-weight: 600; }
	.kv dd { margin: 0; }
	.char-block { margin-bottom: 0.65rem; }
	.char-block strong { font-size: 0.9rem; }
	.mood-list { list-style: none; margin: 0.2rem 0 0; padding: 0; font-size: 0.82rem; }
	.mood-list li { margin-bottom: 0.15rem; }
	.mood-range { color: #9aa0a6; font-size: 0.78rem; }
	.mood-badge { color: #c8d5e8; font-size: 0.78rem; border: 1px solid #2d3e56; border-radius: 999px; padding: 0.16rem 0.45rem; background: #132035; display: inline-block; }
	.memory-text { font-size: 0.85rem; line-height: 1.4; margin: 0.5rem 0 0; white-space: pre-wrap; color: #bdc1c6; }
	.story-gallery-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.35rem; }
	.story-thumb { border: 1px solid #2a2f38; border-radius: 6px; overflow: hidden; background: #161a20; aspect-ratio: 16 / 10; }
	.story-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.story-thumb-placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.2rem;
		font-size: 0.62rem;
		color: #7f8896;
		background: linear-gradient(180deg, #1a1d23 0%, #161a20 100%);
	}
	.slot-list { list-style: none; margin: 0.5rem 0 0; padding: 0; }
	.slot-row { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.65rem; padding-bottom: 0.5rem; border-bottom: 1px solid #1a1d23; }
	.slot-row:last-child { border-bottom: none; }
	.slot-meta { display: block; font-size: 0.78rem; color: #9aa0a6; margin-top: 0.15rem; }
	.slot-actions { display: flex; gap: 0.35rem; }
	.back { margin: 0.5rem 0 0; font-size: 0.9rem; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.inline-err { margin: 0.35rem 0 0; font-size: 0.9rem; }
	:global([data-theme="light"]) .state-note { border-color: #d7dde7; background: #f8fbff; }
	:global([data-theme="light"]) .paused-note { border-color: #f0d187; background: #fff9e6; color: #8a6200; }
	:global([data-theme="light"]) .mood-badge { color: #315b8f; border-color: #cfe0f5; background: #ecf4ff; }
	@media (max-width: 800px) { .layout { flex-direction: column; } .portrait-sidebar { display: none; } .sidebar { width: 100%; max-height: none; } .transcript { height: 45vh; } .input-row { flex-direction: column; align-items: stretch; } .send { width: 100%; } }
</style>
