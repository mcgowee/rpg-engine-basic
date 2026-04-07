<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';

	const SAVE_SLOT_COUNT = 5;

	type TranscriptEntry = { type: 'player' | 'narrator'; text: string };
	type SaveRow = { slot: number; timestamp: string; turns: number };

	let storyId = $state<number | null>(null);
	let bootError = $state<string | null>(null);
	let booting = $state(true);

	let transcript = $state<TranscriptEntry[]>([]);
	let gameTitle = $state('');
	let playerName = $state('');
	let subgraphName = $state('');
	let characterNames = $state<string[]>([]);
	let characterMoods = $state<Record<string, number>>({});
	let memorySummary = $state('');
	let turnCount = $state(0);
	let paused = $state(false);
	let saves = $state<SaveRow[]>([]);
	let message = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let actionOk = $state<string | null>(null);
	let logEl = $state<HTMLDivElement | undefined>(undefined);

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
		actionOk = msg;
		setTimeout(() => { actionOk = null; }, 2800);
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
			characterNames = Object.keys(charsObj).map(k => k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
			const moods: Record<string, number> = {};
			for (const [k, v] of Object.entries(charsObj)) {
				if (v && typeof v === 'object' && 'mood' in v) {
					moods[k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())] = Number(v.mood ?? 5);
				}
			}
			characterMoods = moods;
		}
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
				const resp = String(data.response ?? '').trim();
				const opening = String(data.empty_history_opening ?? '').trim();
				const text = resp || opening;
				transcript = text ? [{ type: 'narrator', text }] : [];
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
			const resp = String(data.response ?? '').trim();
			if (resp) {
				transcript = [...transcript, { type: 'narrator', text: resp }];
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
	<section class="page narrow"><p class="muted">Loading game…</p></section>
{:else if storyId != null}
	<div class="layout">
		<main class="main">
			<div class="transcript-wrap">
				<div class="transcript" bind:this={logEl}>
					{#each transcript as entry, i (i)}
						{#if entry.type === 'player'}
							<div class="row player-row">
								<div class="bubble player"><span class="prefix">You:</span>{entry.text}</div>
							</div>
						{:else}
							<div class="row narrator-row">
								<div class="bubble narrator"><span class="prefix">Narrator:</span>{entry.text}</div>
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
					<textarea class="inp" rows="3" placeholder="What do you do?"
						bind:value={message} disabled={loading || paused} onkeydown={onKeydown}
					></textarea>
					<button type="button" class="btn primary send"
						disabled={loading || paused || !message.trim()} onclick={() => send()}>
						{loading ? 'Thinking…' : 'Send'}
					</button>
				</div>
				{#if error}<p class="err inline-err">{error}</p>{/if}
			</div>
		</main>

		<aside class="sidebar">
			{#if actionOk}<p class="ok toast">{actionOk}</p>{/if}

			<section class="side-block">
				<h2>Status</h2>
				<dl class="kv">
					<dt>Title</dt><dd>{gameTitle || '—'}</dd>
					{#if playerName}<dt>Player</dt><dd>{playerName}</dd>{/if}
					<dt>Turns</dt><dd>{turnCount}</dd>
					{#if subgraphName}<dt>Subgraph</dt><dd>{subgraphName}</dd>{/if}
				</dl>
			</section>

			{#if Object.keys(characterMoods).length > 0}
				<section class="side-block">
					<h2>Characters</h2>
					<ul class="char-list">
						{#each Object.entries(characterMoods) as [name, mood] (name)}
							<li>{name} <span class="mood-badge">mood: {mood}/10</span></li>
						{/each}
					</ul>
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
									<button type="button" class="btn sm" onclick={() => saveToSlot(slot)}>Save</button>
									{#if row}
										<button type="button" class="btn sm" onclick={() => loadFromSlot(slot)}>Load</button>
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
					{paused ? 'Unpause' : 'Pause'}
				</button>
				<p class="back"><a href="/stories">← Back to stories</a></p>
			</section>
		</aside>
	</div>
{/if}

<style>
	.page.narrow { padding: 1rem; max-width: 40rem; }
	.layout { display: flex; gap: 1rem; max-width: 1200px; margin: 0 auto; padding: 0 0.5rem 2rem; min-height: calc(100vh - 2rem); }
	.main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.75rem; }
	.transcript-wrap { flex: 1; min-height: 200px; border: 1px solid #ccc; border-radius: 8px; background: #fafafa; overflow: hidden; }
	.transcript { height: min(60vh, 520px); overflow-y: auto; padding: 0.75rem; }
	.row { margin-bottom: 0.65rem; }
	.player-row { display: flex; justify-content: flex-end; }
	.narrator-row { display: flex; justify-content: flex-start; }
	.bubble { max-width: 92%; padding: 0.45rem 0.65rem; border-radius: 8px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
	.prefix { display: block; font-weight: 700; font-size: 0.8rem; margin-bottom: 0.2rem; opacity: 0.85; }
	.bubble.player { background: #d9e8ff; border: 1px solid #9bb8e8; }
	.bubble.narrator { background: #fff; border: 1px solid #ddd; }
	.input-area { border-top: 1px solid #ddd; padding-top: 0.75rem; }
	.paused-note { margin: 0 0 0.5rem; color: #a34d00; font-weight: 600; }
	.input-row { display: flex; gap: 0.5rem; align-items: flex-end; }
	.inp { flex: 1; min-width: 12rem; font: inherit; padding: 0.4rem 0.5rem; border: 1px solid #aaa; border-radius: 4px; resize: vertical; }
	.btn { padding: 0.4rem 0.75rem; cursor: pointer; border: 1px solid #999; background: #fff; border-radius: 4px; font: inherit; }
	.btn.primary { background: #1a1a8c; color: #fff; border-color: #1a1a8c; }
	.btn:disabled { opacity: 0.65; cursor: not-allowed; }
	.btn.sm { font-size: 0.85rem; padding: 0.2rem 0.5rem; }
	.send { align-self: stretch; }
	.sidebar { width: 280px; flex-shrink: 0; border: 1px solid #ccc; border-radius: 8px; padding: 0.65rem 0.75rem; background: #fff; overflow-y: auto; max-height: calc(100vh - 2rem); }
	.side-block { margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid #eee; }
	.side-block:last-child { border-bottom: none; }
	.side-block h2 { font-size: 0.95rem; margin: 0 0 0.5rem; }
	.kv { margin: 0; display: grid; grid-template-columns: 5rem 1fr; gap: 0.25rem 0.5rem; font-size: 0.88rem; }
	.kv dt { margin: 0; color: #555; font-weight: 600; }
	.kv dd { margin: 0; }
	.char-list { list-style: none; margin: 0; padding: 0; font-size: 0.88rem; }
	.char-list li { margin-bottom: 0.3rem; }
	.mood-badge { color: #666; font-size: 0.8rem; }
	.memory-text { font-size: 0.85rem; line-height: 1.4; margin: 0.5rem 0 0; white-space: pre-wrap; color: #444; }
	details summary { cursor: pointer; font-weight: 600; font-size: 0.95rem; }
	.slot-list { list-style: none; margin: 0.5rem 0 0; padding: 0; }
	.slot-row { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.65rem; padding-bottom: 0.5rem; border-bottom: 1px solid #f0f0f0; }
	.slot-row:last-child { border-bottom: none; }
	.slot-meta { display: block; font-size: 0.78rem; color: #444; margin-top: 0.15rem; }
	.slot-actions { display: flex; gap: 0.35rem; }
	.back { margin: 0.5rem 0 0; font-size: 0.9rem; }
	.muted { color: #666; }
	.err { color: #b00020; }
	.inline-err { margin: 0.35rem 0 0; font-size: 0.9rem; }
	.ok.toast { margin: 0 0 0.5rem; padding: 0.35rem 0.5rem; background: #e8f5e9; border-radius: 4px; font-size: 0.85rem; color: #1b5e20; }
	a { color: #0066cc; }
	@media (max-width: 800px) { .layout { flex-direction: column; } .sidebar { width: 100%; max-height: none; } .transcript { height: 45vh; } }
</style>
