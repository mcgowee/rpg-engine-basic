<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { SvelteSet } from 'svelte/reactivity';
	import { goto } from '$app/navigation';
	import Icon from '$lib/components/Icon.svelte';
	import { coverImagePosition } from '$lib/coverDisplay';
	import type { CharEntry, MoodAxis, PortraitRule, ProgressionConfig } from '$lib/characterTypes';
	import { charEntriesFromStoryCharacters } from '$lib/characterTypes';

	type Props = {
		mode: 'create' | 'edit';
		storyId?: number;
	};

	let { mode, storyId }: Props = $props();

	let activeTab = $state<'basics' | 'subgraph' | 'shared' | 'characters' | 'gallery' | 'locations' | 'quest'>('basics');
	let loadDone = $state(false);
	let saving = $state(false);
	let errors = $state<string[]>([]);

	// Basics
	let title = $state('');
	let description = $state('');
	let genre = $state('');
	let tone = $state('');
	let nsfwRating = $state('none');
	let opening = $state('');
	let subgraphName = $state('narrator_chat_lite');
	let notes = $state('');
	let coverImage = $state('');
	let coverCacheBust = $state('');
	let generatingCover = $state(false);
	let coverError = $state('');
	let coverStyle = $state('cinematic');
	let coverPrompt = $state('');
	let buildingCoverPrompt = $state(false);
	let coverStyles = $state<{ key: string; description: string }[]>([]);
	let coverLoadFailed = $state(false);
	let genreCoverLoadFailed = $state(false);
	type StoryImage = { filename: string; image_id?: number | null; prompt?: string; created_at?: string };
	/** Legacy field — preserved on load/save; use Gallery tab for new scene art */
	let storyImages = $state<StoryImage[]>([]);

	// Scene gallery
	type SceneGalleryItem = {
		id: string;
		url: string;
		tags: string[];
		trigger: string;
		priority: number;
		one_time: boolean;
		caption: string;
		style: string;
		prompt: string;
	};
	let sceneGallery = $state<SceneGalleryItem[]>([]);
	let generatingGalleryImage = $state('');
	let galleryImageError = $state('');

	// Map / quest locations
	type MapLocation = {
		key: string;
		name: string;
		narrator_hint: string;
		opening_text: string;
		characters: string[];
		task: string;
		task_criteria: string;
		min_turns: number;
	};
	let mapLocations = $state<MapLocation[]>([]);
	let mapStart = $state('');
	let mapOrder = $state<string[]>([]);
	let existingSceneImages = $state<{ url: string; filename: string; type: string }[]>([]);

	async function loadExistingImages() {
		if (!storyId) return;
		try {
			const r = await fetch(`/api/ai/list-scene-images?story_id=${storyId}`, { credentials: 'include' });
			if (r.ok) {
				const j = await r.json();
				existingSceneImages = Array.isArray(j.images) ? j.images : [];
			}
		} catch { /* ignore */ }
	}

	async function generateGalleryImage(idx: number) {
		const item = sceneGallery[idx];
		if (!item || !storyId || generatingGalleryImage) return;
		if (!item.prompt.trim()) {
			galleryImageError = 'Enter a ComfyUI prompt first';
			return;
		}
		generatingGalleryImage = item.id;
		galleryImageError = '';
		try {
			const r = await fetch('/api/ai/generate-scene', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					scene_text: item.prompt,
					prompt: item.prompt,
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.url) {
				item.url = j.url;
				sceneGallery = [...sceneGallery];
			} else {
				galleryImageError = j.error ?? 'Generation failed';
			}
		} catch {
			galleryImageError = 'Network error';
		} finally {
			generatingGalleryImage = '';
		}
	}

	async function buildGalleryPrompt(idx: number) {
		const item = sceneGallery[idx];
		if (!item || !storyId) return;
		galleryImageError = '';
		try {
			const r = await fetch('/api/ai/build-gallery-item', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					scene_id: item.id,
					tags: item.tags,
					style: item.style || 'cinematic',
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok) {
				if (j.tags && Array.isArray(j.tags)) item.tags = j.tags;
				if (j.trigger) item.trigger = j.trigger;
				if (j.caption) item.caption = j.caption;
				if (j.prompt) item.prompt = j.prompt;
				sceneGallery = [...sceneGallery];
			} else {
				galleryImageError = j.error ?? 'Build failed';
			}
		} catch {
			galleryImageError = 'Network error';
		}
	}
	let brokenPortraits = new SvelteSet<string>();

	// Shared content
	let narratorPrompt = $state('You are the narrator for a text adventure. Describe scenes in second person. End each beat with: What do you do?');
	let narratorModel = $state('default');
	let playerName = $state('Adventurer');
	let playerBackground = $state('');

	// Characters
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
			const entry: Record<string, unknown> = { prompt: c.prompt, first_line: c.first_line, model: c.model, moods: c.moods };
			const portrait = (c.portrait ?? '').split('?')[0]; // strip cache buster
			if (portrait) entry.portrait = portrait;
			if (c.portraits && Object.keys(c.portraits).length > 0) entry.portraits = c.portraits;
			if (c.portrait_rules && c.portrait_rules.length > 0) entry.portrait_rules = c.portrait_rules;
			if (c.face_ref && Object.keys(c.face_ref).length > 0) entry.face_ref = c.face_ref;
			const fed = (c.face_extra_details ?? '').trim();
			if (fed) entry.face_extra_details = fed;
			if (c.progression && c.progression.stages.length > 0) entry.progression = c.progression;
			out[k] = entry;
		}
		return out;
	}

	// AI
	let concept = $state('');
	let generating = $state(false);
	let genError = $state('');
	let genOk = $state('');

	// Improve / Instruct
	let improvingField = $state('');
	let instructingField = $state('');
	let instructInput = $state('');

	// Suggest
	type TextSuggestion = { text: string };
	type AxisSuggestion = { axis: string; low: string; high: string };
	let suggestingField = $state('');
	let suggestions = $state<(TextSuggestion | AxisSuggestion)[]>([]);
	let suggestExtra = $state<Record<string, string>>({});

	async function fetchSuggestions(field: string, extra?: Record<string, string>, current?: string) {
		suggestingField = field;
		suggestions = [];
		suggestExtra = extra ?? {};
		try {
			const r = await fetch('/api/ai/suggest', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					field,
					context: { ...buildContext(), ...extra },
					current: current ?? '',
					count: 5,
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && Array.isArray(j.suggestions)) {
				suggestions = j.suggestions;
			}
		} catch { /* ignore */ }
		if (suggestions.length === 0) suggestingField = '';
	}

	function closeSuggest() {
		suggestingField = '';
		suggestions = [];
	}

	// Subgraphs list
	let subgraphs = $state<{ name: string; description: string }[]>([]);
	let mainGraphTemplates = $state<{ id: number; name: string }[]>([]);
	/** Empty string = use story subgraph only; otherwise template id as string */
	let mainGraphTemplateId = $state('');

	// Derived
	let charCount = $derived(characterEntries.length);
	let isAiBusy = $derived(generating || improvingField !== '');
	let hasMoodAxes = $derived(characterEntries.some(c => c.moods.length > 0));

	type SubgraphRec = { name: string; reason: string; match: boolean };
	let subgraphRecs = $derived.by((): SubgraphRec[] => {
		const recs: SubgraphRec[] = [];
		if (charCount === 0) {
			recs.push({
				name: 'narrator_chat_lite',
				match: true,
				reason: 'No characters — narrator + memory, fast turns',
			});
		} else if (hasMoodAxes) {
			recs.push({ name: 'narrator_chat', match: true, reason: 'Characters with mood axes — full pipeline with mood tracking, memory, and condense' });
			recs.push({ name: 'narrator_chat_lite', match: false, reason: 'Faster but skips mood tracking and memory compression' });
		} else {
			recs.push({ name: 'narrator_chat_lite', match: true, reason: 'Characters without mood axes — fast narrator + character dialogue' });
			recs.push({ name: 'narrator_chat', match: false, reason: 'Full pipeline — would track moods, but no axes defined yet' });
		}
		recs.push({ name: 'chat_direct', match: false, reason: 'No narrator — pure character dialogue only' });
		return recs;
	});

	const GENRES = [
		'fantasy', 'sci-fi', 'horror', 'romance', 'mystery', 'thriller',
		'slice-of-life', 'historical', 'supernatural', 'post-apocalyptic',
		'urban-fantasy', 'erotica', 'drama', 'comedy',
	];

	function normalizedGenre(value: string): string {
		return value.trim().toLowerCase();
	}

	function storyCoverSrc(): string {
		if (!coverImage) return '';
		return `/images/covers/${coverImage}${coverCacheBust}`;
	}

	function genreCoverFallbackSrc(): string {
		const g = normalizedGenre(genre);
		return g && GENRES.includes(g) ? `/images/genre-${g}.png` : '';
	}

	function portraitSrc(portrait: string): string {
		return `/images/portraits/${portrait}`;
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

	function portraitErrorKey(idx: number, portrait: string): string {
		return `${idx}:${portrait}`;
	}

	function isPortraitBroken(idx: number, portrait: string): boolean {
		return brokenPortraits.has(portraitErrorKey(idx, portrait));
	}

	function markPortraitBroken(idx: number, portrait: string): void {
		const key = portraitErrorKey(idx, portrait);
		if (brokenPortraits.has(key)) return;
		brokenPortraits.add(key);
	}

	function clearPortraitBroken(idx: number, portrait: string): void {
		const key = portraitErrorKey(idx, portrait);
		if (!brokenPortraits.has(key)) return;
		brokenPortraits.delete(key);
	}

	const NSFW_RATINGS = [
		{ value: 'none', label: 'None — clean, no sexual or graphic content' },
		{ value: 'suggestive', label: 'Suggestive — flirting, innuendo, fade-to-black' },
		{ value: 'mature', label: 'Mature — explicit scenes but not the focus' },
		{ value: 'explicit', label: 'Explicit — sex and graphic content are central' },
		{ value: 'extreme', label: 'Extreme — no limits' },
	];

	onMount(async () => {
		loadCoverStyles();
		loadExistingImages();
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

		try {
			const rt = await fetch('/api/main-graph-templates', { credentials: 'include' });
			if (rt.ok) {
				const data = await rt.json();
				mainGraphTemplates = (Array.isArray(data) ? data : []).map((t: Record<string, unknown>) => ({
					id: Number(t.id),
					name: String(t.name ?? ''),
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
					tone = s.tone ?? '';
					nsfwRating = s.nsfw_rating ?? 'none';
					opening = s.opening ?? '';
					subgraphName = s.subgraph_name ?? 'narrator_chat_lite';
					mainGraphTemplateId =
						s.main_graph_template_id != null && s.main_graph_template_id !== ''
							? String(s.main_graph_template_id)
							: '';
					notes = s.notes ?? '';
					coverImage = s.cover_image ?? '';
					narratorPrompt = s.narrator_prompt ?? '';
					narratorModel = s.narrator_model ?? 'default';
					playerName = s.player_name ?? 'Adventurer';
					playerBackground = s.player_background ?? '';
					if (s.characters && typeof s.characters === 'object' && !Array.isArray(s.characters)) {
						characterEntries = charEntriesFromStoryCharacters(s.characters as Record<string, unknown>);
					}
					storyImages = normalizeStoryImages(s.story_images);
					sceneGallery = Array.isArray(s.scene_gallery) ? s.scene_gallery : [];
					// Load map / quest locations
					if (s.map && typeof s.map === 'object' && !Array.isArray(s.map)) {
						const m = s.map as Record<string, unknown>;
						mapStart = String(m.start ?? '');
						mapOrder = Array.isArray(m.order) ? m.order.map(String) : [];
						const locs = m.locations as Record<string, Record<string, unknown>> | undefined;
						if (locs) {
							mapLocations = Object.entries(locs).map(([k, v]) => ({
								key: k,
								name: String(v.name ?? k),
								narrator_hint: String(v.narrator_hint ?? ''),
								opening_text: String(v.opening_text ?? ''),
								characters: Array.isArray(v.characters) ? v.characters.map(String) : [],
								task: String(v.task ?? ''),
								task_criteria: String(v.task_criteria ?? ''),
								min_turns: Number(v.min_turns ?? 2),
							}));
						}
					}
				}
			} catch { /* ignore */ }
		}

		loadDone = true;
	});

	function buildMapData(): Record<string, unknown> {
		if (mapLocations.length === 0) return {};
		const locs: Record<string, Record<string, unknown>> = {};
		for (const loc of mapLocations) {
			locs[loc.key] = {
				name: loc.name,
				narrator_hint: loc.narrator_hint,
				opening_text: loc.opening_text,
				characters: loc.characters,
				task: loc.task,
				task_criteria: loc.task_criteria,
				min_turns: loc.min_turns,
			};
		}
		const order = mapOrder.length > 0 ? mapOrder : mapLocations.map(l => l.key);
		return {
			start: mapStart || order[0] || '',
			order,
			locations: locs,
		};
	}

	async function save() {
		errors = [];
		if (!title.trim()) { errors = ['Title is required']; return; }
		saving = true;
		try {
			const body: Record<string, unknown> = {
				title: title.trim(),
				description: description.trim(),
				genre,
				tone: tone.trim(),
				nsfw_rating: nsfwRating,
				nsfw_tags: [],
				opening: opening.trim(),
				subgraph_name: subgraphName,
				main_graph_template_id:
					mainGraphTemplateId.trim() === '' ? null : parseInt(mainGraphTemplateId, 10),
				narrator_prompt: narratorPrompt.trim(),
				narrator_model: narratorModel.trim() || 'default',
				player_name: playerName.trim() || 'Adventurer',
				player_background: playerBackground.trim(),
				characters: charactersToDict(),
				story_images: storyImages,
				notes: notes.trim(),
				scene_gallery: sceneGallery,
				map: buildMapData(),
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

	async function loadCoverStyles() {
		try {
			const r = await fetch('/api/ai/cover-styles', { credentials: 'include' });
			if (r.ok) {
				const j = await r.json();
				if (Array.isArray(j.styles)) coverStyles = j.styles;
			}
		} catch { /* ignore */ }
	}

	async function buildCoverPrompt() {
		if (!storyId || buildingCoverPrompt) return;
		buildingCoverPrompt = true;
		coverError = '';
		try {
			const r = await fetch('/api/ai/build-cover-prompt', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ story_id: storyId, style: coverStyle }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.prompt) {
				coverPrompt = j.prompt;
			} else {
				coverError = j.error ?? 'Prompt generation failed';
			}
		} catch {
			coverError = 'Network error';
		} finally {
			buildingCoverPrompt = false;
		}
	}

	async function generateCover() {
		if (!storyId || generatingCover) return;
		generatingCover = true;
		coverError = '';
		try {
			const body: Record<string, unknown> = { story_id: storyId };
			if (coverPrompt.trim()) {
				body.prompt = coverPrompt.trim();
			}
			const r = await fetch('/api/ai/generate-cover', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.cover_image) {
				coverImage = j.cover_image;
				coverCacheBust = '?t=' + Date.now();
				coverLoadFailed = false;
				genreCoverLoadFailed = false;
			} else {
				coverError = j.error ?? 'Cover generation failed';
			}
		} catch {
			coverError = 'Network error';
		} finally {
			generatingCover = false;
		}
	}

	function buildContext(extra?: Record<string, string>): Record<string, string> {
		const ctx: Record<string, string> = {
			title, genre, narrator_prompt: narratorPrompt,
			player_name: playerName, player_background: playerBackground,
		};
		if (extra) Object.assign(ctx, extra);
		return ctx;
	}

	async function improve(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>) {
		const text = getText();
		if (!text.trim()) return;
		improvingField = field;
		try {
			const r = await fetch('/api/ai/improve-text', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ field, text: text.trim(), context: buildContext(extra) }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.text) { setText(j.text); }
		} catch { /* ignore */ }
		improvingField = '';
	}

	async function instruct(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>) {
		const text = getText();
		if (!text.trim() || !instructInput.trim()) return;
		instructingField = field;
		try {
			const r = await fetch('/api/ai/improve-text', {
				method: 'POST', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ field, text: text.trim(), instruction: instructInput.trim(), context: buildContext(extra) }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.text) { setText(j.text); }
		} catch { /* ignore */ }
		instructingField = '';
		instructInput = '';
	}
</script>

{#snippet aiButtons(field: string, getText: () => string, setText: (v: string) => void, extra?: Record<string, string>)}
	{@const tips: Record<string, { improve: string; instruct: string; placeholder: string }> = {
		opening: {
			improve: 'AI rewrites: tighten prose, strengthen atmosphere, keep second person',
			instruct: 'Tell the AI what to change — e.g. "make it more suspenseful" or "add rain"',
			placeholder: 'e.g. make it darker and more mysterious',
		},
		description: {
			improve: 'AI rewrites: punchier, 1-2 sentences, no spoilers',
			instruct: 'Tell the AI what to change — e.g. "emphasize the danger"',
			placeholder: 'e.g. focus on the mystery angle',
		},
		notes: {
			improve: 'AI rewrites: clearer, more helpful, explains what the story demonstrates',
			instruct: 'Tell the AI what to add — e.g. "mention the mood system" or "add tips for new players"',
			placeholder: 'e.g. note which subgraph you recommend and why',
		},
		narrator_prompt: {
			improve: 'AI rewrites: clearer instructions about tone, pacing, and style',
			instruct: 'Tell the AI what to change — e.g. "add a rule about short responses"',
			placeholder: 'e.g. make the narrator more humorous',
		},
		player_background: {
			improve: 'AI rewrites: more concrete and vivid, better context for the narrator',
			instruct: 'Tell the AI what to change — e.g. "make them younger" or "add a fear"',
			placeholder: 'e.g. add a reason they need this job',
		},
		character_prompt: {
			improve: 'AI rewrites: sharper personality, distinct speech patterns and quirks',
			instruct: 'Tell the AI what to change — e.g. "add a secret" or "make them speak in slang"',
			placeholder: 'e.g. give them a nervous habit',
		},
		character_first_line: {
			improve: 'AI rewrites: more natural, in-character, reveals personality instantly',
			instruct: 'Tell the AI what to change — e.g. "make it a question" or "more hostile"',
			placeholder: 'e.g. make it sound more desperate',
		},
	}}
	{@const tip = tips[field] ?? { improve: 'AI improves this text', instruct: 'Tell the AI what to change', placeholder: 'What should change?' }}
	<div class="ai-row">
		<button type="button" class="btn sm" disabled={improvingField === field || !getText().trim()}
			title={tip.improve}
			onclick={() => improve(field, getText, setText, extra)}>
			{improvingField === field ? 'Improving…' : 'Improve'}
		</button>
		{#if instructingField === field}
			<div class="instruct-row" transition:fade={{ duration: 100 }}>
				<input type="text" class="instruct-input" placeholder={tip.placeholder} bind:value={instructInput}
					title={tip.instruct}
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); instruct(field, getText, setText, extra); } }} />
				<button type="button" class="btn sm" disabled={!instructInput.trim()}
					title="Send your instruction to the AI"
					onclick={() => instruct(field, getText, setText, extra)}>Apply</button>
				<button type="button" class="btn sm"
					title="Cancel without changes"
					onclick={() => { instructingField = ''; instructInput = ''; }}>Cancel</button>
			</div>
		{:else}
			<button type="button" class="btn sm" disabled={!getText().trim()}
				title={tip.instruct}
				onclick={() => { instructingField = field; instructInput = ''; }}>
				Instruct
			</button>
		{/if}
	</div>
{/snippet}

{#snippet suggestBtn(field: string, onPick: (s: TextSuggestion | AxisSuggestion) => void, tooltip: string, extra?: Record<string, string>, current?: string)}
	<div class="suggest-wrap">
		<button type="button" class="btn sm suggest-btn"
			title={tooltip}
			disabled={suggestingField === field}
			onclick={() => fetchSuggestions(field, extra, current)}>
			{suggestingField === field ? '...' : '💡'}
		</button>
		{#if suggestingField === field && suggestions.length > 0}
			<div class="suggest-popup" transition:fade={{ duration: 100 }}>
				<div class="suggest-header">
					<strong>Suggestions</strong>
					<button type="button" class="btn sm" onclick={closeSuggest}>✕</button>
				</div>
				<ul class="suggest-list">
					{#each suggestions as s, i (i)}
						<li>
							<button type="button" class="suggest-item" onclick={() => { onPick(s); closeSuggest(); }}>
								{#if 'text' in s}
									{s.text}
								{:else if 'axis' in s}
									<span class="axis-preview">{s.axis}</span>
									<span class="axis-range">{s.low} → {s.high}</span>
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
{/snippet}

<h1>{mode === 'edit' ? 'Edit story' : 'Create story'}</h1>
<p><a href="/stories">← Back to stories</a></p>

{#if !loadDone}
	<p class="muted">Loading…</p>
{:else}
	<div class="ai-generate-block">
		<div class="ai-generate-header">
			<span class="ai-icon">✨</span>
			<div>
				<strong>Start with AI</strong>
				<p class="ai-desc">Describe your story idea and the AI will generate a complete skeleton — title, opening, narrator style, player character, and more. You can then review and edit every field in the tabs below.</p>
			</div>
		</div>
		<div class="ai-generate-form">
			<textarea rows="3" placeholder="e.g. A detective investigates a series of disappearances in a small coastal town. The local lighthouse keeper knows more than they're saying..." bind:value={concept}></textarea>
			<button type="button" class="btn primary" disabled={generating || !concept.trim()} onclick={() => generate()}>
				{#if generating}<span class="spinner"></span> Generating…{:else}Generate Story Skeleton{/if}
			</button>
		</div>
		{#if genError}<p class="err" transition:fade={{ duration: 150 }}>{genError}</p>{/if}
		{#if genOk}<p class="ok" transition:fade={{ duration: 150 }}>{genOk}</p>{/if}
	</div>

	<div class="tabs">
		<button type="button" class:active={activeTab === 'basics'} onclick={() => activeTab = 'basics'}><Icon name="edit" size={14} /> Basics</button>
		<button type="button" class:active={activeTab === 'subgraph'} onclick={() => activeTab = 'subgraph'}><Icon name="git-branch" size={14} /> Subgraph</button>
		<button type="button" class:active={activeTab === 'shared'} onclick={() => activeTab = 'shared'}><Icon name="settings" size={14} /> Shared Content</button>
		<button type="button" class:active={activeTab === 'characters'} onclick={() => activeTab = 'characters'}><Icon name="users" size={14} /> Characters</button>
		<button type="button" class:active={activeTab === 'gallery'} onclick={() => activeTab = 'gallery'}><Icon name="image" size={14} /> Gallery</button>
		<button type="button" class:active={activeTab === 'locations'} onclick={() => activeTab = 'locations'}><Icon name="compass" size={14} /> Locations</button>
		<button type="button" class:active={activeTab === 'quest'} onclick={() => activeTab = 'quest'}><Icon name="zap" size={14} /> Quest</button>
	</div>

	{#if activeTab === 'basics'}
		<div class="tab-content">
			<div class="field">
				<div class="field-head">
					<strong>Title *</strong>
					{@render suggestBtn('title', (s) => { if ('text' in s) title = s.text; }, 'Suggest titles based on your story')}
				</div>
				<input type="text" bind:value={title} />
			</div>

			{#if mode === 'edit'}
				<div class="field">
					<strong>Cover Image</strong>
					<span class="hint">Generated from your story's title, genre, and description.</span>
					{#if coverImage}
						<div class="cover-preview">
							{#if !coverLoadFailed}
								<img
									src={storyCoverSrc()}
									alt="Story cover"
									loading="lazy"
									decoding="async"
									style:object-position={coverImagePosition(coverImage)}
									onerror={() => coverLoadFailed = true}
								/>
							{:else if genreCoverFallbackSrc() && !genreCoverLoadFailed}
								<img
									src={genreCoverFallbackSrc()}
									alt="Genre fallback cover"
									loading="lazy"
									decoding="async"
									class="fallback-img"
									onerror={() => genreCoverLoadFailed = true}
								/>
							{:else}
								<div class="image-placeholder cover-placeholder">
									<Icon name="image" size={20} />
									<span>Cover unavailable</span>
								</div>
							{/if}
						</div>
					{:else}
						<p class="muted" style="font-size:0.85rem">No cover image yet.</p>
					{/if}
					<div class="cover-controls">
						<label class="field" style="margin-bottom:0.5rem">
							<strong style="font-size:0.85rem">Style</strong>
							<select bind:value={coverStyle} style="font-size:0.85rem">
								{#each coverStyles as s (s.key)}
									<option value={s.key}>{s.key}</option>
								{/each}
								{#if coverStyles.length === 0}
									<option value="cinematic">cinematic</option>
								{/if}
							</select>
						</label>
						<div class="cover-btn-row">
							<button type="button" class="btn sm" disabled={buildingCoverPrompt || !storyId}
								onclick={() => buildCoverPrompt()}>
								{#if buildingCoverPrompt}<span class="spinner"></span> Building...{:else}Build Prompt{/if}
							</button>
							<button type="button" class="btn sm primary" disabled={generatingCover || !storyId}
								title="Generate cover image (requires ComfyUI)"
								onclick={() => generateCover()}>
								{#if generatingCover}<span class="spinner"></span> Generating...{:else}🎨 Generate Cover{/if}
							</button>
						</div>
						{#if coverPrompt}
							<textarea rows="3" bind:value={coverPrompt} style="font-size:0.82rem; margin-top:0.4rem"
								placeholder="Edit the prompt before generating..."></textarea>
						{/if}
					</div>
					{#if coverError}<p class="err" style="font-size:0.85rem">{coverError}</p>{/if}
				</div>

			{/if}

			<div class="field">
				<strong>Description</strong>
				<span class="hint">Short catalog pitch — 1-2 sentences that make players want to try it.</span>
				<textarea rows="3" bind:value={description}></textarea>
				{@render aiButtons('description', () => description, (v) => description = v)}
			</div>

			<div class="field">
				<strong>Notes</strong>
				<span class="hint">Optional. Explain what this story demonstrates, tips for players, or design notes.</span>
				<textarea rows="2" bind:value={notes}></textarea>
				{@render aiButtons('notes', () => notes, (v) => notes = v)}
			</div>

			<label class="field field-meta">
				<strong>Genre</strong>
				<select bind:value={genre}>
					<option value="">— select —</option>
					{#each GENRES as g}<option value={g}>{g}</option>{/each}
				</select>
			</label>

			<label class="field field-meta">
				<strong>Tone</strong>
				<span class="hint">Comma-separated descriptors: e.g. "dark, romantic, tense" or "lighthearted, campy, humorous"</span>
				<input type="text" bind:value={tone} placeholder="e.g. dark, romantic, tense" />
			</label>

			<label class="field field-meta">
				<strong>NSFW Rating</strong>
				<select bind:value={nsfwRating}>
					{#each NSFW_RATINGS as r}<option value={r.value}>{r.label}</option>{/each}
				</select>
			</label>


			<div class="field">
				<strong>Opening</strong>
				<span class="hint">Second person, present tense. What the player reads first.</span>
				<textarea rows="4" bind:value={opening}></textarea>
				{@render aiButtons('opening', () => opening, (v) => opening = v)}
			</div>

		</div>
	{/if}

	{#if activeTab === 'subgraph'}
		<div class="tab-content">
			<label class="field">
				<strong>Main graph (optional)</strong>
				<span class="hint">
					Multi-phase flow: each phase uses its own subgraph; the game advances by turns, keywords, or other rules you set in the template. Leave empty to use a single subgraph for the whole story.
				</span>
				<select bind:value={mainGraphTemplateId}>
					<option value="">None — single subgraph below</option>
					{#each mainGraphTemplates as t}
						<option value={String(t.id)}>{t.name}</option>
					{/each}
				</select>
			</label>

			<div class="sg-rec-box">
				<strong class="sg-rec-title">Recommended for your story</strong>
				<p class="sg-rec-desc">Based on {charCount === 0 ? 'no characters defined' : `${charCount} character${charCount === 1 ? '' : 's'}${hasMoodAxes ? ' with mood axes' : ''}`}:</p>
				<ul class="sg-rec-list">
					{#each subgraphRecs as rec (rec.name)}
						<li class:best={rec.match}>
							<button type="button" class="sg-rec-pick" class:active={subgraphName === rec.name}
								onclick={() => subgraphName = rec.name}>
								<code>{rec.name}</code>
								{#if subgraphName === rec.name}<span class="sg-current">current</span>{/if}
								{#if rec.match}<span class="sg-badge">recommended</span>{/if}
							</button>
							<span class="sg-rec-reason">{rec.reason}</span>
						</li>
					{/each}
				</ul>
			</div>

			<label class="field">
				<strong>Subgraph</strong>
				<span class="hint">Or choose any available subgraph manually:</span>
				<select bind:value={subgraphName}>
					{#each subgraphs as sg}
						<option value={sg.name}>
							{sg.name} — {sg.description || 'no description'}
						</option>
					{/each}
				</select>
			</label>
			<p class="hint">Manage subgraphs in the <a href="/graphs">Graph Editor</a>. Learn more in the <a href="/docs/engine">Engine Reference</a>.</p>
		</div>
	{/if}

	{#if activeTab === 'shared'}
		<div class="tab-content">
			<div class="field">
				<strong>Narrator Prompt</strong>
				<span class="hint">System instructions for the narrator LLM: tone, pacing, second person, how to end beats. This shapes the voice of your story.</span>
				<textarea rows="4" bind:value={narratorPrompt}></textarea>
				{@render aiButtons('narrator_prompt', () => narratorPrompt, (v) => narratorPrompt = v)}
			</div>

			<label class="field">
				<strong>Narrator Model</strong>
				<span class="hint">Leave as "default" to use the server's configured model.</span>
				<input type="text" bind:value={narratorModel} placeholder="default" />
			</label>

			<div class="field">
				<div class="field-head">
					<strong>Player Name</strong>
					{@render suggestBtn('player_name', (s) => { if ('text' in s) playerName = s.text; }, 'Suggest names that fit the genre and setting')}
				</div>
				<span class="hint">Who the player is in the story world.</span>
				<input type="text" bind:value={playerName} />
			</div>

			<div class="field">
				<strong>Player Background</strong>
				<span class="hint">Player character history and situation — concrete, playable, gives the narrator context for the story.</span>
				<textarea rows="3" bind:value={playerBackground}></textarea>
				{@render aiButtons('player_background', () => playerBackground, (v) => playerBackground = v)}
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
						{@render aiButtons('character_prompt', () => char.prompt, (v) => char.prompt = v, { character_key: char.key })}
					</div>

					<div class="field">
						<strong>First Line</strong>
						<span class="hint">What they say at the start of the game. Should match their personality.</span>
						<input type="text" bind:value={char.first_line} placeholder="What'll it be?" />
						{@render aiButtons('character_first_line', () => char.first_line, (v) => char.first_line = v, { character_key: char.key, character_prompt: char.prompt })}
					</div>

					{#if mode === 'edit'}
						<div class="field">
							<strong>Image &amp; media</strong>
							<span class="hint">
								Base portraits and expression variants are created on a dedicated page. Saves apply to this story; use
								<strong>Save story</strong> here for prompts and moods.
							</span>
							{#if storyId && char.key.trim()}
								<div class="char-media-row">
									<a
										class="btn sm primary"
										href="/charactermedia/{storyId}/{encodeURIComponent(char.key)}"
									>
										Open image &amp; media editor
									</a>
									<code class="char-media-key">{char.key}</code>
								</div>
							{:else}
								<p class="muted" style="font-size:0.88rem; margin-top:0.35rem">
									Set a character key and save the story before opening the media editor.
								</p>
							{/if}
							{#if char.portrait && !isPortraitBroken(idx, char.portrait)}
								<div class="portrait-preview">
									<img
										src={portraitSrc(char.portrait)}
										alt="{char.key} portrait"
										loading="lazy"
										decoding="async"
										onerror={() => markPortraitBroken(idx, char.portrait ?? '')}
										onload={() => clearPortraitBroken(idx, char.portrait ?? '')}
									/>
								</div>
							{:else if char.portrait}
								<div class="portrait-preview">
									<div class="image-placeholder portrait-placeholder">
										<Icon name="user" size={20} />
										<span>Portrait unavailable</span>
									</div>
								</div>
							{:else}
								<p class="muted" style="font-size:0.88rem; margin-top:0.35rem">No portrait yet.</p>
							{/if}
						</div>
					{/if}

					<div class="field">
						<div class="field-head">
							<strong>Mood Axes</strong>
							{@render suggestBtn(
								'mood_axis_new',
								(s) => { if ('axis' in s) char.moods = [...char.moods, { axis: s.axis, low: s.low, high: s.high, value: 5 }]; },
								'Suggest new mood axes based on this character',
								{ character_key: char.key, character_prompt: char.prompt, existing_axes: char.moods.map(a => a.axis).join(', ') }
							)}
						</div>
						<span class="hint">Each axis is a scale between two emotions. The mood node adjusts these each turn.</span>
						{#each char.moods as axis, ai (ai)}
							<div class="axis-row">
								<input type="text" bind:value={axis.axis} placeholder="axis name" class="axis-input" />
								<input type="text" bind:value={axis.low} placeholder="low label" class="axis-input" />
								<span class="axis-arrow">←→</span>
								<input type="text" bind:value={axis.high} placeholder="high label" class="axis-input" />
								<input type="number" min="1" max="10" bind:value={axis.value} class="axis-value" />
								{@render suggestBtn(
									'mood_axis_refine',
									(s) => { if ('axis' in s) { axis.axis = s.axis; axis.low = s.low; axis.high = s.high; } },
									'Suggest better labels for this axis',
									{ character_key: char.key, character_prompt: char.prompt },
									`${axis.axis}|${axis.low}|${axis.high}`
								)}
								<button type="button" class="btn sm danger" onclick={() => { char.moods = char.moods.filter((_, i) => i !== ai); }}>×</button>
							</div>
						{/each}
						<button type="button" class="btn sm" onclick={() => { char.moods = [...char.moods, { axis: '', low: '', high: '', value: 5 }]; }}>Add axis</button>
					</div>

					<div class="field">
						<div class="field-head">
							<strong>Progression Stages</strong>
							<span class="hint-inline">(optional)</span>
						</div>
						<span class="hint">NPC-driven stage progression. The character advances through stages based on turn count and mood thresholds. Requires narrator_chat_progression subgraph.</span>

						{#if char.progression}
							<div class="progression-editor">
								<div class="prog-field">
									<label>Stages <span class="hint-inline">(comma-separated)</span>
									<input type="text"
										value={char.progression.stages.join(', ')}
										oninput={(e) => {
											if (!char.progression) return;
											char.progression.stages = (e.currentTarget as HTMLInputElement).value.split(',').map(s => s.trim().toLowerCase().replace(/\s+/g, '_')).filter(Boolean);
										}}
										placeholder="meet, chat, flirt, kiss, ..."
									/>
									</label>
								</div>
								<div class="prog-field">
									<label>Min turns per stage <span class="hint-inline">(comma-separated numbers)</span>
									<input type="text"
										value={char.progression.min_turns_per_stage.join(', ')}
										oninput={(e) => {
											if (!char.progression) return;
											char.progression.min_turns_per_stage = (e.currentTarget as HTMLInputElement).value.split(',').map(s => Number(s.trim()) || 1);
										}}
										placeholder="2, 3, 3, 2, ..."
									/>
									</label>
								</div>
								<div class="prog-field">
									<span class="prog-label">Advance criteria <span class="hint-inline">(what the player must do/say to advance past each stage)</span></span>
									{#each char.progression.stages as stageName, si (stageName)}
										{#if si < char.progression.stages.length - 1}
											<div class="criteria-row">
												<span class="criteria-stage">{stageName}</span>
												<input type="text"
													value={char.progression.advance_when[stageName] ?? ''}
													oninput={(e) => {
														if (!char.progression) return;
														char.progression.advance_when = { ...char.progression.advance_when, [stageName]: (e.currentTarget as HTMLInputElement).value };
													}}
													placeholder="What must the player do or say to leave this stage?"
												/>
											</div>
										{/if}
									{/each}
								</div>
								<div class="prog-field">
									<span class="prog-label">Advance thresholds <span class="hint-inline">(fallback — mood axis: minimum value, used if no criteria above)</span></span>
									{#each Object.entries(char.progression.advance_threshold) as [axis, val], ti (axis)}
										<div class="threshold-row">
											<input type="text" value={axis} class="axis-input"
												oninput={(e) => {
													if (!char.progression) return;
													const newKey = (e.currentTarget as HTMLInputElement).value.trim();
													const entries = Object.entries(char.progression.advance_threshold);
													entries[ti] = [newKey, val];
													char.progression.advance_threshold = Object.fromEntries(entries);
												}}
												placeholder="mood axis"
											/>
											<span class="axis-arrow">&ge;</span>
											<input type="number" min="1" max="10" value={val} class="axis-value"
												oninput={(e) => {
													if (!char.progression) return;
													char.progression.advance_threshold[axis] = Number((e.currentTarget as HTMLInputElement).value) || 5;
												}}
											/>
											<button type="button" class="btn sm danger" onclick={() => {
												if (!char.progression) return;
												const next = { ...char.progression.advance_threshold };
												delete next[axis];
												char.progression.advance_threshold = next;
											}}>&times;</button>
										</div>
									{/each}
									<button type="button" class="btn sm" onclick={() => {
										if (!char.progression) return;
										char.progression.advance_threshold = { ...char.progression.advance_threshold, '': 5 };
									}}>Add threshold</button>
								</div>
								<div class="prog-field">
									<span class="prog-label">NPC directives <span class="hint-inline">(what the NPC should do/feel at each stage — overrides engine defaults)</span></span>
									{#each char.progression.stages as stageName (stageName)}
										<div class="criteria-row">
											<span class="criteria-stage">{stageName}</span>
											<input type="text"
												value={char.progression.stage_directives[stageName] ?? ''}
												oninput={(e) => {
													if (!char.progression) return;
													char.progression.stage_directives = { ...char.progression.stage_directives, [stageName]: (e.currentTarget as HTMLInputElement).value };
												}}
												placeholder="How the NPC should behave in this stage"
											/>
										</div>
									{/each}
								</div>
								<div class="prog-field">
									<span class="prog-label">Narrator hints <span class="hint-inline">(scene atmosphere the narrator should create at each stage — overrides engine defaults)</span></span>
									{#each char.progression.stages as stageName (stageName)}
										<div class="criteria-row">
											<span class="criteria-stage">{stageName}</span>
											<input type="text"
												value={char.progression.stage_narrator_hints[stageName] ?? ''}
												oninput={(e) => {
													if (!char.progression) return;
													char.progression.stage_narrator_hints = { ...char.progression.stage_narrator_hints, [stageName]: (e.currentTarget as HTMLInputElement).value };
												}}
												placeholder="Scene atmosphere / pacing hint for the narrator"
											/>
										</div>
									{/each}
								</div>
								<div class="prog-row">
									<label class="prog-check">
										<input type="checkbox" bind:checked={char.progression.initiator} />
										NPC initiates (drives the interaction forward)
									</label>
								</div>
								<div class="prog-field">
									<label>Style
									<input type="text" bind:value={char.progression.style} placeholder="e.g. warm but direct, teasing, professional" />
									</label>
								</div>
								<div class="prog-field">
									<label>Pace
									<input type="text" bind:value={char.progression.pace} placeholder="e.g. slow_burn, patient, aggressive" />
									</label>
								</div>
								<button type="button" class="btn sm danger" onclick={() => { char.progression = undefined; }}>Remove progression</button>
							</div>
						{:else}
							<button type="button" class="btn sm" onclick={() => {
								char.progression = {
									stages: ['meet', 'chat', 'connect', 'deepen', 'resolve'],
									min_turns_per_stage: [1, 2, 2, 2, 2],
									advance_when: {},
									advance_threshold: {},
									stage_directives: {},
									stage_narrator_hints: {},
									initiator: true,
									style: '',
									pace: '',
								};
							}}>Enable progression</button>
						{/if}
					</div>

					<button type="button" class="btn sm danger" onclick={() => removeCharacter(idx)}>Remove character</button>
				</fieldset>
			{/each}

			<button type="button" class="btn" onclick={() => addCharacter()}>Add character</button>
		</div>
	{/if}

	{#if activeTab === 'gallery'}
		<div class="tab-content">
			<h2 class="sub">Scene Gallery</h2>
			<p class="hint">Pre-made images triggered during play by tags and keywords. Displayed in the play sidebar. Save the story after adding images.</p>

			{#if galleryImageError}<p class="err">{galleryImageError}</p>{/if}

			{#each sceneGallery as item, idx (item.id || idx)}
				<div class="gallery-card">
					<div class="gallery-card-header">
						<strong>{item.id || `Scene ${idx + 1}`}</strong>
						<button type="button" class="btn sm danger" onclick={() => {
							sceneGallery = sceneGallery.filter((_, i) => i !== idx);
						}}>Remove</button>
					</div>

					<div class="gallery-card-body">
						{#if item.url}
							<div class="gallery-preview">
								<img src={item.url.startsWith('/') ? item.url : `/images/scenes/${item.url}`}
									alt={item.caption || item.id} class="gallery-thumb" />
							</div>
						{/if}

						<div class="gallery-fields">
							<label class="field-sm">
								<span>ID</span>
								<input type="text" bind:value={item.id} placeholder="kitchen_morning" />
							</label>
							<label class="field-sm">
								<span>Tags (comma-separated)</span>
								<input type="text" value={item.tags.join(', ')}
									oninput={(e) => {
										item.tags = (e.currentTarget as HTMLInputElement).value.split(',').map(t => t.trim()).filter(Boolean);
										sceneGallery = [...sceneGallery];
									}}
									placeholder="kitchen, morning, cooking" />
							</label>
							<label class="field-sm">
								<span>Trigger phrase</span>
								<input type="text" bind:value={item.trigger} placeholder="cooking breakfast together" />
							</label>
							<label class="field-sm">
								<span>Caption</span>
								<input type="text" bind:value={item.caption} placeholder="Morning light fills the kitchen" />
							</label>
							<div class="gallery-card-options">
								<label class="field-sm inline">
									<span>Priority</span>
									<input type="number" bind:value={item.priority} min="0" max="10" style="width:4rem" />
								</label>
								<label class="tag-check">
									<input type="checkbox" bind:checked={item.one_time} />
									One-time (milestone)
								</label>
							</div>
						</div>
					</div>

					<div class="gallery-prompt-section">
						<label class="field-sm">
							<span>Style</span>
							<select bind:value={item.style} style="font-size:0.85rem">
								{#each coverStyles as s (s.key)}
									<option value={s.key}>{s.key}</option>
								{/each}
								{#if coverStyles.length === 0}
									<option value="cinematic">cinematic</option>
								{/if}
							</select>
						</label>
						<label class="field-sm">
							<span>Image prompt</span>
							<textarea rows="2" bind:value={item.prompt} placeholder="Cozy apartment kitchen, morning sunlight..."></textarea>
						</label>
						<div class="gallery-btn-row">
							<button type="button" class="btn sm" onclick={() => buildGalleryPrompt(idx)}>
								Build Prompt
							</button>
							<button type="button" class="btn sm primary"
								disabled={generatingGalleryImage === item.id || !item.prompt.trim()}
								onclick={() => generateGalleryImage(idx)}>
								{#if generatingGalleryImage === item.id}<span class="spinner"></span> Generating...{:else}🎨 Generate{/if}
							</button>
						</div>
					</div>

					<div class="field-sm">
						<span>Image</span>
						<div class="image-url-row">
							<select style="flex:1; font-size:0.82rem" value={item.url}
								onchange={(e) => {
									item.url = (e.currentTarget as HTMLSelectElement).value;
									sceneGallery = [...sceneGallery];
								}}>
								<option value="">— select existing image —</option>
								{#each existingSceneImages as img (img.url)}
									<option value={img.url}>{img.filename}</option>
								{/each}
							</select>
							<span class="hint" style="display:inline; margin:0 0.3rem">or</span>
							<input type="text" bind:value={item.url} placeholder="paste URL" style="flex:1; font-size:0.82rem" />
						</div>
					</div>
				</div>
			{/each}

			<button type="button" class="btn" onclick={() => {
				sceneGallery = [...sceneGallery, {
					id: `scene_${sceneGallery.length + 1}`,
					url: '',
					tags: [],
					trigger: '',
					priority: 5,
					one_time: false,
					caption: '',
					style: 'cinematic',
					prompt: '',
				}];
			}}>+ Add Scene Image</button>
		</div>
	{/if}

	{#if activeTab === 'locations'}
		<div class="tab-content">
			<h2 class="sub">Locations</h2>
			<p class="hint">Define the locations in your quest world. Assign characters from the Characters tab to each location.</p>

			{#if mapLocations.length === 0}
				<p class="muted">No locations yet. Add one to start building your quest map.</p>
			{/if}

			{#each mapLocations as loc, idx (idx)}
				<div class="location-card">
					<div class="location-card-header">
						<strong>{loc.name || `Location ${idx + 1}`}</strong>
						<button type="button" class="btn sm danger" onclick={() => {
							const key = mapLocations[idx].key;
							mapLocations = mapLocations.filter((_, i) => i !== idx);
							mapOrder = mapOrder.filter(k => k !== key);
						}}>Remove</button>
					</div>

					<label class="field-sm">
						<span>Key <span class="hint-inline">(slug, no spaces)</span></span>
						<input type="text" bind:value={loc.key} placeholder="tavern"
							oninput={(e) => {
								loc.key = (e.currentTarget as HTMLInputElement).value.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
							}} />
					</label>

					<label class="field-sm">
						<span>Name</span>
						<input type="text" bind:value={loc.name} placeholder="The Rusted Nail"
							oninput={(e) => {
								if (!loc.key) {
									loc.key = (e.currentTarget as HTMLInputElement).value.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
								}
							}} />
					</label>

					<label class="field-sm">
						<span>Narrator hint <span class="hint-inline">(atmosphere for the narrator)</span></span>
						<textarea rows="2" bind:value={loc.narrator_hint} placeholder="A dim, smoky tavern at a crossroads..."></textarea>
					</label>

					<label class="field-sm">
						<span>Opening text <span class="hint-inline">(optional, shown on first arrival)</span></span>
						<textarea rows="2" bind:value={loc.opening_text} placeholder="You push through the heavy oak door..."></textarea>
					</label>

					<div class="field-sm">
						<span class="prog-label">Characters at this location</span>
						{#if characterEntries.filter(c => c.key.trim()).length === 0}
							<p class="muted">Define characters in the Characters tab first.</p>
						{:else}
							<div class="char-checkboxes">
								{#each characterEntries.filter(c => c.key.trim()) as char (char.key)}
									<label class="tag-check">
										<input type="checkbox"
											checked={loc.characters.includes(char.key)}
											onchange={() => {
												if (loc.characters.includes(char.key)) {
													loc.characters = loc.characters.filter(k => k !== char.key);
												} else {
													loc.characters = [...loc.characters, char.key];
												}
											}} />
										{char.key}
									</label>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			{/each}

			<button type="button" class="btn" onclick={() => {
				mapLocations = [...mapLocations, {
					key: '',
					name: '',
					narrator_hint: '',
					opening_text: '',
					characters: [],
					task: '',
					task_criteria: '',
					min_turns: 2,
				}];
			}}>+ Add Location</button>
		</div>
	{/if}

	{#if activeTab === 'quest'}
		<div class="tab-content">
			<h2 class="sub">Quest Sequence</h2>
			<p class="hint">Define the order players visit locations and the task at each stop. Requires the <code>narrator_chat_quest</code> subgraph.</p>

			{#if mapLocations.length === 0}
				<p class="muted">Add locations in the Locations tab first.</p>
			{:else}
				<div class="field">
					<label><strong>Start location</strong>
					<select bind:value={mapStart}>
						<option value="">— select —</option>
						{#each mapLocations as loc (loc.key)}
							{#if loc.key}
								<option value={loc.key}>{loc.name || loc.key}</option>
							{/if}
						{/each}
					</select>
					</label>
				</div>

				<h3 class="sub">Location Order & Tasks</h3>
				<p class="hint">Arrange locations in the order the player visits them. Define a visible task and hidden completion criteria for each.</p>

				{#if mapOrder.length === 0 && mapLocations.length > 0}
					<button type="button" class="btn sm" onclick={() => {
						mapOrder = mapLocations.filter(l => l.key).map(l => l.key);
						if (!mapStart && mapOrder.length > 0) mapStart = mapOrder[0];
					}}>Auto-fill order from locations</button>
				{/if}

				{#each mapOrder as locKey, idx (locKey)}
					{@const loc = mapLocations.find(l => l.key === locKey)}
					{#if loc}
						<div class="quest-step-card">
							<div class="quest-step-header">
								<span class="quest-step-num">{idx + 1}</span>
								<strong>{loc.name || loc.key}</strong>
								<div class="quest-step-actions">
									{#if idx > 0}
										<button type="button" class="btn sm" title="Move up" onclick={() => {
											const arr = [...mapOrder];
											[arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
											mapOrder = arr;
										}}>↑</button>
									{/if}
									{#if idx < mapOrder.length - 1}
										<button type="button" class="btn sm" title="Move down" onclick={() => {
											const arr = [...mapOrder];
											[arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]];
											mapOrder = arr;
										}}>↓</button>
									{/if}
									<button type="button" class="btn sm danger" title="Remove from sequence" onclick={() => {
										mapOrder = mapOrder.filter((_, i) => i !== idx);
									}}>×</button>
								</div>
							</div>

							<label class="field-sm">
								<span>Task <span class="hint-inline">(visible to the player as their objective)</span></span>
								<input type="text" bind:value={loc.task} placeholder="Retrieve the stolen ledger from the back storeroom" />
							</label>

							<label class="field-sm">
								<span>Task criteria <span class="hint-inline">(hidden — how the AI judges completion)</span></span>
								<textarea rows="2" bind:value={loc.task_criteria} placeholder="The player goes to the storeroom and finds or returns the ledger"></textarea>
							</label>

							<label class="field-sm inline">
								<span>Min turns</span>
								<input type="number" bind:value={loc.min_turns} min="1" max="20" style="width:4rem" />
							</label>
						</div>
					{/if}
				{/each}

				{@const unusedLocs = mapLocations.filter(l => l.key && !mapOrder.includes(l.key))}
				{#if unusedLocs.length > 0}
					<div class="field">
						<label><strong>Add location to sequence</strong>
						<select onchange={(e) => {
							const val = (e.currentTarget as HTMLSelectElement).value;
							if (val) {
								mapOrder = [...mapOrder, val];
								(e.currentTarget as HTMLSelectElement).value = '';
							}
						}}>
							<option value="">— select —</option>
							{#each unusedLocs as loc (loc.key)}
								<option value={loc.key}>{loc.name || loc.key}</option>
							{/each}
						</select>
						</label>
					</div>
				{/if}
			{/if}
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
	.tabs { display: flex; gap: 0.35rem; margin-bottom: 1rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.4rem; flex-wrap: wrap; }
	.tabs button { padding: 0.45rem 0.85rem; border: 1px solid #2a2f38; background: #1a1d23; color: #9aa0a6; cursor: pointer; font: inherit; border-radius: 8px; transition: color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease; }
	.tabs button:hover { color: #e8eaed; border-color: #46505e; background: #20242c; }
	.tabs button.active { background: #1a73e8; color: #fff; border-color: #1a73e8; font-weight: 600; }
	.tab-content { max-width: 700px; }
	.char-media-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.65rem; margin: 0.5rem 0 0.35rem; }
	.char-media-row .btn { text-decoration: none; display: inline-block; text-align: center; }
	.char-media-key { font-size: 0.82rem; background: #2a2f38; padding: 0.2rem 0.45rem; border-radius: 4px; }
	.field { display: block; margin-bottom: 1rem; }
	.field-meta { border: 1px solid #2a2f38; border-radius: 10px; padding: 0.75rem 0.85rem; background: #161a20; }
	.field strong { display: block; margin-bottom: 0.25rem; }
	.field input, .field textarea, .field select { width: 100%; box-sizing: border-box; }
	.hint { display: block; font-size: 0.82rem; color: #9aa0a6; margin-bottom: 0.3rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; margin-top: 0.3rem; }
	.ai-generate-block { border: 1px solid #1a73e8; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; background: #111827; }
	.ai-generate-header { display: flex; gap: 0.75rem; margin-bottom: 0.75rem; }
	.ai-generate-header .ai-icon { font-size: 1.5rem; flex-shrink: 0; margin-top: 0.1rem; }
	.ai-generate-header strong { font-size: 1.05rem; display: block; margin-bottom: 0.2rem; }
	.ai-desc { margin: 0; font-size: 0.85rem; color: #9aa0a6; line-height: 1.5; }
	.ai-generate-form { display: flex; flex-direction: column; gap: 0.5rem; }
	.ai-generate-form textarea { width: 100%; box-sizing: border-box; min-height: 3.5rem; }
	.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2f38; }
	.err { color: #f28b82; margin: 0.25rem 0; }
	.err-box { margin-top: 1rem; }
	.ok { color: #81c995; margin: 0.25rem 0; }
	.muted { color: #9aa0a6; }
	.char-card { border: 1px solid #2a2f38; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; background: #1a1d23; }
	.axis-row { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
	.axis-input { width: 6rem; }
	.axis-value { width: 3.5rem; }
	.axis-arrow { color: #9aa0a6; font-size: 0.85rem; }
	.progression-editor { margin-top: 0.5rem; padding: 0.6rem; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 8px; }
	.prog-field { margin-bottom: 0.5rem; }
	.prog-field label, .prog-field .prog-label { display: block; font-size: 0.82rem; color: #9aa0a6; margin-bottom: 0.2rem; }
	.prog-row { margin-bottom: 0.5rem; }
	.prog-check { font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; cursor: pointer; }
	.threshold-row { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.3rem; }
	.criteria-row { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.35rem; }
	.criteria-stage { min-width: 5.5rem; font-size: 0.82rem; color: #c58af9; font-weight: 600; text-transform: capitalize; }
	.criteria-row input { flex: 1; }
	.hint-inline { font-size: 0.78rem; color: #5f6368; font-weight: normal; }
	.gallery-card { border: 1px solid #2a2f38; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem; background: #1a1d23; }
	.gallery-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
	.gallery-card-body { display: flex; gap: 0.75rem; margin-bottom: 0.5rem; }
	.gallery-preview { flex-shrink: 0; }
	.gallery-fields { flex: 1; min-width: 0; }
	.gallery-thumb { max-width: 180px; height: auto; border-radius: 6px; border: 1px solid #2a2f38; }
	.gallery-card-options { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
	.gallery-prompt-section { border-top: 1px solid #2a2f38; padding-top: 0.5rem; margin-top: 0.3rem; }
	.gallery-btn-row { display: flex; gap: 0.5rem; margin-top: 0.3rem; }
	.image-url-row { display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap; }
	.field-sm { display: block; margin-bottom: 0.4rem; }
	.field-sm span { display: block; font-size: 0.78rem; color: #9aa0a6; margin-bottom: 0.15rem; }
	.field-sm input, .field-sm textarea { width: 100%; box-sizing: border-box; font-size: 0.85rem; }
	.field-sm.inline { display: inline-flex; align-items: center; gap: 0.3rem; }
	.field-sm.inline span { display: inline; margin-bottom: 0; }
	.cover-controls { margin-top: 0.5rem; }
	.cover-btn-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.cover-preview {
		margin: 0.5rem 0;
		width: min(100%, 460px);
		aspect-ratio: 16 / 6.5;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid #2a2f38;
		background: #161a20;
	}
	.cover-preview img { width: 100%; height: 100%; object-fit: cover; object-position: center; display: block; }
	.cover-preview img.fallback-img { opacity: 0.95; }
	.portrait-preview {
		margin: 0.5rem 0;
		width: 120px;
		aspect-ratio: 2 / 3;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid #2a2f38;
		background: #161a20;
	}
	.portrait-preview img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.image-placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.35rem;
		color: #7f8896;
		font-size: 0.76rem;
		background: linear-gradient(180deg, #1b2028 0%, #171b22 100%);
	}
	.cover-placeholder { font-size: 0.8rem; }
	.portrait-placeholder { font-size: 0.72rem; }
	.danger { color: #f28b82; border-color: #c5221f; }
	.sg-rec-box { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 1.25rem; background: #1a1d23; }
	.sg-rec-title { font-size: 0.95rem; display: block; margin-bottom: 0.2rem; }
	.sg-rec-desc { font-size: 0.82rem; color: #9aa0a6; margin: 0 0 0.65rem; }
	.sg-rec-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
	.sg-rec-pick { display: block; width: 100%; text-align: left; background: #13151a; border: 1px solid #2a2f38; border-radius: 6px; padding: 0.5rem 0.75rem; color: #e8eaed; font: inherit; cursor: pointer; }
	.sg-rec-pick:hover { border-color: #5f6368; }
	.sg-rec-pick.active { border-color: #1a73e8; }
	.sg-rec-pick code { font-size: 0.88rem; color: #8ab4f8; }
	.sg-current { font-size: 0.7rem; background: #1a73e8; color: #fff; padding: 0.1rem 0.35rem; border-radius: 3px; margin-left: 0.4rem; vertical-align: middle; }
	.sg-badge { font-size: 0.7rem; background: #1a3a1a; color: #81c995; padding: 0.1rem 0.35rem; border-radius: 3px; margin-left: 0.4rem; vertical-align: middle; }
	.sg-rec-reason { display: block; font-size: 0.8rem; color: #9aa0a6; margin-top: 0.2rem; padding-left: 0.75rem; }
	.field-head { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.25rem; }
	.field-head strong { margin-bottom: 0; }
	.ai-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; margin-top: 0.35rem; }
	.instruct-row { display: flex; align-items: center; gap: 0.35rem; flex: 1; min-width: 14rem; }
	.instruct-input { flex: 1; font-size: 0.85rem; padding: 0.3rem 0.5rem; }
	.suggest-wrap { position: relative; display: inline-block; }
	.suggest-btn { font-size: 0.9rem; padding: 0.15rem 0.4rem; line-height: 1; min-width: unset; }
	.suggest-popup { position: absolute; top: 100%; left: 0; z-index: 100; min-width: 16rem; max-width: 22rem; background: #1a1d23; border: 1px solid #3c4043; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); margin-top: 0.25rem; }
	.suggest-header { display: flex; align-items: center; justify-content: space-between; padding: 0.4rem 0.65rem; border-bottom: 1px solid #2a2f38; }
	.suggest-header strong { font-size: 0.82rem; color: #9aa0a6; }
	.suggest-list { list-style: none; margin: 0; padding: 0.25rem 0; }
	.suggest-item { display: block; width: 100%; text-align: left; background: none; border: none; color: #e8eaed; padding: 0.45rem 0.65rem; font: inherit; font-size: 0.88rem; cursor: pointer; line-height: 1.4; }
	.suggest-item:hover { background: #2a2f38; }
	.axis-preview { font-weight: 600; margin-right: 0.35rem; }
	.axis-range { color: #9aa0a6; font-size: 0.82rem; }
	.tag-check { display: flex; align-items: center; gap: 0.4rem; font-size: 0.88rem; color: #e8eaed; cursor: pointer; }
	.tag-check input[type="checkbox"] { accent-color: #1a73e8; margin: 0; }
	:global([data-theme="light"]) .tabs { border-bottom-color: #dfe3e7; }
	:global([data-theme="light"]) .tabs button { border-color: #d9dde2; background: #f7f8fa; color: #5a6472; }
	:global([data-theme="light"]) .tabs button:hover { color: #1f2937; border-color: #cdd3db; background: #f2f5f8; }
	:global([data-theme="light"]) .tabs button.active { color: #fff; background: #1a73e8; border-color: #1a73e8; }
	:global([data-theme="light"]) .field-meta { border-color: #dfe3e7; background: #fafbfc; }
	/* Location & Quest tabs */
	.location-card { border: 1px solid #2a2f38; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem; background: #1a1d23; }
	.location-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
	.char-checkboxes { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.2rem; }
	.quest-step-card { border: 1px solid #2a2f38; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem; background: #1a1d23; }
	.quest-step-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
	.quest-step-num { display: inline-flex; align-items: center; justify-content: center; width: 1.5rem; height: 1.5rem; border-radius: 50%; background: #c58af9; color: #fff; font-size: 0.75rem; font-weight: 700; flex-shrink: 0; }
	.quest-step-actions { margin-left: auto; display: flex; gap: 0.25rem; }
</style>
