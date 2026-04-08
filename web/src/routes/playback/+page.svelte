<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import Icon from '$lib/components/Icon.svelte';
	import { toast } from '$lib/toast.svelte';

	type StoryOption = { id: number; title: string; subgraph_name: string };
	type SavedScript = { filename: string; name: string; story_title: string; turns: number; created: string };
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
	let savedScripts = $state<SavedScript[]>([]);
	let selectedStoryId = $state<number | null>(null);
	let loadingStories = $state(true);

	// Mode
	type Mode = 'generate' | 'replay';
	let mode = $state<Mode>('generate');
	let maxTurns = $state(5);
	let delayBetweenTurns = $state(1);

	// Replay mode
	let replayMessages = $state<string[]>([]);
	let loadedScriptName = $state('');

	// Playback state
	type PlayState = 'idle' | 'starting' | 'playing' | 'paused' | 'done';
	let playState = $state<PlayState>('idle');
	let turns = $state<TurnResult[]>([]);
	let generatedMessages = $state<string[]>([]);
	let currentTurn = $state(0);
	let openingText = $state('');
	let gameTitle = $state('');
	let subgraphName = $state('');
	let playerName = $state('');
	let playerBackground = $state('');
	let totalTime = $state(0);
	let error = $state('');

	// Save script
	let scriptName = $state('');
	let savingScript = $state(false);

	// Stats
	let avgTime = $derived(turns.length > 0 ? turns.reduce((a, t) => a + t.time_seconds, 0) / turns.length : 0);
	let avgLength = $derived(turns.length > 0 ? Math.round(turns.reduce((a, t) => a + t.response_length, 0) / turns.length) : 0);

	let logEl = $state<HTMLDivElement | undefined>(undefined);

	onMount(async () => {
		try {
			const [ownR, pubR, scriptsR] = await Promise.all([
				fetch('/api/stories', { credentials: 'include' }),
				fetch('/api/stories/public', { credentials: 'include' }),
				fetch('/api/playback-scripts', { credentials: 'include' }),
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

			if (scriptsR.ok) {
				savedScripts = await scriptsR.json();
			}
		} catch { /* ignore */ }
		loadingStories = false;
	});

	async function scrollToBottom() {
		await tick();
		if (logEl) logEl.scrollTop = logEl.scrollHeight;
	}

	async function apiCall(method: string, path: string, body?: unknown): Promise<Record<string, unknown>> {
		const opts: RequestInit = { method, credentials: 'include', headers: { 'Content-Type': 'application/json' } };
		if (body) opts.body = JSON.stringify(body);
		const r = await fetch(`/api${path}`, opts);
		return await r.json().catch(() => ({}));
	}

	function parseMoods(data: Record<string, unknown>): Record<string, Record<string, number>> {
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
		return moods;
	}

	async function loadScript(filename: string) {
		const data = await apiCall('GET', `/playback-scripts/${filename}`);
		if (data.messages && Array.isArray(data.messages)) {
			replayMessages = data.messages as string[];
			maxTurns = replayMessages.length;
			loadedScriptName = String(data.name ?? filename);
			mode = 'replay';
			if (data.story_id) selectedStoryId = Number(data.story_id);
			toast(`Loaded script: ${loadedScriptName}`, 'success');
		}
	}

	async function startPlayback() {
		if (!selectedStoryId) return;
		playState = 'starting';
		error = '';
		turns = [];
		generatedMessages = [];
		currentTurn = 0;
		totalTime = 0;

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
			playerName = String((state.player as Record<string, unknown>)?.name ?? 'the player');
			playerBackground = String((state.player as Record<string, unknown>)?.background ?? '');
		}

		playState = 'playing';
		await scrollToBottom();
		await runTurns();
	}

	async function runTurns() {
		const startTime = performance.now();
		const numTurns = mode === 'replay' ? replayMessages.length : maxTurns;

		for (let i = turns.length; i < numTurns; i++) {
			if (playState !== 'playing') break;

			currentTurn = i + 1;
			let msg: string;

			if (mode === 'replay') {
				msg = replayMessages[i] ?? 'I look around.';
			} else {
				// Generate mode — LLM creates the player action
				const lastResponse = turns.length > 0 ? turns[turns.length - 1].response : openingText;
				const prevActions = generatedMessages;

				const genData = await apiCall('POST', '/ai/generate-player-action', {
					scene: lastResponse,
					player_name: playerName,
					player_background: playerBackground,
					game_title: gameTitle,
					previous_actions: prevActions,
					turn_number: i + 1,
					total_turns: numTurns,
				});
				msg = String(genData.action ?? 'I look around.');
				generatedMessages = [...generatedMessages, msg];
			}

			// Delay between turns
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

			const turn: TurnResult = {
				turn: i + 1,
				message: msg,
				response: String(data.response ?? ''),
				moods: parseMoods(data),
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

	async function saveScript() {
		if (!scriptName.trim() || generatedMessages.length === 0) return;
		savingScript = true;
		const data = await apiCall('POST', '/playback-scripts', {
			name: scriptName.trim(),
			story_id: selectedStoryId,
			story_title: gameTitle,
			messages: generatedMessages,
		});
		if (data.ok) {
			toast(`Script saved: ${scriptName}`, 'success');
			savedScripts = [...savedScripts, {
				filename: String(data.filename),
				name: scriptName,
				story_title: gameTitle,
				turns: generatedMessages.length,
				created: new Date().toISOString(),
			}];
			scriptName = '';
		}
		savingScript = false;
	}

	function downloadResults() {
		const results = {
			story_id: selectedStoryId,
			game_title: gameTitle,
			subgraph: subgraphName,
			mode,
			opening: openingText,
			total_time: totalTime,
			avg_turn_time: Math.round(avgTime * 100) / 100,
			avg_response_length: avgLength,
			messages: mode === 'generate' ? generatedMessages : replayMessages.slice(0, turns.length),
			turns,
			timestamp: new Date().toISOString(),
		};
		const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `playback_${mode}_story${selectedStoryId}_${Date.now()}.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function moodColor(v: number): string {
		if (v <= 3) return '#f28b82';
		if (v <= 5) return '#f6b93b';
		if (v <= 7) return '#8ab4f8';
		return '#81c995';
	}

	function reset() {
		playState = 'idle';
		turns = [];
		generatedMessages = [];
		error = '';
	}
</script>

<svelte:head>
	<title>Playback — RPG Engine</title>
</svelte:head>

<section class="playback">
	<h1><Icon name="play" size={24} /> Playback Viewer</h1>
	<p class="lede">Generate natural player dialogue, save as scripts, and replay to test different models.</p>

	{#if playState === 'idle'}
		<div class="setup">
			<!-- Mode selector -->
			<div class="mode-toggle">
				<button type="button" class="mode-btn" class:active={mode === 'generate'} onclick={() => mode = 'generate'}>
					Generate Script
				</button>
				<button type="button" class="mode-btn" class:active={mode === 'replay'} onclick={() => mode = 'replay'}>
					Replay Script
				</button>
			</div>

			{#if mode === 'generate'}
				<p class="mode-desc">The LLM plays as the character, generating natural responses to the narrator. The resulting messages are saved as a reusable test script.</p>
			{:else}
				<p class="mode-desc">Load a saved script and replay it against the current model/settings. Same messages every time for fair comparison.</p>
			{/if}

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
					<input type="number" min="1" max="20" bind:value={maxTurns} disabled={mode === 'replay' && replayMessages.length > 0} />
				</label>

				<label class="field">
					<strong>Delay (sec)</strong>
					<input type="number" min="0" max="10" step="0.5" bind:value={delayBetweenTurns} />
				</label>
			</div>

			{#if mode === 'replay'}
				{#if savedScripts.length > 0}
					<div class="scripts-list">
						<strong>Saved Scripts</strong>
						{#each savedScripts as sc (sc.filename)}
							<div class="script-row">
								<button type="button" class="script-link" onclick={() => loadScript(sc.filename)}>
									{sc.name}
								</button>
								<span class="script-meta">{sc.turns} turns · {sc.story_title}</span>
							</div>
						{/each}
					</div>
				{:else}
					<p class="muted">No saved scripts yet. Use Generate mode first to create one.</p>
				{/if}

				{#if loadedScriptName}
					<div class="loaded-script">
						<strong>Loaded: {loadedScriptName}</strong>
						<ol class="message-preview">
							{#each replayMessages as msg, i (i)}
								<li>{msg}</li>
							{/each}
						</ol>
					</div>
				{/if}
			{/if}

			<button type="button" class="btn primary start-btn"
				disabled={!selectedStoryId || (mode === 'replay' && replayMessages.length === 0)}
				onclick={startPlayback}>
				<Icon name="play" size={16} /> {mode === 'generate' ? 'Generate & Play' : 'Replay Script'}
			</button>
			{#if error}<p class="err">{error}</p>{/if}
		</div>
	{:else}
		<div class="playback-layout">
			<div class="playback-main">
				<div class="controls">
					<div class="controls-left">
						<span class="game-info">{gameTitle} · {subgraphName}</span>
						<span class="mode-badge">{mode === 'generate' ? 'Generating' : 'Replaying'}</span>
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
						<span class="turn-counter">Turn {currentTurn}/{mode === 'replay' ? replayMessages.length : maxTurns}</span>
					</div>
				</div>

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
								<div class="entry-label">{mode === 'generate' ? 'AI Player' : 'Player'} · Turn {turn.turn}</div>
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
								<span class="spinner"></span> {mode === 'generate' ? 'Generating player action + narrator response...' : 'Waiting for response...'}
							</div>
						{/if}
					</div>
				</div>
			</div>

			<aside class="playback-sidebar">
				<h3>Stats</h3>
				<dl class="kv">
					<dt>Mode</dt><dd>{mode}</dd>
					<dt>Turns</dt><dd>{turns.length}/{mode === 'replay' ? replayMessages.length : maxTurns}</dd>
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

				{#if mode === 'generate' && generatedMessages.length > 0}
					<h3>Save Script</h3>
					<p class="hint">Save the generated messages as a reusable test script.</p>
					<input type="text" placeholder="Script name..." bind:value={scriptName} />
					<button type="button" class="btn sm primary" style="margin-top:0.35rem"
						disabled={!scriptName.trim() || savingScript}
						onclick={saveScript}>
						{savingScript ? 'Saving...' : 'Save Script'}
					</button>
				{/if}

				<div class="done-actions">
					<button type="button" class="btn sm" onclick={downloadResults}>
						<Icon name="download" size={12} /> Download JSON
					</button>
					{#if playState === 'done'}
						<button type="button" class="btn primary" onclick={reset}>New Test</button>
					{/if}
				</div>
			</aside>
		</div>
	{/if}
</section>

<style>
	.playback { max-width: 1200px; margin: 0 auto; padding: 0 1rem 2rem; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.setup { max-width: 700px; }
	.mode-toggle { display: flex; gap: 0; margin-bottom: 0.75rem; }
	.mode-btn { padding: 0.5rem 1.25rem; border: 1px solid #2a2f38; background: #1a1d23; color: #9aa0a6; cursor: pointer; font: inherit; font-size: 0.9rem; }
	.mode-btn:first-child { border-radius: 8px 0 0 8px; }
	.mode-btn:last-child { border-radius: 0 8px 8px 0; }
	.mode-btn.active { background: #1a73e8; border-color: #1a73e8; color: #fff; }
	.mode-desc { font-size: 0.85rem; color: #9aa0a6; margin: 0 0 1rem; line-height: 1.5; }
	.setup-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
	.setup-row .field { flex: 1; min-width: 150px; }
	.field { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.75rem; }
	.field strong { font-size: 0.9rem; }
	.scripts-list { margin: 1rem 0; }
	.scripts-list strong { display: block; margin-bottom: 0.5rem; }
	.script-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; }
	.script-link { background: none; border: none; color: #8ab4f8; font: inherit; cursor: pointer; text-decoration: underline; }
	.script-meta { font-size: 0.78rem; color: #9aa0a6; }
	.loaded-script { margin: 1rem 0; padding: 0.75rem; background: #1a1d23; border: 1px solid #2a2f38; border-radius: 8px; }
	.message-preview { margin: 0.5rem 0 0; padding-left: 1.25rem; font-size: 0.85rem; color: #bdc1c6; }
	.message-preview li { margin-bottom: 0.2rem; }
	.start-btn { font-size: 1rem; padding: 0.6rem 1.5rem; margin-top: 1rem; }
	.playback-layout { display: flex; gap: 1rem; }
	.playback-main { flex: 1; min-width: 0; }
	.playback-sidebar { width: 250px; flex-shrink: 0; background: #13151a; border: 1px solid #2a2f38; border-radius: 10px; padding: 0.75rem; overflow-y: auto; max-height: calc(100vh - 8rem); }
	.playback-sidebar h3 { font-size: 0.9rem; margin: 0.75rem 0 0.35rem; }
	.playback-sidebar h3:first-child { margin-top: 0; }
	.controls { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; margin-bottom: 0.5rem; border-bottom: 1px solid #2a2f38; }
	.controls-left { display: flex; gap: 0.5rem; align-items: center; font-size: 0.85rem; color: #9aa0a6; }
	.controls-right { display: flex; gap: 0.5rem; align-items: center; }
	.mode-badge { font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 12px; background: #1a3a5c; color: #8ab4f8; font-weight: 600; }
	.turn-counter { font-size: 0.82rem; color: #8ab4f8; font-weight: 600; }
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
	.hint { font-size: 0.78rem; color: #9aa0a6; margin: 0.25rem 0; }
	.done-actions { margin-top: 1rem; display: flex; flex-direction: column; gap: 0.5rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; cursor: pointer; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; margin-top: 0.5rem; }
	@media (max-width: 800px) { .playback-layout { flex-direction: column; } .playback-sidebar { width: 100%; max-height: none; } }
</style>
