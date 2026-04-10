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
		bubble_count: number;
		time_seconds: number;
		response_length: number;
	};

	// Setup
	let stories = $state<StoryOption[]>([]);
	let savedScripts = $state<SavedScript[]>([]);
	let selectedStoryId = $state<number | null>(null);
	let loadingStories = $state(true);

	// Mode
	type Mode = 'generate' | 'replay' | 'compare';
	let mode = $state<Mode>('generate');
	let maxTurns = $state(5);
	let delayBetweenTurns = $state(1);

	// Compare mode
	type ModelOption = { id: string; name: string; provider: string };
	let availableModels = $state<ModelOption[]>([]);
	let modelA = $state('');
	let modelB = $state('');
	let compareResults = $state<{ modelA: TurnResult[]; modelB: TurnResult[] } | null>(null);
	let compareRunning = $state(false);
	let comparePhase = $state<'idle' | 'running_a' | 'running_b' | 'done'>('idle');

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

	// Evaluation
	type Evaluation = {
		overall_score?: number;
		summary?: string;
		strengths?: string[];
		weaknesses?: string[];
		turn_scores?: { turn: number; relevance: number; prose_quality: number; engagement: number; note: string }[];
		consistency?: string;
		pacing?: string;
		suggestions?: string[];
		parse_error?: boolean;
	};
	type Recommendation = {
		priority: string;
		category: string;
		title: string;
		description: string;
		implementation: string;
		expected_impact: string;
	};
	type Analysis = {
		analysis?: { primary_issue?: string; score_trend?: string; worst_turn?: number; best_turn?: number };
		recommendations?: Recommendation[];
		prompt_suggestions?: { narrator_prompt_additions?: string; player_generator_improvements?: string };
		raw_response?: string;
		parse_error?: boolean;
	};
	let evaluation = $state<Evaluation | null>(null);
	let evaluating = $state(false);
	let evalError = $state('');
	let analysis = $state<Analysis | null>(null);
	let analyzing = $state(false);
	let analysisError = $state('');
	let activeTab = $state<'playback' | 'evaluate' | 'node_health'>('playback');

	// Node health analysis (client-side only, no API)
	type NodeStatus = 'ok' | 'skipped' | 'warn' | 'error';
	type NodeHealthTurn = {
		turn: number;
		bubbles: { status: NodeStatus; detail: string };
		narrator: { status: NodeStatus; chars: number };
		condense: { status: NodeStatus; words: number };
		memory: { status: NodeStatus; detail: string };
		time: number;
	};
	type MoodSnapshot = { turn: number; moods: Record<string, Record<string, number>> };
	type NodeHealthReport = {
		turns: NodeHealthTurn[];
		issues: string[];
		memorySummaries: { turn: number; summary: string }[];
		moodSnapshots: MoodSnapshot[];
		stats: {
			avgResponseChars: number;
			avgTime: number;
			memoryPopulated: number;
			memoryEmpty: number;
			avgBubbles: number;
			maxMemoryWords: number;
		};
	};
	let nodeHealth = $state<NodeHealthReport | null>(null);

	function analyzeNodeHealth() {
		const healthTurns: NodeHealthTurn[] = [];
		const issues: string[] = [];
		const memorySummaries: { turn: number; summary: string }[] = [];
		const moodSnapshots: MoodSnapshot[] = [];
		let memoryPopulated = 0;
		let memoryEmpty = 0;
		let maxMemoryWords = 0;
		let bubbleSum = 0;

		for (const t of turns) {
			const bc = t.bubble_count;
			bubbleSum += bc;
			let bubbles: { status: NodeStatus; detail: string };
			if (bc <= 0) {
				bubbles = { status: 'skipped', detail: 'No bubbles' };
			} else if (bc === 1) {
				bubbles = { status: 'ok', detail: '1 bubble' };
			} else {
				bubbles = { status: 'ok', detail: `${bc} bubbles` };
			}

			const narrator = {
				status: (t.response_length > 0 ? 'ok' : 'error') as NodeStatus,
				chars: t.response_length,
			};

			const memWords = t.memory_summary ? t.memory_summary.split(/\s+/).length : 0;
			if (memWords > maxMemoryWords) maxMemoryWords = memWords;

			let condense: { status: NodeStatus; words: number };
			let memory: { status: NodeStatus; detail: string };
			if (t.memory_summary) {
				condense = {
					status: memWords > 120 ? 'warn' : 'ok',
					words: memWords,
				};
				memory = { status: 'ok', detail: 'Stored' };
				memoryPopulated++;
				memorySummaries.push({ turn: t.turn, summary: t.memory_summary });
				if (memWords > 120) {
					issues.push(`Turn ${t.turn}: Memory summary at ${memWords} words — exceeds 100 word target`);
				}
			} else {
				condense = { status: 'skipped', words: 0 };
				memory = { status: 'skipped', detail: 'Empty' };
				memoryEmpty++;
			}

			if (t.response_length === 0) {
				issues.push(`Turn ${t.turn}: Empty combined response`);
			}
			if (t.response_length > 2000) {
				issues.push(`Turn ${t.turn}: Response very long (${t.response_length} chars) — may need shorter prompt`);
			}

			if (t.moods && Object.keys(t.moods).length > 0) {
				moodSnapshots.push({ turn: t.turn, moods: t.moods });
			}

			healthTurns.push({ turn: t.turn, bubbles, narrator, condense, memory, time: t.time_seconds });
		}

		const totalChars = turns.reduce((a, t) => a + t.response_length, 0);
		const totalTime = turns.reduce((a, t) => a + t.time_seconds, 0);

		nodeHealth = {
			turns: healthTurns,
			issues,
			memorySummaries,
			moodSnapshots,
			stats: {
				avgResponseChars: turns.length > 0 ? Math.round(totalChars / turns.length) : 0,
				avgTime: turns.length > 0 ? +(totalTime / turns.length).toFixed(1) : 0,
				memoryPopulated,
				memoryEmpty,
				avgBubbles: turns.length > 0 ? +(bubbleSum / turns.length).toFixed(1) : 0,
				maxMemoryWords,
			},
		};
	}

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

			// Load available models for compare mode
			try {
				const modelsR = await fetch('/api/models', { credentials: 'include' });
				if (modelsR.ok) {
					const modelsData = await modelsR.json();
					const models: ModelOption[] = [];
					for (const [provName, prov] of Object.entries(modelsData.providers ?? {})) {
						const p = prov as { available: boolean; models: { id: string; name: string }[] };
						if (!p.available) continue;
						for (const m of p.models) {
							models.push({ id: m.id, name: m.name, provider: provName });
						}
					}
					availableModels = models;
					if (models.length >= 2) {
						modelA = models[0].id;
						modelB = models[1].id;
					}
				}
			} catch { /* ignore */ }
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
		const text = await r.text();
		try {
			const data = JSON.parse(text);
			if (!r.ok && !data.error) data.error = `HTTP ${r.status}`;
			return data;
		} catch {
			return { error: `HTTP ${r.status}: ${text.slice(0, 200)}` };
		}
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
				if (genData.error) {
					const errMsg = String(genData.error);
					console.error('generate-player-action error:', errMsg);
					// Show error but keep playing with a fallback
					msg = `[Action generation failed: ${errMsg.slice(0, 80)}]`;
				} else {
					msg = String(genData.action ?? 'I consider what to do next.');
				}
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

			const bubblesRaw = data.bubbles;
			const bubbleCount = Array.isArray(bubblesRaw) ? bubblesRaw.length : 0;
			const turn: TurnResult = {
				turn: i + 1,
				message: msg,
				response: String(data.response ?? ''),
				moods: parseMoods(data),
				memory_summary: String(data.memory_summary ?? ''),
				bubble_count: bubbleCount,
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

	async function runCompare() {
		if (!selectedStoryId || !modelA || !modelB || replayMessages.length === 0) return;
		compareRunning = true;
		compareResults = null;
		comparePhase = 'running_a';

		const runWithModel = async (model: string): Promise<TurnResult[]> => {
			// Set model override
			await apiCall('POST', '/settings/model-override', { model });
			// Start fresh game
			await apiCall('POST', '/play/start', { story_id: selectedStoryId });

			const results: TurnResult[] = [];
			for (let i = 0; i < replayMessages.length; i++) {
				const msg = replayMessages[i];
				const turnStart = performance.now();
				const data = await apiCall('POST', '/play/chat', { story_id: selectedStoryId, message: msg });
				const turnTime = (performance.now() - turnStart) / 1000;

				if (data.error) break;

				const bubblesRaw = data.bubbles;
				const bubbleCount = Array.isArray(bubblesRaw) ? bubblesRaw.length : 0;
				results.push({
					turn: i + 1,
					message: msg,
					response: String(data.response ?? ''),
					moods: parseMoods(data),
					memory_summary: String(data.memory_summary ?? ''),
					bubble_count: bubbleCount,
					time_seconds: Math.round(turnTime * 100) / 100,
					response_length: String(data.response ?? '').length,
				});
			}

			// Clear override
			await apiCall('POST', '/settings/model-override', { model: '' });
			return results;
		};

		try {
			const resultsA = await runWithModel(modelA);
			comparePhase = 'running_b';
			const resultsB = await runWithModel(modelB);
			compareResults = { modelA: resultsA, modelB: resultsB };
			comparePhase = 'done';
		} catch {
			error = 'Compare failed';
		} finally {
			compareRunning = false;
			// Ensure override is cleared
			await apiCall('POST', '/settings/model-override', { model: '' });
		}
	}

	function downloadCompare() {
		if (!compareResults) return;
		const data = {
			story_id: selectedStoryId,
			game_title: gameTitle || 'Compare Test',
			model_a: modelA,
			model_b: modelB,
			script: replayMessages,
			results_a: compareResults.modelA,
			results_b: compareResults.modelB,
			timestamp: new Date().toISOString(),
		};
		const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `compare_${modelA.replace(/[/:]/g, '_')}_vs_${modelB.replace(/[/:]/g, '_')}_${Date.now()}.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function runEvaluation() {
		evaluating = true;
		evalError = '';
		evaluation = null;
		try {
			const data = await apiCall('POST', '/ai/evaluate-playback', {
				game_title: gameTitle,
				opening: openingText,
				turns: turns.map(t => ({ turn: t.turn, message: t.message, response: t.response })),
			});
			if (data.error) {
				evalError = String(data.error);
			} else if (data.evaluation) {
				evaluation = data.evaluation as Evaluation;
				activeTab = 'evaluate';
			}
		} catch {
			evalError = 'Network error';
		} finally {
			evaluating = false;
		}
	}

	async function runAnalysis() {
		if (!evaluation) return;
		analyzing = true;
		analysisError = '';
		analysis = null;
		try {
			const data = await apiCall('POST', '/ai/analyze-evaluation', {
				evaluation,
				game_title: gameTitle,
				subgraph: subgraphName,
				turns: turns.map(t => ({ turn: t.turn, message: t.message, response: t.response.slice(0, 200) })),
			});
			if (data.error) {
				analysisError = String(data.error);
			} else if (data.analysis) {
				analysis = data.analysis as Analysis;
			}
		} catch {
			analysisError = 'Network error';
		} finally {
			analyzing = false;
		}
	}

	function priorityColor(p: string): string {
		if (p === 'high') return '#f28b82';
		if (p === 'medium') return '#f6b93b';
		return '#81c995';
	}

	function buildEvalReport(): string {
		let report = `# Playback Evaluation Report\n`;
		report += `**Game:** ${gameTitle}\n`;
		report += `**Subgraph:** ${subgraphName}\n`;
		report += `**Turns:** ${turns.length}\n`;
		report += `**Date:** ${new Date().toLocaleString()}\n\n`;

		if (evaluation) {
			report += `## Evaluation\n\n`;
			if (evaluation.overall_score) report += `**Overall Score: ${evaluation.overall_score}/10**\n\n`;
			if (evaluation.summary) report += `${evaluation.summary}\n\n`;

			if (evaluation.strengths?.length) {
				report += `### Strengths\n`;
				for (const s of evaluation.strengths) report += `- ${s}\n`;
				report += `\n`;
			}
			if (evaluation.weaknesses?.length) {
				report += `### Weaknesses\n`;
				for (const w of evaluation.weaknesses) report += `- ${w}\n`;
				report += `\n`;
			}
			if (evaluation.consistency) report += `### Consistency\n${evaluation.consistency}\n\n`;
			if (evaluation.pacing) report += `### Pacing\n${evaluation.pacing}\n\n`;

			if (evaluation.turn_scores?.length) {
				report += `### Per-Turn Scores\n`;
				report += `| Turn | Relevance | Prose | Engage | Note |\n`;
				report += `|------|-----------|-------|--------|------|\n`;
				for (const ts of evaluation.turn_scores) {
					report += `| ${ts.turn} | ${ts.relevance} | ${ts.prose_quality} | ${ts.engagement} | ${ts.note} |\n`;
				}
				report += `\n`;
			}
			if (evaluation.suggestions?.length) {
				report += `### Suggestions\n`;
				for (const s of evaluation.suggestions) report += `- ${s}\n`;
				report += `\n`;
			}
		}

		if (analysis) {
			report += `## Recommendations\n\n`;
			if (analysis.analysis) {
				report += `**Primary Issue:** ${analysis.analysis.primary_issue ?? 'N/A'}\n`;
				report += `**Score Trend:** ${analysis.analysis.score_trend ?? 'N/A'}\n`;
				report += `**Best Turn:** ${analysis.analysis.best_turn ?? 'N/A'} | **Worst Turn:** ${analysis.analysis.worst_turn ?? 'N/A'}\n\n`;
			}
			if (analysis.recommendations?.length) {
				for (const rec of analysis.recommendations) {
					report += `### [${rec.priority.toUpperCase()}] ${rec.title}\n`;
					report += `**Category:** ${rec.category}\n\n`;
					report += `${rec.description}\n\n`;
					report += `**Implementation:**\n\`\`\`\n${rec.implementation}\n\`\`\`\n\n`;
					report += `**Expected impact:** ${rec.expected_impact}\n\n`;
				}
			}
			if (analysis.prompt_suggestions) {
				report += `### Prompt Suggestions\n\n`;
				if (analysis.prompt_suggestions.narrator_prompt_additions) {
					report += `**Add to narrator prompt:**\n\`\`\`\n${analysis.prompt_suggestions.narrator_prompt_additions}\n\`\`\`\n\n`;
				}
				if (analysis.prompt_suggestions.player_generator_improvements) {
					report += `**Player action generator:**\n\`\`\`\n${analysis.prompt_suggestions.player_generator_improvements}\n\`\`\`\n\n`;
				}
			}
		}

		// Include turn transcript
		report += `## Turn Transcript\n\n`;
		for (const t of turns) {
			report += `### Turn ${t.turn}\n`;
			report += `**Player:** ${t.message}\n\n`;
			report += `**Response:** ${t.response.slice(0, 300)}${t.response.length > 300 ? '...' : ''}\n\n`;
			if (t.bubble_count > 0) report += `**Bubbles:** ${t.bubble_count}\n\n`;
		}

		return report;
	}

	async function copyReport() {
		const report = buildEvalReport();
		try {
			if (navigator.clipboard && navigator.clipboard.writeText) {
				await navigator.clipboard.writeText(report);
				toast('Report copied to clipboard', 'success');
			} else {
				// Fallback for non-HTTPS or older browsers
				const textarea = document.createElement('textarea');
				textarea.value = report;
				textarea.style.position = 'fixed';
				textarea.style.opacity = '0';
				document.body.appendChild(textarea);
				textarea.select();
				document.execCommand('copy');
				document.body.removeChild(textarea);
				toast('Report copied to clipboard', 'success');
			}
		} catch {
			// If all else fails, download instead
			downloadReport();
			toast('Copy failed — downloaded as file instead', 'warning');
		}
	}

	function downloadReport() {
		const report = buildEvalReport();
		const blob = new Blob([report], { type: 'text/markdown' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `eval_report_${gameTitle.replace(/\s+/g, '_').toLowerCase()}_${Date.now()}.md`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function buildNodeHealthReport(): string {
		if (!nodeHealth) return '';
		const nh = nodeHealth;
		let r = `# Node Health Report\n`;
		r += `**Game:** ${gameTitle}\n`;
		r += `**Subgraph:** ${subgraphName}\n`;
		r += `**Turns:** ${turns.length}\n`;
		r += `**Date:** ${new Date().toLocaleString()}\n\n`;

		r += `## Stats\n`;
		r += `- Avg Response Chars: ${nh.stats.avgResponseChars}\n`;
		r += `- Avg Turn Time: ${nh.stats.avgTime}s\n`;
		r += `- Avg Bubbles / Turn: ${nh.stats.avgBubbles}\n`;
		r += `- Memory Populated: ${nh.stats.memoryPopulated}/${nh.stats.memoryPopulated + nh.stats.memoryEmpty}\n`;
		r += `- Max Summary Words: ${nh.stats.maxMemoryWords}\n\n`;

		if (nh.issues.length > 0) {
			r += `## Issues Detected\n`;
			for (const issue of nh.issues) r += `- ${issue}\n`;
			r += `\n`;
		}

		r += `## Per-Turn Node Status\n`;
		r += `| Turn | Bubbles | Response | Condense | Memory | Time |\n`;
		r += `|------|---------|----------|----------|--------|------|\n`;
		for (const t of nh.turns) {
			r += `| ${t.turn} | ${t.bubbles.detail} | ${t.narrator.chars} chars | ${t.condense.words > 0 ? `${t.condense.words} words` : 'Empty'} | ${t.memory.detail} | ${t.time.toFixed(1)}s |\n`;
		}
		r += `\n`;

		if (nh.memorySummaries.length > 0) {
			r += `## Memory Summary Progression\n`;
			for (const ms of nh.memorySummaries) {
				r += `### Turn ${ms.turn} (${ms.summary.split(/\s+/).length} words)\n`;
				r += `${ms.summary}\n\n`;
			}
		}

		if (nh.moodSnapshots.length > 0) {
			r += `## Mood Progression\n`;
			r += `| Turn |`;
			const firstSnap = nh.moodSnapshots[0];
			const headers: string[] = [];
			for (const [char, axes] of Object.entries(firstSnap.moods)) {
				for (const axis of Object.keys(axes)) {
					headers.push(`${char.replace(/_/g, ' ')} — ${axis}`);
				}
			}
			r += headers.map(h => ` ${h} |`).join('') + `\n`;
			r += `|------|` + headers.map(() => `------|`).join('') + `\n`;
			for (const snap of nh.moodSnapshots) {
				r += `| ${snap.turn} |`;
				for (const axes of Object.values(snap.moods)) {
					for (const val of Object.values(axes)) {
						r += ` ${val}/10 |`;
					}
				}
				r += `\n`;
			}
			r += `\n`;
		}

		return r;
	}

	async function copyNodeHealthReport() {
		const report = buildNodeHealthReport();
		try {
			if (navigator.clipboard && navigator.clipboard.writeText) {
				await navigator.clipboard.writeText(report);
				toast('Node health report copied to clipboard', 'success');
			} else {
				const textarea = document.createElement('textarea');
				textarea.value = report;
				textarea.style.position = 'fixed';
				textarea.style.opacity = '0';
				document.body.appendChild(textarea);
				textarea.select();
				document.execCommand('copy');
				document.body.removeChild(textarea);
				toast('Node health report copied to clipboard', 'success');
			}
		} catch {
			downloadNodeHealthReport();
			toast('Copy failed — downloaded as file instead', 'warning');
		}
	}

	function downloadNodeHealthReport() {
		const report = buildNodeHealthReport();
		const blob = new Blob([report], { type: 'text/markdown' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `node_health_${gameTitle.replace(/\s+/g, '_').toLowerCase()}_${Date.now()}.md`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function scoreColor(score: number): string {
		if (score >= 8) return '#81c995';
		if (score >= 6) return '#8ab4f8';
		if (score >= 4) return '#f6b93b';
		return '#f28b82';
	}

	async function reset() {
		playState = 'idle';
		turns = [];
		generatedMessages = [];
		error = '';
		// Refresh saved scripts list
		try {
			const r = await fetch('/api/playback-scripts', { credentials: 'include' });
			if (r.ok) savedScripts = await r.json();
		} catch { /* ignore */ }
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
			<div class="mode-toggle" aria-label="Playback mode">
				<button type="button" class="mode-btn" class:active={mode === 'generate'} onclick={() => mode = 'generate'}>
					Generate
				</button>
				<button type="button" class="mode-btn" class:active={mode === 'replay'} onclick={() => mode = 'replay'}>
					Replay
				</button>
				<button type="button" class="mode-btn" class:active={mode === 'compare'} onclick={() => mode = 'compare'}>
					Compare
				</button>
			</div>

			{#if mode === 'generate'}
				<p class="mode-desc">The LLM plays as the character, generating natural responses to the narrator. The resulting messages are saved as a reusable test script.</p>
			{:else if mode === 'replay'}
				<p class="mode-desc">Load a saved script and replay it against the current model/settings. Same messages every time for fair comparison.</p>
			{:else}
				<p class="mode-desc">Run the same script against two models side by side. Same messages, different models — compare quality and speed.</p>
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

			{#if mode === 'compare'}
				{#if savedScripts.length > 0}
					<div class="scripts-list">
						<strong>Select Script</strong>
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
					<p class="muted">No saved scripts. Generate one first.</p>
				{/if}

				{#if loadedScriptName}
					<p class="muted">Script: <strong>{loadedScriptName}</strong> ({replayMessages.length} turns)</p>
				{/if}

				<div class="model-select-row">
					<label class="field">
						<strong>Model A</strong>
						<select bind:value={modelA}>
							{#each availableModels as m (m.id)}
								<option value={m.id}>{m.name} ({m.provider})</option>
							{/each}
						</select>
					</label>
					<span class="vs-label">vs</span>
					<label class="field">
						<strong>Model B</strong>
						<select bind:value={modelB}>
							{#each availableModels as m (m.id)}
								<option value={m.id}>{m.name} ({m.provider})</option>
							{/each}
						</select>
					</label>
				</div>
			{/if}

			{#if mode === 'compare'}
				<button type="button" class="btn primary start-btn"
					disabled={!selectedStoryId || replayMessages.length === 0 || !modelA || !modelB || modelA === modelB || compareRunning}
					onclick={runCompare}>
					<Icon name="play" size={16} /> {compareRunning ? (comparePhase === 'running_a' ? `Running Model A...` : `Running Model B...`) : 'Run Comparison'}
				</button>
			{:else}
				<button type="button" class="btn primary start-btn"
					disabled={!selectedStoryId || (mode === 'replay' && replayMessages.length === 0)}
					onclick={startPlayback}>
					<Icon name="play" size={16} /> {mode === 'generate' ? 'Generate & Play' : 'Replay Script'}
				</button>
			{/if}
			{#if error}<p class="err">{error}</p>{/if}

			{#if compareResults}
				<div class="compare-results">
					<h2>Comparison Results</h2>
					<div class="compare-grid">
						<div class="compare-col">
							<h3>Model A: {modelA.split('/').pop()}</h3>
							<div class="compare-stats">
								<span>Avg time: {(compareResults.modelA.reduce((a, t) => a + t.time_seconds, 0) / compareResults.modelA.length).toFixed(1)}s</span>
								<span>Avg length: {Math.round(compareResults.modelA.reduce((a, t) => a + t.response_length, 0) / compareResults.modelA.length)} chars</span>
							</div>
							{#each compareResults.modelA as turn (turn.turn)}
								<div class="compare-turn">
									<div class="compare-turn-header">Turn {turn.turn} · {turn.time_seconds}s</div>
									<div class="compare-player">{turn.message}</div>
									<div class="compare-response">{turn.response.slice(0, 300)}{turn.response.length > 300 ? '...' : ''}</div>
								</div>
							{/each}
						</div>
						<div class="compare-col">
							<h3>Model B: {modelB.split('/').pop()}</h3>
							<div class="compare-stats">
								<span>Avg time: {(compareResults.modelB.reduce((a, t) => a + t.time_seconds, 0) / compareResults.modelB.length).toFixed(1)}s</span>
								<span>Avg length: {Math.round(compareResults.modelB.reduce((a, t) => a + t.response_length, 0) / compareResults.modelB.length)} chars</span>
							</div>
							{#each compareResults.modelB as turn (turn.turn)}
								<div class="compare-turn">
									<div class="compare-turn-header">Turn {turn.turn} · {turn.time_seconds}s</div>
									<div class="compare-player">{turn.message}</div>
									<div class="compare-response">{turn.response.slice(0, 300)}{turn.response.length > 300 ? '...' : ''}</div>
								</div>
							{/each}
						</div>
					</div>
					<div class="compare-actions">
						<button type="button" class="btn" onclick={downloadCompare}>
							<Icon name="download" size={14} /> Download Comparison JSON
						</button>
					</div>
				</div>
			{/if}
		</div>
	{:else}
		<!-- Tab bar -->
		{#if turns.length > 0}
			<p class="tab-hint">Results views</p>
			<div class="tab-bar">
				<button type="button" class="tab-btn" class:active={activeTab === 'playback'} onclick={() => activeTab = 'playback'}>Playback</button>
				<button type="button" class="tab-btn" class:active={activeTab === 'evaluate'} onclick={() => activeTab = 'evaluate'}>Evaluate</button>
				<button type="button" class="tab-btn" class:active={activeTab === 'node_health'} onclick={() => activeTab = 'node_health'}>Node Health</button>
			</div>
		{/if}

		{#if activeTab === 'evaluate' && turns.length > 0}
			<!-- Evaluate tab -->
			<div class="eval-panel">
				{#if !evaluation && !evaluating}
					<div class="eval-start">
						<h2>AI Evaluation</h2>
						<p>Send this play session to Azure GPT-4o-mini for quality analysis. The judge evaluates relevance, prose quality, engagement, consistency, and pacing.</p>
						<button type="button" class="btn primary" disabled={evaluating} onclick={runEvaluation}>
							<Icon name="zap" size={14} /> Run Evaluation
						</button>
						{#if evalError}<p class="err">{evalError}</p>{/if}
					</div>
				{:else if evaluating}
					<div class="eval-loading">
						<span class="spinner"></span> Azure is evaluating {turns.length} turns...
					</div>
				{:else if evaluation}
					<div class="eval-results" transition:fade={{ duration: 200 }}>
						{#if evaluation.overall_score}
							<div class="eval-overall">
								<div class="eval-score" style="color:{scoreColor(evaluation.overall_score)}">{evaluation.overall_score}<span class="score-max">/10</span></div>
								<p class="eval-summary">{evaluation.summary ?? ''}</p>
							</div>
						{/if}

						{#if evaluation.strengths?.length}
							<div class="eval-section">
								<h3>Strengths</h3>
								<ul>{#each evaluation.strengths as s}<li class="strength">{s}</li>{/each}</ul>
							</div>
						{/if}

						{#if evaluation.weaknesses?.length}
							<div class="eval-section">
								<h3>Weaknesses</h3>
								<ul>{#each evaluation.weaknesses as w}<li class="weakness">{w}</li>{/each}</ul>
							</div>
						{/if}

						{#if evaluation.consistency}
							<div class="eval-section">
								<h3>Consistency</h3>
								<p>{evaluation.consistency}</p>
							</div>
						{/if}

						{#if evaluation.pacing}
							<div class="eval-section">
								<h3>Pacing</h3>
								<p>{evaluation.pacing}</p>
							</div>
						{/if}

						{#if evaluation.turn_scores?.length}
							<div class="eval-section">
								<h3>Per-Turn Scores</h3>
								<table class="score-table">
									<thead>
										<tr><th>Turn</th><th>Relevance</th><th>Prose</th><th>Engage</th><th>Note</th></tr>
									</thead>
									<tbody>
										{#each evaluation.turn_scores as ts (ts.turn)}
											<tr>
												<td>{ts.turn}</td>
												<td style="color:{scoreColor(ts.relevance)}">{ts.relevance}</td>
												<td style="color:{scoreColor(ts.prose_quality)}">{ts.prose_quality}</td>
												<td style="color:{scoreColor(ts.engagement)}">{ts.engagement}</td>
												<td class="note-cell">{ts.note}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}

						{#if evaluation.suggestions?.length}
							<div class="eval-section">
								<h3>Suggestions</h3>
								<ul>{#each evaluation.suggestions as s}<li>{s}</li>{/each}</ul>
							</div>
						{/if}

						<div class="eval-actions">
							<button type="button" class="btn" onclick={runEvaluation}>
								{evaluating ? 'Re-evaluating...' : 'Re-evaluate'}
							</button>
							<button type="button" class="btn primary" disabled={analyzing} onclick={runAnalysis}>
								<Icon name="zap" size={14} /> {analyzing ? 'Analyzing...' : 'Get Recommendations'}
							</button>
						</div>

						{#if analysisError}<p class="err">{analysisError}</p>{/if}

						{#if analyzing}
							<div class="eval-loading" style="margin-top:1rem">
								<span class="spinner"></span> Azure is generating actionable recommendations...
							</div>
						{/if}

						{#if analysis}
							<div class="recs-panel" transition:fade={{ duration: 200 }}>
								{#if analysis.analysis}
									<div class="recs-overview">
										<h3>Analysis</h3>
										<dl class="recs-kv">
											{#if analysis.analysis.primary_issue}
												<dt>Primary Issue</dt><dd>{analysis.analysis.primary_issue}</dd>
											{/if}
											{#if analysis.analysis.score_trend}
												<dt>Score Trend</dt><dd>{analysis.analysis.score_trend}</dd>
											{/if}
											{#if analysis.analysis.best_turn}
												<dt>Best Turn</dt><dd>Turn {analysis.analysis.best_turn}</dd>
											{/if}
											{#if analysis.analysis.worst_turn}
												<dt>Worst Turn</dt><dd>Turn {analysis.analysis.worst_turn}</dd>
											{/if}
										</dl>
									</div>
								{/if}

								{#if analysis.recommendations?.length}
									<h3>Recommendations</h3>
									{#each analysis.recommendations as rec, i (i)}
										<div class="rec-card">
											<div class="rec-header">
												<span class="rec-priority" style="color:{priorityColor(rec.priority)}">{rec.priority.toUpperCase()}</span>
												<span class="rec-category">{rec.category}</span>
												<strong class="rec-title">{rec.title}</strong>
											</div>
											<p class="rec-desc">{rec.description}</p>
											<div class="rec-impl">
												<strong>Implementation:</strong>
												<pre class="rec-code">{rec.implementation}</pre>
											</div>
											<p class="rec-impact"><strong>Expected impact:</strong> {rec.expected_impact}</p>
										</div>
									{/each}
								{/if}

								{#if analysis.prompt_suggestions}
									<div class="prompt-suggestions">
										<h3>Prompt Suggestions</h3>
										{#if analysis.prompt_suggestions.narrator_prompt_additions}
											<div class="suggestion-block">
												<strong>Add to narrator prompt:</strong>
												<pre class="rec-code">{analysis.prompt_suggestions.narrator_prompt_additions}</pre>
											</div>
										{/if}
										{#if analysis.prompt_suggestions.player_generator_improvements}
											<div class="suggestion-block">
												<strong>Player action generator:</strong>
												<pre class="rec-code">{analysis.prompt_suggestions.player_generator_improvements}</pre>
											</div>
										{/if}
									</div>
								{/if}

								{#if analysis.parse_error && analysis.raw_response}
									<div class="eval-section">
										<h3>Raw Response (parse failed)</h3>
										<pre class="rec-code">{analysis.raw_response}</pre>
									</div>
								{/if}
							</div>
						{/if}

						{#if evaluation || analysis}
							<div class="report-actions">
								<h3>Export Report</h3>
								<div class="report-buttons">
									<button type="button" class="btn" onclick={copyReport}>
										<Icon name="copy" size={14} /> Copy to Clipboard
									</button>
									<button type="button" class="btn" onclick={downloadReport}>
										<Icon name="download" size={14} /> Download Markdown
									</button>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{:else if activeTab === 'node_health' && turns.length > 0}
			<!-- Node Health tab -->
			<div class="eval-panel">
				{#if !nodeHealth}
					<div class="eval-start">
						<h2>Node Health Analysis</h2>
						<p>Analyze pipeline behavior for this session: UI bubbles from the API, memory/condense status, response sizes, and timing. No extra API call — runs locally.</p>
						<button type="button" class="btn primary" onclick={analyzeNodeHealth}>
							<Icon name="zap" size={14} /> Analyze Nodes
						</button>
					</div>
				{:else}
					<div class="eval-results" transition:fade={{ duration: 200 }}>
						<!-- Stats overview -->
						<div class="nh-stats">
							<div class="nh-stat">
								<span class="nh-stat-value">{nodeHealth.stats.avgResponseChars}</span>
								<span class="nh-stat-label">Avg Response Chars</span>
							</div>
							<div class="nh-stat">
								<span class="nh-stat-value">{nodeHealth.stats.avgTime}s</span>
								<span class="nh-stat-label">Avg Turn Time</span>
							</div>
							<div class="nh-stat">
								<span class="nh-stat-value">{nodeHealth.stats.avgBubbles}</span>
								<span class="nh-stat-label">Avg Bubbles</span>
							</div>
							<div class="nh-stat">
								<span class="nh-stat-value">{nodeHealth.stats.memoryPopulated}/{nodeHealth.stats.memoryPopulated + nodeHealth.stats.memoryEmpty}</span>
								<span class="nh-stat-label">Memory Populated</span>
							</div>
							<div class="nh-stat">
								<span class="nh-stat-value">{nodeHealth.stats.maxMemoryWords}</span>
								<span class="nh-stat-label">Max Summary Words</span>
							</div>
						</div>

						<!-- Issues -->
						{#if nodeHealth.issues.length > 0}
							<div class="eval-section">
								<h3>Issues Detected</h3>
								<ul class="nh-issues">
									{#each nodeHealth.issues as issue}
										<li class="nh-issue">{issue}</li>
									{/each}
								</ul>
							</div>
						{:else}
							<div class="eval-section">
								<h3>Issues Detected</h3>
								<p class="nh-ok">No issues found.</p>
							</div>
						{/if}

						<!-- Per-turn table -->
						<div class="eval-section">
							<h3>Per-Turn Node Status</h3>
							<table class="score-table nh-table">
								<thead>
									<tr>
										<th>Turn</th>
										<th>Bubbles</th>
										<th>Response</th>
										<th>Condense</th>
										<th>Memory</th>
										<th>Time</th>
									</tr>
								</thead>
								<tbody>
									{#each nodeHealth.turns as t (t.turn)}
										<tr>
											<td>{t.turn}</td>
											<td>
												<span class="nh-badge nh-{t.bubbles.status}">{t.bubbles.detail}</span>
											</td>
											<td>
												<span class="nh-badge nh-{t.narrator.status}">{t.narrator.chars} chars</span>
											</td>
											<td>
												<span class="nh-badge nh-{t.condense.status}">{t.condense.words > 0 ? `${t.condense.words} words` : 'Empty'}</span>
											</td>
											<td>
												<span class="nh-badge nh-{t.memory.status}">{t.memory.detail}</span>
											</td>
											<td>{t.time.toFixed(1)}s</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>

						<!-- Memory progression -->
						{#if nodeHealth.memorySummaries.length > 0}
							<div class="eval-section">
								<h3>Memory Summary Progression</h3>
								{#each nodeHealth.memorySummaries as ms (ms.turn)}
									<div class="nh-memory-entry">
										<span class="nh-memory-turn">Turn {ms.turn}</span>
										<span class="nh-memory-words">({ms.summary.split(/\s+/).length} words)</span>
										<p class="nh-memory-text">{ms.summary}</p>
									</div>
								{/each}
							</div>
						{/if}

						<!-- Mood progression -->
						{#if nodeHealth.moodSnapshots.length > 0}
							<div class="eval-section">
								<h3>Mood Progression</h3>
								<table class="score-table nh-table">
									<thead>
										<tr>
											<th>Turn</th>
											{#each Object.keys(nodeHealth.moodSnapshots[0]?.moods ?? {}) as char}
												{#each Object.keys((nodeHealth.moodSnapshots[0]?.moods ?? {})[char] ?? {}) as axis}
													<th>{char.replace(/_/g, ' ')} — {axis}</th>
												{/each}
											{/each}
										</tr>
									</thead>
									<tbody>
										{#each nodeHealth.moodSnapshots as snap (snap.turn)}
											<tr>
												<td>{snap.turn}</td>
												{#each Object.entries(snap.moods) as [char, axes]}
													{#each Object.entries(axes) as [axis, val]}
														<td>
															<span class="nh-badge nh-mood" style="color:{val <= 3 ? '#f28b82' : val >= 7 ? '#81c995' : '#8ab4f8'}">{val}/10</span>
														</td>
													{/each}
												{/each}
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}

						<div class="eval-actions">
							<button type="button" class="btn" onclick={() => { nodeHealth = null; }}>Reset</button>
							<button type="button" class="btn" onclick={analyzeNodeHealth}>Re-analyze</button>
						</div>

						<div class="report-actions">
							<h3>Export Report</h3>
							<div class="report-buttons">
								<button type="button" class="btn" onclick={copyNodeHealthReport}>
									<Icon name="copy" size={14} /> Copy to Clipboard
								</button>
								<button type="button" class="btn" onclick={downloadNodeHealthReport}>
									<Icon name="download" size={14} /> Download Markdown
								</button>
							</div>
						</div>
					</div>
				{/if}
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
								{#if turn.bubble_count > 0}
									<div class="entry-guidance">
										<span class="guidance-label">Bubbles:</span> {turn.bubble_count}
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
	{/if}
</section>

<style>
	.playback { max-width: 1200px; margin: 0 auto; padding: 0 1rem 2rem; }
	.lede { color: #9aa0a6; margin: 0 0 1.5rem; }
	.setup { max-width: 700px; }
	.mode-toggle { display: inline-flex; gap: 0; margin-bottom: 0.6rem; border: 1px solid #2a2f38; border-radius: 10px; overflow: hidden; }
	.mode-btn { padding: 0.5rem 1.25rem; border: 0; border-right: 1px solid #2a2f38; background: #1a1d23; color: #9aa0a6; cursor: pointer; font: inherit; font-size: 0.9rem; transition: background-color 0.18s ease, color 0.18s ease; }
	.mode-btn:last-child { border-right: 0; }
	.mode-btn:first-child { border-radius: 8px 0 0 8px; }
	.mode-btn:last-child { border-radius: 0 8px 8px 0; }
	.mode-btn.active { background: #1a73e8; border-color: #1a73e8; color: #fff; }
	.mode-btn:hover { color: #e8eaed; background: #242a33; }
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
	.model-select-row { display: flex; gap: 1rem; align-items: end; flex-wrap: wrap; margin: 1rem 0; }
	.model-select-row .field { flex: 1; min-width: 200px; }
	.vs-label { font-size: 1.1rem; font-weight: 700; color: #5f6368; padding-bottom: 0.5rem; }
	.compare-results { margin-top: 2rem; }
	.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
	.compare-col { border: 1px solid #2a2f38; border-radius: 10px; padding: 0.75rem; background: #1a1d23; }
	.compare-col h3 { margin: 0 0 0.5rem; font-size: 0.95rem; }
	.compare-stats { display: flex; gap: 1rem; font-size: 0.78rem; color: #9aa0a6; margin-bottom: 0.75rem; }
	.compare-turn { margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #2a2f38; }
	.compare-turn:last-child { border-bottom: none; }
	.compare-turn-header { font-size: 0.75rem; color: #8ab4f8; font-weight: 600; margin-bottom: 0.25rem; }
	.compare-player { font-size: 0.82rem; color: #9aa0a6; margin-bottom: 0.25rem; }
	.compare-response { font-size: 0.85rem; line-height: 1.5; color: #bdc1c6; }
	.compare-actions { margin-top: 1rem; }
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
	.entry-guidance { margin-top: 0.4rem; padding: 0.4rem 0.6rem; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 4px; font-size: 0.78rem; color: #c58af9; white-space: pre-wrap; }
	.guidance-label { font-weight: 600; color: #8a6abf; }
	.mood-chip { font-size: 0.77rem; color: #d3d8df; background: #111722; border: 1px solid #2b3442; border-radius: 999px; padding: 0.22rem 0.5rem; display: inline-flex; align-items: center; gap: 0.32rem; }
	.mood-val { margin-left: 0.12rem; font-weight: 700; }
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
	/* Tab bar */
	.tab-hint { margin: 0 0 0.4rem; font-size: 0.78rem; color: #7f8691; letter-spacing: 0.03em; text-transform: uppercase; }
	.tab-bar { display: flex; gap: 0.35rem; margin-bottom: 1rem; flex-wrap: wrap; }
	.tab-btn { padding: 0.42rem 1rem; border: 1px solid #2a2f38; border-radius: 999px; background: #1a1d23; color: #9aa0a6; cursor: pointer; font: inherit; font-size: 0.82rem; transition: background-color 0.18s ease, color 0.18s ease, border-color 0.18s ease; }
	.tab-btn:first-child { border-radius: 999px; }
	.tab-btn:last-child { border-radius: 999px; }
	.tab-btn.active { background: #1a73e8; border-color: #1a73e8; color: #fff; }
	.tab-btn:hover { color: #e8eaed; border-color: #46505e; background: #20242c; }

	/* Evaluate tab */
	.eval-panel { max-width: 800px; }
	.eval-start { text-align: center; padding: 2rem; border: 1px solid #2a2f38; border-radius: 12px; background: #1a1d23; }
	.eval-start h2 { margin: 0 0 0.5rem; }
	.eval-start p { color: #bdc1c6; margin: 0 0 1.5rem; max-width: 500px; margin-left: auto; margin-right: auto; line-height: 1.5; }
	.eval-loading { text-align: center; padding: 3rem; color: #9aa0a6; }
	.eval-results { padding: 0; }
	.eval-overall { text-align: center; margin-bottom: 2rem; padding: 1.5rem; background: #1a1d23; border: 1px solid #2a2f38; border-radius: 12px; }
	.eval-score { font-size: 3rem; font-weight: 700; }
	.score-max { font-size: 1.2rem; color: #5f6368; font-weight: 400; }
	.eval-summary { color: #bdc1c6; margin: 0.5rem 0 0; line-height: 1.5; font-size: 0.95rem; }
	.eval-section { margin-bottom: 1.5rem; border: 1px solid #2a2f38; border-radius: 10px; padding: 0.85rem 1rem; background: #161a20; }
	.eval-section h3 { font-size: 1rem; margin: 0 0 0.5rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.eval-section ul { padding-left: 1.25rem; margin: 0; }
	.eval-section li { margin-bottom: 0.3rem; font-size: 0.9rem; color: #bdc1c6; line-height: 1.5; }
	.eval-section p { font-size: 0.9rem; color: #bdc1c6; line-height: 1.5; }
	.strength { color: #81c995 !important; }
	.weakness { color: #f6b93b !important; }
	.score-table { width: 100%; font-size: 0.85rem; }
	.score-table th { font-size: 0.75rem; }
	.score-table td { text-align: center; }
	.note-cell { text-align: left !important; font-size: 0.82rem; color: #9aa0a6; max-width: 250px; }
	.eval-actions { margin-top: 1.5rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.recs-panel { margin-top: 2rem; }
	.recs-overview { background: #1a1d23; border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; margin-bottom: 1.5rem; }
	.recs-kv { display: grid; grid-template-columns: 8rem 1fr; gap: 0.3rem 0.75rem; font-size: 0.9rem; margin: 0.5rem 0 0; }
	.recs-kv dt { color: #9aa0a6; font-weight: 600; margin: 0; }
	.recs-kv dd { margin: 0; color: #bdc1c6; }
	.rec-card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.rec-header { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.5rem; }
	.rec-priority { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.05em; }
	.rec-category { font-size: 0.72rem; color: #8ab4f8; background: #111827; padding: 0.15rem 0.4rem; border-radius: 4px; }
	.rec-title { font-size: 0.95rem; }
	.rec-desc { font-size: 0.88rem; color: #bdc1c6; line-height: 1.5; margin: 0 0 0.5rem; }
	.rec-impl { margin-bottom: 0.5rem; }
	.rec-impl strong { font-size: 0.82rem; color: #9aa0a6; }
	.rec-code { background: #0f1114; border: 1px solid #2a2f38; border-radius: 6px; padding: 0.5rem 0.75rem; font-size: 0.82rem; white-space: pre-wrap; margin: 0.25rem 0 0; color: #e8eaed; overflow-x: auto; }
	.rec-impact { font-size: 0.85rem; color: #81c995; margin: 0; }
	.report-actions { margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #2a2f38; }
	.report-actions h3 { margin: 0 0 0.5rem; }
	.report-buttons { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.prompt-suggestions { margin-top: 1.5rem; }
	.suggestion-block { margin-bottom: 1rem; }
	.suggestion-block strong { font-size: 0.88rem; display: block; margin-bottom: 0.25rem; }

	@media (max-width: 800px) { .playback-layout { flex-direction: column; } .playback-sidebar { width: 100%; max-height: none; } }

	/* Node Health tab */
	.nh-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(9.2rem, 1fr)); gap: 0.65rem; margin-bottom: 1.25rem; }
	.nh-stat { background: #1a1d23; border: 1px solid #2a2f38; border-radius: 8px; padding: 0.75rem 1rem; text-align: center; min-width: 7rem; }
	.nh-stat-value { display: block; font-size: 1.4rem; font-weight: 700; color: #8ab4f8; }
	.nh-stat-label { display: block; font-size: 0.75rem; color: #9aa0a6; margin-top: 0.2rem; }
	.nh-issues { list-style: none; padding: 0; margin: 0; }
	.nh-issue { padding: 0.35rem 0; color: #f28b82; font-size: 0.88rem; border-bottom: 1px solid #2a2f38; }
	.nh-issue:last-child { border-bottom: none; }
	.nh-ok { color: #81c995; font-size: 0.88rem; }
	.nh-table td { font-size: 0.82rem; vertical-align: middle; }
	.nh-badge { display: inline-block; padding: 0.2rem 0.52rem; border-radius: 999px; font-size: 0.78rem; border: 1px solid transparent; }
	.nh-ok { background: #1a3a1a; color: #81c995; }
	.nh-skipped { background: #2a2f38; color: #9aa0a6; }
	.nh-warn { background: #3d2e00; color: #f6b93b; }
	.nh-error { background: #3c1111; color: #f28b82; }
	.nh-mood { background: #131926; border-color: #2c3442; font-weight: 700; }
	.nh-memory-entry { margin-bottom: 0.75rem; padding: 0.6rem 0.75rem; background: #1a1d23; border: 1px solid #2a2f38; border-radius: 6px; }
	.nh-memory-turn { font-weight: 600; color: #8ab4f8; font-size: 0.85rem; }
	.nh-memory-words { font-size: 0.75rem; color: #9aa0a6; margin-left: 0.4rem; }
	.nh-memory-text { margin: 0.3rem 0 0; font-size: 0.85rem; color: #e8eaed; line-height: 1.5; }
	:global([data-theme="light"]) .mode-toggle { border-color: #d9dde2; }
	:global([data-theme="light"]) .mode-btn { background: #f7f9fb; color: #5a6472; border-right-color: #d9dde2; }
	:global([data-theme="light"]) .mode-btn:hover { color: #1f2937; background: #eef2f7; }
	:global([data-theme="light"]) .tab-hint { color: #7a8390; }
	:global([data-theme="light"]) .tab-btn { background: #f7f9fb; border-color: #d9dde2; color: #5a6472; }
	:global([data-theme="light"]) .tab-btn:hover { color: #1f2937; background: #eef2f7; border-color: #cdd4de; }
	:global([data-theme="light"]) .mood-chip { color: #334155; background: #f3f7fb; border-color: #d8e3ef; }
	:global([data-theme="light"]) .eval-section { background: #fafbfd; border-color: #dfe3e8; }
	:global([data-theme="light"]) .nh-mood { background: #eef5ff; border-color: #d4e4fb; }
</style>
