<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import Icon from '$lib/components/Icon.svelte';
	import { toast } from '$lib/toast.svelte';

	type StoryOption = { id: number; title: string; subgraph_name: string };
	type TurnResult = {
		turn: number;
		message: string;
		response: string;
		moods: Record<string, Record<string, number>>;
		memory_summary: string;
		time_seconds: number;
		response_length: number;
	};

	// Setup
	let stories = $state<StoryOption[]>([]);
	let selectedStoryId = $state<number | null>(null);
	let loadingStories = $state(true);

	// Playback config
	let turnMessages = $state<string[]>([
		"I look around carefully.",
		"I approach the nearest person.",
		"I ask them what's going on here.",
		"I examine something that catches my eye.",
		"I try something bold.",
		"I investigate further.",
		"I press for more details.",
		"I consider my options and act decisively.",
		"I explore a new direction.",
		"I make my final move.",
	]);
	let maxTurns = $state(5);
	let delayBetweenTurns = $state(2);

	// Playback state
	type PlayState = 'idle' | 'starting' | 'playing' | 'paused' | 'done';
	let playState = $state<PlayState>('idle');
	let turns = $state<TurnResult[]>([]);
	let currentTurn = $state(0);
	let openingText = $state('');
	let gameTitle = $state('');
	let subgraphName = $state('');
	let totalTime = $state(0);
	let error = $state('');
	let cookies = $state('');
	let abortController = $state<AbortController | null>(null);

	// Stats
	let avgTime = $derived(turns.length > 0 ? turns.reduce((a, t) => a + t.time_seconds, 0) / turns.length : 0);
	let avgLength = $derived(turns.length > 0 ? Math.round(turns.reduce((a, t) => a + t.response_length, 0) / turns.length) : 0);

	// Scroll
	let logEl = $state<HTMLDivElement | undefined>(undefined);

	onMount(async () => {
		// Load stories
		try {
			const [ownR, pubR] = await Promise.all([
				fetch('/api/stories', { credentials: 'include' }),
				fetch('/api/stories/public', { credentials: 'include' }),
			]);
			const ownJ = await ownR.json().catch(() => []);
			const pubJ = await pubR.json().catch(() => ({}));
			const ownList = Array.isArray(ownJ) ? ownJ : [];
			const pubList = Array.isArray(pubJ) ? pubJ : (pubJ.stories ?? []);

			const seen = new Set<number>();
			const all: StoryOption[] = [];
			for (const s of [...ownList, ...pubList]) {
				const id = Number(s.id);
				if (!Number.isFinite(id) || seen.has(id)) continue;
				seen.add(id);
				all.push({ id, title: String(s.title ?? ''), subgraph_name: String(s.subgraph_name ?? '') });
			}
			stories = all;
		} catch { /* ignore */ }
		loadingStories = false;
	});

	async function scrollToBottom() {
		await new Promise(r => setTimeout(r, 50));
		if (logEl) logEl.scrollTop = logEl.scrollHeight;
	}

	async function apiCall(method: string, path: string, body?: unknown): Promise<Record<string, unknown>> {
		const opts: RequestInit = {
			method,
			credentials: 'include',
			headers: { 'Content-Type': 'application/json' },
		};
		if (body) opts.body = JSON.stringify(body);
		const r = await fetch(`/api${path}`, opts);
		return await r.json().catch(() => ({}));
	}

	async function startPlayback() {
		if (!selectedStoryId) return;
		playState = 'starting';
		error = '';
		turns = [];
		currentTurn = 0;
		totalTime = 0;

		// Start a new game
		const startData = await apiCall('POST', '/play/start', { story_id: selectedStoryId });
		if (startData.error) {
			error = String(startData.error);
			playState = 'idle';
			return;
		}

		openingText = String(startData.response ?? '');
		const state = startData.state as Record<string, unknown> | undefined;
		if (state) {
			gameTitle = String(state.game_title ?? '');
			subgraphName = String(state.subgraph_name ?? '');
		}

		playState = 'playing';
		await scrollToBottom();
		await runTurns();
	}

	async function runTurns() {
		const startTime = performance.now();

		for (let i = 0; i < maxTurns; i++) {
			if (playState !== 'playing') break;

			const msg = turnMessages[i % turnMessages.length];
			currentTurn = i + 1;

			// Wait between turns
			if (i > 0 && delayBetweenTurns > 0) {
				await new Promise(r => setTimeout(r, delayBetweenTurns * 1000));
			}
			if (playState !== 'playing') break;

			const turnStart = performance.now();
			const data = await apiCall('POST', '/play/chat', { story_id: selectedStoryId, message: msg });
			const turnTime = (performance.now() - turnStart) / 1000;

			if (data.error) {
				error = String(data.error);
				break;
			}

			const moods: Record<string, Record<string, number>> = {};
			const chars = data.characters;
			if (chars && typeof chars === 'object') {
				for (const [k, v] of Object.entries(chars as Record<string, Record<string, unknown>>)) {
					if (!v) continue;
					const rawMoods = v.moods;
					if (Array.isArray(rawMoods)) {
						moods[k] = {};
						for (const m of rawMoods) {
							if (m && typeof m === 'object' && 'axis' in m) {
								moods[k][(m as Record<string, unknown>).axis as string] = Number((m as Record<string, unknown>).value ?? 0);
							}
						}
					} else if (typeof v.mood === 'number') {
						moods[k] = { mood: v.mood as number };
					}
				}
			}

			const turn: TurnResult = {
				turn: i + 1,
				message: msg,
				response: String(data.response ?? ''),
				moods,
				memory_summary: String(data.memory_summary ?? ''),
				time_seconds: Math.round(turnTime * 100) / 100,
				response_length: String(data.response ?? '').length,
			};
			turns = [...turns, turn];
			await scrollToBottom();
		}

		totalTime = Math.round((performance.now() - startTime) / 100) / 10;
		if (playState === 'playing') playState = 'done';
	}

	function pause() { playState = 'paused'; }
	function resume() { playState = 'playing'; runTurns(); }
	function stop() { playState = 'done'; }

	function moodColor(v: number): string {
		if (v <= 3) return '#f28b82';
		if (v <= 5) return '#f6b93b';
		if (v <= 7) return '#8ab4f8';
		return '#81c995';
	}

	function editMessage(idx: number, val: string) {
		turnMessages[idx] = val;
		turnMessages = [...turnMessages];
	}

	function addMessage() {
		turnMessages = [...turnMessages, 'I do something.'];
		maxTurns = Math.max(maxTurns, turnMessages.length);
	}
</script>

<svelte:head>
	<title>Playback — RPG Engine</title>
</svelte:head>

<section class="playback">
	<h1><Icon name="play" size={24} /> Playback Viewer</h1>
	<p class="lede">Watch a story play automatically and see how the engine performs.</p>

	{#if playState === 'idle'}
		<div class="setup">
			<div class="setup-row">
				<label class="field">
					<strong>Story</strong>
					{#if loadingStories}
						<span class="muted">Loading...</span>
					{:else}
						<select bind:value={selectedStoryId}>
							<option value={null}>— select a story —</option>
							{#each stories as s (s.id)}
								<option value={s.id}>{s.title} ({s.subgraph_name})</option>
							{/each}
						</select>
					{/if}
				</label>

				<label class="field">
					<strong>Turns</strong>
					<input type="number" min="1" max="20" bind:value={maxTurns} />
				</label>

				<label class="field">
					<strong>Delay (seconds)</strong>
					<input type="number" min="0" max="10" step="0.5" bind:value={delayBetweenTurns} />
				</label>
			</div>

			<div class="messages-setup">
				<strong>Messages (one per turn)</strong>
				<span class="hint">These are sent automatically as the player. Edit them to test specific scenarios.</span>
				{#each turnMessages as msg, i (i)}
					<div class="msg-row">
						<span class="msg-num">{i + 1}</span>
						<input type="text" value={msg} onchange={(e) => editMessage(i, (e.target as HTMLInputElement).value)} />
					</div>
				{/each}
				<button type="button" class="btn sm" onclick={addMessage}>+ Add message</button>
			</div>

			<button type="button" class="btn primary start-btn"
				disabled={!selectedStoryId}
				onclick={startPlayback}>
				<Icon name="play" size={16} /> Start Playback
			</button>
			{#if error}<p class="err">{error}</p>{/if}
		</div>
	{:else}
		<!-- Playback view -->
		<div class="playback-layout">
			<div class="playback-main">
				<!-- Controls -->
				<div class="controls">
					<div class="controls-left">
						<span class="game-info">{gameTitle} · {subgraphName}</span>
					</div>
					<div class="controls-right">
						{#if playState === 'playing'}
							<button type="button" class="btn sm" onclick={pause}><Icon name="pause" size={12} /> Pause</button>
							<button type="button" class="btn sm" onclick={stop}>Stop</button>
						{:else if playState === 'paused'}
							<button type="button" class="btn sm primary" onclick={resume}><Icon name="play" size={12} /> Resume</button>
							<button type="button" class="btn sm" onclick={stop}>Stop</button>
						{:else if playState === 'starting'}
							<span class="muted"><span class="spinner"></span> Starting...</span>
						{/if}
						<span class="turn-counter">Turn {currentTurn}/{maxTurns}</span>
					</div>
				</div>

				<!-- Transcript -->
				<div class="transcript-wrap">
					<div class="transcript" bind:this={logEl}>
						{#if openingText}
							<div class="entry opening" transition:fade={{ duration: 200 }}>
								<div class="entry-label">Opening</div>
								<div class="entry-text">{openingText}</div>
							</div>
						{/if}

						{#each turns as turn (turn.turn)}
							<div class="entry player" transition:fade={{ duration: 200 }}>
								<div class="entry-label">Player · Turn {turn.turn}</div>
								<div class="entry-text">{turn.message}</div>
							</div>
							<div class="entry narrator" transition:fade={{ duration: 200 }}>
								<div class="entry-label">Response · {turn.time_seconds}s · {turn.response_length} chars</div>
								<div class="entry-text">{turn.response}</div>
								{#if Object.keys(turn.moods).length > 0}
									<div class="entry-moods">
										{#each Object.entries(turn.moods) as [char, axes] (char)}
											<span class="mood-chip">
												{char.replace(/_/g, ' ')}:
												{#each Object.entries(axes) as [axis, val] (axis)}
													<span class="mood-val" style="color:{moodColor(val)}">{axis} {val}</span>
												{/each}
											</span>
										{/each}
									</div>
								{/if}
							</div>
						{/each}

						{#if playState === 'playing'}
							<div class="entry loading">
								<span class="spinner"></span> Generating turn {currentTurn}...
							</div>
						{/if}
					</div>
				</div>
			</div>

			<!-- Stats sidebar -->
			<aside class="playback-sidebar">
				<h3>Stats</h3>
				<dl class="kv">
					<dt>Turns</dt><dd>{turns.length}/{maxTurns}</dd>
					<dt>Total time</dt><dd>{totalTime}s</dd>
					<dt>Avg turn</dt><dd>{avgTime.toFixed(1)}s</dd>
					<dt>Avg length</dt><dd>{avgLength} chars</dd>
				</dl>

				{#if turns.length > 0}
					<h3>Turn Times</h3>
					<div class="time-bars">
						{#each turns as turn (turn.turn)}
							{@const maxT = Math.max(...turns.map(t => t.time_seconds), 1)}
							<div class="time-row">
								<span class="time-label">T{turn.turn}</span>
								<div class="time-bar-bg">
									<div class="time-bar-fill" style="width:{(turn.time_seconds / maxT) * 100}%"></div>
								</div>
								<span class="time-val">{turn.time_seconds}s</span>
							</div>
						{/each}
					</div>
				{/if}

				{#if turns.length > 0 && turns[turns.length - 1].memory_summary}
					<h3>Memory</h3>
					<p class="memory-text">{turns[turns.length - 1].memory_summary}</p>
				{/if}

				{#if playState === 'done'}
					<div class="done-actions">
						<button type="button" class="btn primary" onclick={() => { playState = 'idle'; turns = []; }}>
							New Test
						</button>
					</div>
				{/if}
			</aside>
		</div>
	{/if}
</section>

<style>
	.playback { max-width: 1200px; margin: 0 auto; padding: 0 1rem 2rem; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }

	/* Setup */
	.setup { max-width: 700px; }
	.setup-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
	.setup-row .field { flex: 1; min-width: 150px; }
	.field { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.75rem; }
	.field strong { font-size: 0.9rem; }
	.messages-setup { margin: 1rem 0; }
	.messages-setup strong { display: block; margin-bottom: 0.25rem; }
	.hint { font-size: 0.82rem; color: #9aa0a6; display: block; margin-bottom: 0.5rem; }
	.msg-row { display: flex; gap: 0.35rem; align-items: center; margin-bottom: 0.3rem; }
	.msg-num { font-size: 0.75rem; color: #5f6368; min-width: 1.5rem; text-align: center; }
	.msg-row input { flex: 1; font-size: 0.88rem; }
	.start-btn { font-size: 1rem; padding: 0.6rem 1.5rem; margin-top: 1rem; }

	/* Playback layout */
	.playback-layout { display: flex; gap: 1rem; }
	.playback-main { flex: 1; min-width: 0; }
	.playback-sidebar { width: 250px; flex-shrink: 0; background: #13151a; border: 1px solid #2a2f38; border-radius: 10px; padding: 0.75rem; overflow-y: auto; max-height: calc(100vh - 8rem); }
	.playback-sidebar h3 { font-size: 0.9rem; margin: 0.75rem 0 0.35rem; }
	.playback-sidebar h3:first-child { margin-top: 0; }

	/* Controls */
	.controls { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; margin-bottom: 0.5rem; border-bottom: 1px solid #2a2f38; }
	.controls-left { font-size: 0.85rem; color: #9aa0a6; }
	.controls-right { display: flex; gap: 0.5rem; align-items: center; }
	.game-info { font-weight: 500; }
	.turn-counter { font-size: 0.82rem; color: #8ab4f8; font-weight: 600; }

	/* Transcript */
	.transcript-wrap { border: 1px solid #2a2f38; border-radius: 10px; overflow: hidden; background: #1a1d23; }
	.transcript { height: 60vh; overflow-y: auto; padding: 0.75rem; }
	.entry { margin-bottom: 0.75rem; padding: 0.6rem 0.75rem; border-radius: 8px; border-left: 3px solid; }
	.entry.opening { border-left-color: #5f6368; background: #13151a; }
	.entry.player { border-left-color: #1a73e8; background: #111827; }
	.entry.narrator { border-left-color: #81c995; background: #13151a; }
	.entry.loading { border-left-color: #f6b93b; background: #1a1a10; color: #9aa0a6; }
	.entry-label { font-size: 0.72rem; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; }
	.entry-text { font-size: 0.92rem; line-height: 1.6; white-space: pre-wrap; }
	.entry-moods { margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.mood-chip { font-size: 0.78rem; color: #9aa0a6; }
	.mood-val { margin-left: 0.2rem; font-weight: 600; }

	/* Stats */
	.kv { margin: 0; display: grid; grid-template-columns: 5rem 1fr; gap: 0.2rem 0.5rem; font-size: 0.85rem; }
	.kv dt { color: #9aa0a6; }
	.kv dd { margin: 0; }
	.time-bars { margin-top: 0.35rem; }
	.time-row { display: flex; align-items: center; gap: 0.35rem; margin-bottom: 0.25rem; }
	.time-label { font-size: 0.72rem; color: #9aa0a6; min-width: 1.5rem; }
	.time-bar-bg { flex: 1; height: 10px; background: #2a2f38; border-radius: 3px; overflow: hidden; }
	.time-bar-fill { height: 100%; background: #1a73e8; border-radius: 3px; }
	.time-val { font-size: 0.72rem; color: #9aa0a6; min-width: 2.5rem; text-align: right; }
	.memory-text { font-size: 0.8rem; color: #bdc1c6; line-height: 1.4; font-style: italic; }
	.done-actions { margin-top: 1rem; }

	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; cursor: pointer; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; margin-top: 0.5rem; }

	@media (max-width: 800px) {
		.playback-layout { flex-direction: column; }
		.playback-sidebar { width: 100%; max-height: none; }
	}
</style>
