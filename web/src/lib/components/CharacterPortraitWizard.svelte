<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import {
		FACE_REF_OPTIONS_STATIC,
		FACE_REF_FIELD_LABELS,
		FACE_REF_FIELD_ORDER,
		type FaceRefOptionsPayload,
	} from '$lib/faceRefOptions';
	import type { CharEntry, PortraitRule } from '$lib/characterTypes';
	import { charEntryFromStoryPayload, mergeCharEntryFromServer } from '$lib/characterTypes';
	import { suggestPortraitRules, ruleSummary } from '$lib/portraitRulesSuggest';

	type Props = {
		storyId: number;
		character: CharEntry;
		onCharacterChange: (next: CharEntry) => void;
		/** Optional hook after a variant batch (e.g. refresh scene image lists). */
		afterVariantsGenerated?: () => void;
	};

	let { storyId, character, onCharacterChange, afterVariantsGenerated }: Props = $props();

	type WizardStep =
		| 'idle'
		| 'generating_faces'
		| 'pick_base'
		| 'variants'
		| 'generating_variants'
		| 'rules_suggest';
	type FaceCandidate = { index: number; filename: string; url: string };

	let wizardStep = $state<WizardStep>('idle');
	let wizardCandidates = $state<FaceCandidate[]>([]);
	let wizardPickedFace = $state('');
	let wizardVariantResults = $state<
		{ key: string; ok: boolean; url?: string; filename?: string; error?: string }[]
	>([]);
	let wizardError = $state('');
	let wizardVariantOk = $state('');
	let wizardWeight = $state(0.75);

	/** Editable draft after a successful variant batch — optional mood→expression rules */
	let portraitRulesDraft = $state<PortraitRule[]>([]);
	let variantKeysAfterRun = $state<string[]>([]);

	let faceRefOptions = $state<FaceRefOptionsPayload | null>(null);
	let faceRefForm = $state<Record<string, string>>({ ...FACE_REF_OPTIONS_STATIC.defaults });
	let faceRefExtraDetails = $state('');

	const DEFAULT_VARIANTS = [
		{ key: 'happy', prompt: 'happy smiling joyful expression, warm eyes' },
		{ key: 'flirty', prompt: 'flirty playful expression, slight smirk, half-lidded eyes' },
		{ key: 'angry', prompt: 'angry scowling expression, furrowed brows, intense eyes' },
		{ key: 'sad', prompt: 'sad melancholic expression, downcast eyes, subtle frown' },
		{ key: 'neutral', prompt: 'neutral calm expression, relaxed face, steady gaze' },
		{ key: 'surprised', prompt: 'surprised wide-eyed expression, raised eyebrows, open mouth' },
	];
	let wizardVariants = $state(DEFAULT_VARIANTS.map((v) => ({ ...v, enabled: true })));

	/** Cache-bust per variant after single-file regen (same filename on disk). */
	let variantReloadNonce = $state<Record<string, number>>({});
	let variantRegenerating = $state<Record<string, boolean>>({});
	let deleteConfirmKey = $state<string | null>(null);
	let editingVariantKey = $state<string | null>(null);
	let renameDraft = $state('');
	let renameInputEl = $state<HTMLInputElement | null>(null);
	let variantFieldError = $state('');

	let customVariantKeyInput = $state('');
	let customVariantDesc = $state('');
	let customVariantBusy = $state(false);

	const faceRefFieldsSource = $derived(faceRefOptions ?? FACE_REF_OPTIONS_STATIC);

	function isValidVariantKey(key: string): boolean {
		return /^[a-zA-Z0-9_]+$/.test(key.trim());
	}

	function referenceFaceFilenameForVariants(): string {
		const w = wizardPickedFace.split('?')[0].trim();
		if (w) return w;
		return (character.portrait ?? '').split('?')[0].trim();
	}

	function variantPortraitUrl(filename: string, vkey: string): string {
		const base = filename.split('?')[0];
		const n = variantReloadNonce[vkey];
		const q = n != null ? `?v=${n}` : '';
		return `/images/portraits/${base}${q}`;
	}

	function defaultVariantPromptForKey(vkey: string): string {
		const def = DEFAULT_VARIANTS.find((d) => d.key === vkey);
		return def?.prompt ?? `${vkey} expression, portrait`;
	}

	function isVariantDefaultPortrait(vfile: string): boolean {
		const pb = (character.portrait ?? '').split('?')[0];
		const fb = vfile.split('?')[0];
		return Boolean(pb && fb && pb === fb);
	}

	async function loadFaceRefOptions() {
		try {
			const r = await fetch('/api/ai/face-ref-options', { credentials: 'include' });
			if (r.ok) {
				const j = (await r.json().catch(() => null)) as FaceRefOptionsPayload | null;
				if (j?.fields && j?.defaults) {
					faceRefOptions = j;
					faceRefForm = { ...j.defaults };
					return;
				}
			}
		} catch {
			/* ignore */
		}
		faceRefOptions = FACE_REF_OPTIONS_STATIC;
		faceRefForm = { ...FACE_REF_OPTIONS_STATIC.defaults };
	}

	function hydrateFaceFormFromCharacter() {
		const defaults = (faceRefOptions ?? FACE_REF_OPTIONS_STATIC).defaults;
		if (character.face_ref && Object.keys(character.face_ref).length > 0) {
			faceRefForm = { ...defaults, ...character.face_ref };
		} else {
			faceRefForm = { ...defaults };
		}
		faceRefExtraDetails = character.face_extra_details ?? '';
	}

	type PersistPortraitOpts = {
		/**
		 * Character-portraits POST merges keys only. Use this when the map must lose keys
		 * (delete variant / rename) by replacing the whole `portraits` object on the story.
		 */
		replaceEntirePortraitsMap?: boolean;
	};

	async function persistCharacterPortraitFields(
		partial: {
			portrait?: string;
			portraits?: Record<string, string>;
			face_ref?: Record<string, string>;
			face_extra_details?: string;
			portrait_rules?: PortraitRule[];
		},
		opts?: PersistPortraitOpts,
	) {
		const charKey = character.key.trim();
		if (!charKey) return;

		if (opts?.replaceEntirePortraitsMap && partial.portraits !== undefined) {
			try {
				const gr = await fetch(`/api/stories/${storyId}`, { credentials: 'include' });
				const sj = (await gr.json().catch(() => ({}))) as Record<string, unknown>;
				if (!gr.ok) return;
				const chars = sj.characters;
				if (!chars || typeof chars !== 'object' || Array.isArray(chars)) return;
				const raw = (chars as Record<string, unknown>)[charKey];
				if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return;
				const merged: Record<string, unknown> = { ...(raw as Record<string, unknown>) };
				merged.portraits = partial.portraits;
				if (partial.portrait_rules !== undefined) merged.portrait_rules = partial.portrait_rules;
				if (partial.portrait !== undefined) {
					const p = partial.portrait.trim();
					merged.portrait = p ? p.split('?')[0] : '';
				}
				(chars as Record<string, unknown>)[charKey] = merged;
				const pr = await fetch(`/api/stories/${storyId}`, {
					method: 'PUT',
					credentials: 'include',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ characters: chars }),
				});
				if (!pr.ok) return;
				const next = charEntryFromStoryPayload(charKey, merged);
				if (next) onCharacterChange(next);
			} catch {
				/* non-fatal */
			}
			return;
		}

		try {
			const r = await fetch(`/api/stories/${storyId}/character-portraits`, {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ character_key: charKey, ...partial }),
			});
			const j = (await r.json().catch(() => ({}))) as {
				character?: Record<string, unknown>;
				error?: string;
			};
			if (r.ok && j.character && typeof j.character === 'object') {
				onCharacterChange(mergeCharEntryFromServer(character, j.character));
			}
		} catch {
			/* non-fatal */
		}
	}

	function portraitRulesWithoutVariantUse(rules: PortraitRule[] | undefined, variantKey: string): PortraitRule[] {
		return (rules ?? []).filter((r) => r.use !== variantKey);
	}

	function portraitRulesRenameUse(rules: PortraitRule[] | undefined, fromKey: string, toKey: string): PortraitRule[] {
		return (rules ?? []).map((r) => (r.use === fromKey ? { ...r, use: toKey } : r));
	}

	async function confirmDeleteVariant(vkey: string, vfile: string) {
		const portraits = { ...(character.portraits ?? {}) };
		delete portraits[vkey];
		const portrait_rules = portraitRulesWithoutVariantUse(character.portrait_rules, vkey);
		const fileBase = vfile.split('?')[0];
		const portraitBase = (character.portrait ?? '').split('?')[0];
		const refBase = referenceFaceFilenameForVariants();
		const clearDefault = portraitBase && fileBase && portraitBase === fileBase;
		const portraitPatch = clearDefault && refBase ? refBase : undefined;
		deleteConfirmKey = null;
		onCharacterChange({
			...character,
			portraits,
			portrait_rules,
			...(portraitPatch !== undefined ? { portrait: portraitPatch } : {}),
		});
		await persistCharacterPortraitFields(
			{
				portraits,
				portrait_rules,
				...(portraitPatch !== undefined ? { portrait: portraitPatch } : {}),
			},
			{ replaceEntirePortraitsMap: true },
		);
	}

	async function regenerateSingleVariant(vkey: string) {
		const ref = referenceFaceFilenameForVariants();
		if (!ref) {
			wizardError = 'Pick or save a base reference portrait first.';
			return;
		}
		variantFieldError = '';
		wizardError = '';
		variantRegenerating = { ...variantRegenerating, [vkey]: true };
		try {
			const r = await fetch('/api/ai/generate-character-variants', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: character.key.trim(),
					reference: ref,
					variants: [{ key: vkey, prompt: defaultVariantPromptForKey(vkey) }],
					weight: wizardWeight,
				}),
			});
			const j = (await r.json().catch(() => ({}))) as {
				error?: string;
				results?: { key: string; ok: boolean; filename?: string }[];
			};
			if (!r.ok) {
				wizardError = j.error || 'Variant regeneration failed';
				return;
			}
			const row = (j.results ?? []).find((x) => x.key === vkey && x.ok && x.filename);
			if (!row?.filename) {
				wizardError = 'Regeneration did not return a file for this variant.';
				return;
			}
			const portraits = { ...(character.portraits ?? {}), [vkey]: row.filename };
			onCharacterChange({ ...character, portraits });
			variantReloadNonce = { ...variantReloadNonce, [vkey]: Date.now() };
			await persistCharacterPortraitFields({ portraits: { [vkey]: row.filename } });
			afterVariantsGenerated?.();
		} catch {
			wizardError = 'Network error';
		} finally {
			const next = { ...variantRegenerating };
			delete next[vkey];
			variantRegenerating = next;
		}
	}

	async function submitCustomVariant() {
		variantFieldError = '';
		wizardError = '';
		const key = customVariantKeyInput.trim();
		const desc = customVariantDesc.trim();
		if (!key) {
			variantFieldError = 'Variant name is required.';
			return;
		}
		if (!isValidVariantKey(key)) {
			variantFieldError = 'Use letters, numbers, and underscores only.';
			return;
		}
		if (character.portraits?.[key]) {
			variantFieldError = 'That variant name already exists.';
			return;
		}
		if (!desc) {
			variantFieldError = 'Add an expression description.';
			return;
		}
		const ref = referenceFaceFilenameForVariants();
		if (!ref) {
			variantFieldError = 'Pick or save a base reference portrait first.';
			return;
		}
		customVariantBusy = true;
		try {
			const r = await fetch('/api/ai/generate-character-variants', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: character.key.trim(),
					reference: ref,
					variants: [{ key, prompt: desc }],
					weight: wizardWeight,
				}),
			});
			const j = (await r.json().catch(() => ({}))) as {
				error?: string;
				results?: { key: string; ok: boolean; filename?: string }[];
			};
			if (!r.ok) {
				variantFieldError = j.error || 'Generation failed';
				return;
			}
			const row = (j.results ?? []).find((x) => x.key === key && x.ok && x.filename);
			if (!row?.filename) {
				variantFieldError = 'Generation did not return a file for this variant.';
				return;
			}
			const portraits = { ...(character.portraits ?? {}), [key]: row.filename };
			variantFieldError = '';
			onCharacterChange({ ...character, portraits });
			await persistCharacterPortraitFields({ portraits: { [key]: row.filename } });
			customVariantKeyInput = '';
			customVariantDesc = '';
			afterVariantsGenerated?.();
		} catch {
			variantFieldError = 'Network error';
		} finally {
			customVariantBusy = false;
		}
	}

	function startRenameVariant(vkey: string) {
		variantFieldError = '';
		editingVariantKey = vkey;
		renameDraft = vkey;
		void tick().then(() => {
			renameInputEl?.focus();
			renameInputEl?.select();
		});
	}

	function cancelRenameVariant() {
		editingVariantKey = null;
		renameDraft = '';
	}

	async function commitRenameVariant(fromKey: string) {
		variantFieldError = '';
		const toKey = renameDraft.trim();
		if (toKey === fromKey) {
			cancelRenameVariant();
			return;
		}
		if (!toKey) {
			variantFieldError = 'Name cannot be empty.';
			void tick().then(() => renameInputEl?.focus());
			return;
		}
		if (!isValidVariantKey(toKey)) {
			variantFieldError = 'Use letters, numbers, and underscores only.';
			void tick().then(() => renameInputEl?.focus());
			return;
		}
		if (character.portraits?.[toKey]) {
			variantFieldError = 'That name is already used.';
			void tick().then(() => renameInputEl?.focus());
			return;
		}
		const fn = character.portraits?.[fromKey];
		if (!fn) {
			cancelRenameVariant();
			return;
		}
		const portraits: Record<string, string> = { ...(character.portraits ?? {}) };
		delete portraits[fromKey];
		portraits[toKey] = fn;
		const portrait_rules = portraitRulesRenameUse(character.portrait_rules, fromKey, toKey);
		const nr = { ...variantReloadNonce };
		if (nr[fromKey] != null) {
			nr[toKey] = nr[fromKey]!;
			delete nr[fromKey];
			variantReloadNonce = nr;
		}
		variantFieldError = '';
		editingVariantKey = null;
		renameDraft = '';
		onCharacterChange({ ...character, portraits, portrait_rules });
		await persistCharacterPortraitFields(
			{ portraits, portrait_rules },
			{ replaceEntirePortraitsMap: true },
		);
	}

	async function setDefaultPortraitFromVariantFile(filename: string) {
		const fn = filename.split('?')[0].trim();
		if (!fn) return;
		onCharacterChange({ ...character, portrait: fn });
		await persistCharacterPortraitFields({ portrait: fn });
	}

	let generatingFaces = $state(false);

	async function startFaceWizard() {
		generatingFaces = true;
		wizardCandidates = [];
		wizardPickedFace = '';
		wizardVariantResults = [];
		wizardError = '';
		wizardVariantOk = '';
		const charKey = character.key.trim();
		if (!charKey) { generatingFaces = false; return; }
		try {
			const r = await fetch('/api/ai/generate-character-faces', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: charKey,
					count: 3,
					...faceRefForm,
					face_extra_details: faceRefExtraDetails.trim(),
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (!r.ok) {
				wizardError = j.error || 'Face generation failed';
				return;
			}
			wizardCandidates = j.candidates || [];
			if (wizardCandidates.length === 0) wizardError = 'No faces generated';
			else {
				void persistCharacterPortraitFields({
					face_ref: { ...faceRefForm },
					face_extra_details: faceRefExtraDetails.trim(),
				});
			}
		} catch {
			wizardError = 'Network error';
		} finally {
			generatingFaces = false;
		}
	}

	function openVariantToolsOnly() {
		const fn = (character.portrait ?? '').split('?')[0].trim();
		if (!fn) return;
		hydrateFaceFormFromCharacter();
		wizardPickedFace = fn;
		wizardCandidates = [];
		wizardVariantResults = [];
		wizardError = '';
		wizardVariantOk = '';
		wizardStep = 'variants';
	}

	function goToVariantsPhase() {
		if (!wizardPickedFace.trim()) return;
		wizardStep = 'variants';
		wizardVariantOk = '';
	}

	let generatingVariants = $state(false);
	let showRulesSuggest = $state(false);

	async function generateVariantsFromRef() {
		generatingVariants = true;
		wizardVariantResults = [];
		wizardError = '';
		wizardVariantOk = '';
		showRulesSuggest = false;
		const charKey = character.key.trim();
		const ref = referenceFaceFilenameForVariants();
		const enabledVariants = wizardVariants.filter((v) => v.enabled).map((v) => ({ key: v.key, prompt: v.prompt }));
		if (enabledVariants.length === 0) {
			wizardError = 'Select at least one variant';
			generatingVariants = false;
			return;
		}
		if (!ref) {
			wizardError = 'Pick or save a base reference portrait first.';
			generatingVariants = false;
			return;
		}
		try {
			const r = await fetch('/api/ai/generate-character-variants', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: charKey,
					reference: ref,
					variants: enabledVariants,
					weight: wizardWeight,
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (!r.ok) {
				wizardError = j.error || 'Variant generation failed';
				return;
			}
			wizardVariantResults = j.results || [];
			const portraits = { ...(character.portraits ?? {}) };
			const okKeys: string[] = [];
			for (const row of wizardVariantResults) {
				if (row.ok && row.filename && row.key) {
					portraits[row.key] = row.filename;
					okKeys.push(row.key);
				}
			}
			onCharacterChange({ ...character, portraits });
			const okN = okKeys.length;
			wizardVariantOk =
				okN > 0
					? `Saved ${okN} variant(s) (keys: ${okKeys.join(', ')}). They are stored on the story.`
					: '';
			if (okKeys.length > 0) {
				variantKeysAfterRun = [...new Set([...Object.keys(portraits), ...okKeys])].sort();
				portraitRulesDraft = suggestPortraitRules(character.moods, okKeys);
				showRulesSuggest = true;
			}
			afterVariantsGenerated?.();
		} catch {
			wizardError = 'Network error';
		} finally {
			generatingVariants = false;
		}
	}

	function resetWizard() {
		wizardStep = 'idle';
		wizardCandidates = [];
		wizardPickedFace = '';
		wizardVariantOk = '';
		wizardError = '';
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
		deleteConfirmKey = null;
		editingVariantKey = null;
		renameDraft = '';
		variantFieldError = '';
	}

	function removeRuleAt(index: number) {
		portraitRulesDraft = portraitRulesDraft.filter((_, i) => i !== index);
	}

	function applyPortraitRulesDraft() {
		const charKey = character.key.trim();
		if (!charKey) return;
		onCharacterChange({ ...character, portrait_rules: [...portraitRulesDraft] });
		void persistCharacterPortraitFields({ portrait_rules: [...portraitRulesDraft] });
		wizardVariantOk = 'Portrait rules saved (optional fine-tuning).';
		showRulesSuggest = false;
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
	}

	function dismissRulesSuggest() {
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
		showRulesSuggest = false;
	}

	onMount(() => {
		void loadFaceRefOptions();
		hydrateFaceFormFromCharacter();
		// If character already has a portrait, use it as the reference for variants
		const existingPortrait = (character.portrait ?? '').split('?')[0].trim();
		if (existingPortrait) {
			wizardPickedFace = existingPortrait;
		}
	});
</script>

<div class="wizard-section">
	<div class="field-head">
		<strong>Character Consistency Wizard</strong>
	</div>
	<span class="hint">
		<strong>Phase 1</strong> — Set face options, generate candidates, pick one <strong>base reference</strong> (IP-Adapter /
		LoRA–friendly headshot). <strong>Phase 2</strong> — Generate expression variants anytime; they are saved on the story.
		You can leave and return — your base face, face options, and variants reload from the story.
	</span>

	<div class="wizard-face-controls">
		<strong class="wizard-face-controls-title">Face reference (manual)</strong>
		<div class="wizard-face-grid">
			{#each FACE_REF_FIELD_ORDER as fk (fk)}
				<label class="field-sm wizard-face-field">
					<span>{FACE_REF_FIELD_LABELS[fk] ?? fk}</span>
					<select
						class="wizard-face-select"
						value={faceRefForm[fk] ?? ''}
						onchange={(e) => {
							faceRefForm = { ...faceRefForm, [fk]: (e.currentTarget as HTMLSelectElement).value };
						}}
					>
						{#each (faceRefFieldsSource.fields[fk] ?? []) as opt (opt.value)}
							<option value={opt.value}>{opt.label}</option>
						{/each}
					</select>
				</label>
			{/each}
		</div>
		<label class="field-sm">
			<span>Extra facial details (optional)</span>
			<textarea
				rows="2"
				class="wizard-face-extra"
				bind:value={faceRefExtraDetails}
				placeholder="e.g. freckles, scar, beauty mark, glasses — short phrases"
			></textarea>
		</label>
	</div>

	<!-- Phase 1: Generate candidate faces -->
	<div class="wizard-phase-tag">Phase 1 — Generate candidate faces</div>
	<div class="cover-btn-row" style="margin-top:0.5rem; flex-wrap:wrap">
		<button type="button"
			class="btn sm primary"
			disabled={!character.key.trim() || generatingFaces}
			onclick={() => startFaceWizard()}
		>
			{#if generatingFaces}<span class="spinner"></span> Generating…{:else}Generate candidate faces{/if}
		</button>
	</div>

	{#if wizardCandidates.length > 0}
		<div class="wizard-pick">
			<p class="hint" style="margin-top:0.5rem">
				Choose one candidate as the <strong>base face</strong> (IP-Adapter will lock to this). It becomes the character’s
				default portrait.
			</p>
			<div class="wizard-candidates">
				{#each wizardCandidates as cand (cand.index)}
					<button
						type="button"
						class="wizard-face-btn"
						class:selected={wizardPickedFace === cand.filename}
						onclick={() => {
							wizardPickedFace = cand.filename;
							onCharacterChange({ ...character, portrait: cand.filename });
							void persistCharacterPortraitFields({ portrait: cand.filename });
						}}
					>
						<img src={`/images/portraits/${cand.filename}`} alt="Candidate {cand.index + 1}" />
						<span class="wizard-face-label">Face {cand.index + 1}</span>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	{#if wizardError}
		<p class="err" style="font-size:0.85rem; margin-top:0.35rem">{wizardError}</p>
	{/if}

	<hr style="border-color:#2a2f38; margin:1rem 0" />

	<!-- Phase 2: Expression variants (always visible) -->
	<div class="wizard-phase-tag">Phase 2 — Expression variants</div>
		<p class="hint" style="margin-top:0.35rem">
			Reference image below is what IP-Adapter uses. Each run writes files under
			<code class="wizard-code">web/static/images/portraits/</code> and updates this character’s
			<strong>portraits</strong> map (mood keys). Adjust checkboxes and click <strong>Generate</strong> again anytime.
		</p>

		{#if referenceFaceFilenameForVariants()}
			<div class="wizard-ref-row">
				<div>
					<span class="wizard-subcap">Base reference</span>
					<div class="wizard-ref-preview">
						<img src={`/images/portraits/${referenceFaceFilenameForVariants().split('?')[0]}`} alt="Reference face" />
					</div>
				</div>
				<div class="wizard-saved-variants">
					<span class="wizard-subcap">Saved variants ({Object.keys(character.portraits ?? {}).length})</span>
					{#if Object.keys(character.portraits ?? {}).length === 0}
						<p class="muted" style="font-size:0.82rem; margin:0.35rem 0 0">None yet — generate below.</p>
					{:else}
						<div class="wizard-variant-grid">
							{#each Object.entries(character.portraits ?? {}).sort(([a], [b]) => a.localeCompare(b)) as [vkey, vfile] (vkey)}
								<div class="wizard-variant-tile">
									<div
										class="wizard-variant-thumb"
										class:wizard-variant-thumb-default={isVariantDefaultPortrait(vfile)}
									>
										<img src={variantPortraitUrl(vfile, vkey)} alt={vkey} />
										{#if variantRegenerating[vkey]}
											<div class="wizard-variant-thumb-overlay" aria-live="polite">
												<span class="spinner wizard-variant-overlay-spinner"></span>
											</div>
										{/if}
										{#if deleteConfirmKey === vkey}
											<div class="wizard-variant-delete-confirm">
												<span>Delete <strong>{vkey}</strong>?</span>
												<div class="wizard-variant-delete-actions">
													<button type="button" class="btn sm" onclick={() => (deleteConfirmKey = null)}>Cancel</button>
													<button
														type="button"
														class="btn sm danger"
														onclick={() => void confirmDeleteVariant(vkey, vfile)}
													>Delete</button>
												</div>
											</div>
										{:else}
											<div class="wizard-variant-actions">
												<div class="wizard-variant-actions-row wizard-variant-actions-top">
													<button
														type="button"
														class="wizard-variant-icon-btn"
														title="Set as default portrait"
														aria-label="Set as default portrait"
														onmousedown={(e) => e.preventDefault()}
														onclick={() => void setDefaultPortraitFromVariantFile(vfile)}
													>
														{isVariantDefaultPortrait(vfile) ? '★' : '☆'}
													</button>
													<button
														type="button"
														class="wizard-variant-icon-btn wizard-variant-icon-danger"
														title="Remove variant from character"
														aria-label="Delete variant"
														onmousedown={(e) => e.preventDefault()}
														onclick={() => (deleteConfirmKey = vkey)}
													>
														×
													</button>
												</div>
												<div class="wizard-variant-actions-row wizard-variant-actions-bottom">
													<button
														type="button"
														class="wizard-variant-icon-btn"
														title="Regenerate this variant"
														aria-label="Regenerate this variant"
														disabled={Boolean(variantRegenerating[vkey])}
														onmousedown={(e) => e.preventDefault()}
														onclick={() => void regenerateSingleVariant(vkey)}
													>
														↻
													</button>
												</div>
											</div>
										{/if}
									</div>
									{#if editingVariantKey === vkey}
										<input
											class="wizard-variant-rename-input"
											bind:this={renameInputEl}
											bind:value={renameDraft}
											onblur={() => void commitRenameVariant(vkey)}
											onkeydown={(e) => {
												if (e.key === 'Enter') {
													e.preventDefault();
													void commitRenameVariant(vkey);
												} else if (e.key === 'Escape') {
													e.preventDefault();
													cancelRenameVariant();
												}
											}}
										/>
									{:else}
										<button
											type="button"
											class="wizard-variant-label-btn wizard-face-label"
											onclick={() => startRenameVariant(vkey)}
										>
											{vkey}
										</button>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
					{#if variantFieldError}
						<p class="err wizard-variant-field-err" style="font-size:0.78rem; margin:0.35rem 0 0">{variantFieldError}</p>
					{/if}
					<div class="wizard-custom-variant">
						<span class="wizard-subcap" style="margin-top:0.55rem">Add custom variant</span>
						<div class="wizard-custom-variant-form">
							<input
								class="wizard-custom-variant-input"
								type="text"
								placeholder="variant_key"
								autocomplete="off"
								disabled={customVariantBusy}
								bind:value={customVariantKeyInput}
							/>
							<input
								class="wizard-custom-variant-input wizard-custom-variant-grow"
								type="text"
								placeholder="Expression description (prompt)"
								autocomplete="off"
								disabled={customVariantBusy}
								bind:value={customVariantDesc}
							/>
							<button
								type="button"
								class="btn sm primary"
								disabled={customVariantBusy || !referenceFaceFilenameForVariants().trim()}
								onclick={() => void submitCustomVariant()}
							>
								{#if customVariantBusy}<span class="spinner wizard-variant-overlay-spinner"></span>{/if}
								Generate
							</button>
						</div>
					</div>
				</div>
			</div>
		{/if}

		{#if wizardVariantResults.length > 0}
			<div class="wizard-last-run">
				<span class="wizard-subcap">Last run</span>
				<div class="wizard-candidates" style="margin-top:0.35rem">
					{#each wizardVariantResults as vr (vr.key)}
						<div class="wizard-variant-result" class:failed={!vr.ok}>
							{#if vr.ok && vr.url}
								<img src={vr.url} alt="{vr.key} variant" />
							{:else}
								<div class="image-placeholder portrait-placeholder">
									<span>Failed</span>
								</div>
							{/if}
							<span class="wizard-face-label">{vr.key}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if wizardVariantOk}
			<p class="ok" style="font-size:0.85rem; margin-top:0.5rem" transition:fade={{ duration: 150 }}>{wizardVariantOk}</p>
		{/if}
		{#if wizardError}
			<p class="err" style="font-size:0.85rem; margin-top:0.35rem">{wizardError}</p>
		{/if}

		<div class="wizard-variant-config">
			<strong style="font-size:0.88rem">Which expressions to generate</strong>
			<div class="wizard-variant-list">
				{#each wizardVariants as v (v.key)}
					<label class="tag-check">
						<input type="checkbox" bind:checked={v.enabled} />
						<span>{v.key}</span>
					</label>
				{/each}
			</div>
			<label class="field-sm" style="margin-top:0.4rem">
				<span>Face similarity (weight: {wizardWeight.toFixed(2)})</span>
				<input type="range" min="0.4" max="1.0" step="0.05" bind:value={wizardWeight} style="width:12rem" />
			</label>
			<div class="cover-btn-row" style="margin-top:0.4rem">
				<button
					type="button"
					class="btn sm primary"
					disabled={!referenceFaceFilenameForVariants().trim() || generatingVariants}
					onclick={() => generateVariantsFromRef()}
				>
					{#if generatingVariants}<span class="spinner"></span> Generating…{:else}Generate {wizardVariants.filter((v) => v.enabled).length} variant(s){/if}
				</button>
			</div>
		</div>

	{#if generatingVariants}
		<div class="wizard-status">
			<span class="spinner"></span> Generating variants with IP-Adapter ({wizardVariants.filter((v) => v.enabled).length}
			image(s))…
		</div>
	{/if}

	{#if showRulesSuggest}
		<div class="wizard-phase-tag">Optional — Mood rules</div>
		<p class="hint" style="margin-top:0.45rem">
			<strong>Fine-tuning only.</strong> At play time, facial expressions are chosen by the <strong>expression_picker</strong> LLM from
			your variants. These rules are an optional hint for other systems (e.g. legacy mood→portrait mapping). You can skip this
			entirely.
		</p>
		{#if portraitRulesDraft.length === 0}
			<p class="muted" style="font-size:0.88rem; margin:0.5rem 0">
				No automatic rules for your current mood axes. We only suggest ranges for axes named <code class="wizard-code">mood</code>
				or <code class="wizard-code">arousal</code>, and only for variants you just generated.
			</p>
		{:else}
			<ul class="rules-draft-list">
				{#each portraitRulesDraft as rule, ri (ri)}
					<li class="rules-draft-row">
						<span class="rules-draft-summary">{ruleSummary(rule)}</span>
						<label class="rules-use-label">
							<span>Expression</span>
							<select
								class="wizard-face-select rules-use-select"
								value={rule.use}
								onchange={(e) => {
									const v = (e.currentTarget as HTMLSelectElement).value;
									portraitRulesDraft = portraitRulesDraft.map((r, i) =>
										i === ri ? { ...r, use: v } : r,
									);
								}}
							>
								{#each variantKeysAfterRun as vk (vk)}
									<option value={vk}>{vk}</option>
								{/each}
							</select>
						</label>
						<button type="button" class="btn sm danger" onclick={() => removeRuleAt(ri)}>Remove</button>
					</li>
				{/each}
			</ul>
		{/if}
		<div class="cover-btn-row" style="margin-top:0.65rem">
			<button type="button" class="btn sm primary" onclick={() => applyPortraitRulesDraft()}>
				Apply suggestions
			</button>
			<button type="button" class="btn sm" onclick={() => dismissRulesSuggest()}>Skip — LLM only</button>
		</div>
		<p class="muted" style="font-size:0.78rem; margin-top:0.45rem">
			Applying replaces this character’s saved <code class="wizard-code">portrait_rules</code> with the list above (or clears them
			if the list is empty).
		</p>
	{/if}
</div>

<style>
	.field-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
	}
	.hint {
		display: block;
		font-size: 0.82rem;
		color: #9aa0a6;
		margin-bottom: 0.3rem;
		line-height: 1.45;
	}
	.field-sm {
		display: block;
		margin-bottom: 0.4rem;
	}
	.field-sm span {
		display: block;
		font-size: 0.78rem;
		color: #9aa0a6;
		margin-bottom: 0.15rem;
	}
	.field-sm input,
	.field-sm textarea {
		width: 100%;
		box-sizing: border-box;
		font-size: 0.85rem;
	}
	.btn {
		padding: 0.45rem 0.85rem;
		border: 1px solid #3c4043;
		background: #2a2f38;
		color: #e8eaed;
		border-radius: 8px;
		font: inherit;
		font-size: 0.85rem;
	}
	.btn:hover {
		border-color: #5f6368;
	}
	.btn.primary {
		background: #1a73e8;
		border-color: #1a73e8;
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn.sm {
		font-size: 0.8rem;
		padding: 0.35rem 0.65rem;
		margin-top: 0.3rem;
	}
	.cover-btn-row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.err {
		color: #f28b82;
		margin: 0.25rem 0;
	}
	.ok {
		color: #81c995;
		margin: 0.25rem 0;
	}
	.muted {
		color: #9aa0a6;
	}
	.tag-check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.88rem;
		color: #e8eaed;
		cursor: pointer;
	}
	.tag-check input[type='checkbox'] {
		accent-color: #1a73e8;
		margin: 0;
	}
	.wizard-section {
		border: 1px solid #2a3a50;
		border-radius: 8px;
		padding: 0.75rem;
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
		background: #111827;
	}
	.wizard-face-controls {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid #2a2f38;
	}
	.wizard-face-controls-title {
		display: block;
		font-size: 0.82rem;
		color: #c4c7ce;
		margin-bottom: 0.45rem;
	}
	.wizard-face-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.45rem 0.75rem;
		margin-top: 0.35rem;
	}
	@media (max-width: 520px) {
		.wizard-face-grid {
			grid-template-columns: 1fr;
		}
	}
	.wizard-face-field .wizard-face-select {
		font-size: 0.82rem;
		width: 100%;
	}
	.wizard-face-extra {
		font-size: 0.82rem;
		width: 100%;
		box-sizing: border-box;
		resize: vertical;
		min-height: 2.5rem;
	}
	.wizard-phase-tag {
		display: inline-block;
		margin-top: 0.5rem;
		padding: 0.2rem 0.5rem;
		border-radius: 6px;
		background: #1a3a5c;
		color: #a8c7fa;
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.02em;
	}
	.wizard-code {
		font-size: 0.78rem;
		background: #2a2f38;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
	}
	.wizard-subcap {
		display: block;
		font-size: 0.78rem;
		color: #9aa0a6;
		margin-bottom: 0.35rem;
		font-weight: 600;
	}
	.wizard-ref-row {
		display: flex;
		gap: 1rem;
		flex-wrap: wrap;
		margin-top: 0.65rem;
		align-items: flex-start;
	}
	.wizard-ref-preview {
		width: 120px;
		aspect-ratio: 2 / 3;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid #2a2f38;
		background: #161a20;
	}
	.wizard-ref-preview img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.wizard-saved-variants {
		flex: 1;
		min-width: 200px;
	}
	.wizard-variant-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		margin-top: 0.25rem;
	}
	.wizard-variant-tile {
		text-align: center;
		width: 72px;
	}
	.wizard-variant-thumb {
		position: relative;
		width: 72px;
		border-radius: 6px;
		overflow: hidden;
	}
	.wizard-variant-thumb-default {
		box-shadow: 0 0 0 2px #f9ab00;
	}
	.wizard-variant-thumb img {
		width: 72px;
		height: 108px;
		object-fit: cover;
		border-radius: 6px;
		border: 1px solid #2a2f38;
		display: block;
	}
	.wizard-variant-thumb-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.45);
		border-radius: 6px;
	}
	.wizard-variant-overlay-spinner {
		margin: 0;
		width: 1.25rem;
		height: 1.25rem;
		border-top-color: #e8eaed;
	}
	.wizard-variant-actions {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: 0.15rem;
		opacity: 0;
		transition: opacity 0.12s ease;
		pointer-events: none;
		border-radius: 6px;
	}
	.wizard-variant-thumb:hover .wizard-variant-actions {
		opacity: 1;
		pointer-events: auto;
	}
	@media (hover: none) {
		.wizard-variant-actions {
			opacity: 0.72;
			pointer-events: auto;
		}
	}
	.wizard-variant-actions-row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		width: 100%;
	}
	.wizard-variant-actions-bottom {
		justify-content: flex-end;
	}
	.wizard-variant-icon-btn {
		width: 1.35rem;
		height: 1.35rem;
		padding: 0;
		border: none;
		border-radius: 4px;
		background: rgba(22, 26, 32, 0.55);
		color: #e8eaed;
		font-size: 1rem;
		line-height: 1;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0.55;
		transition:
			opacity 0.12s ease,
			background 0.12s ease;
	}
	.wizard-variant-thumb:hover .wizard-variant-icon-btn {
		opacity: 0.9;
	}
	.wizard-variant-icon-btn:hover:not(:disabled) {
		opacity: 1;
		background: rgba(22, 26, 32, 0.88);
	}
	.wizard-variant-icon-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
	.wizard-variant-icon-danger:hover:not(:disabled) {
		color: #f28b82;
	}
	.wizard-variant-delete-confirm {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		gap: 0.35rem;
		padding: 0.25rem;
		background: rgba(10, 12, 16, 0.92);
		font-size: 0.68rem;
		color: #e8eaed;
		text-align: center;
		border-radius: 6px;
		z-index: 2;
	}
	.wizard-variant-delete-confirm strong {
		color: #fde293;
		font-weight: 600;
	}
	.wizard-variant-delete-actions {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
		justify-content: center;
	}
	.wizard-variant-delete-actions .btn.sm {
		margin-top: 0;
	}
	.wizard-variant-label-btn {
		background: none;
		border: none;
		padding: 0.1rem 0.2rem;
		margin: 0;
		cursor: pointer;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		border-radius: 4px;
		font: inherit;
	}
	.wizard-variant-label-btn:hover {
		background: #2a2f38;
		color: #e8eaed;
	}
	.wizard-variant-rename-input {
		width: 100%;
		box-sizing: border-box;
		font-size: 0.72rem;
		margin-top: 0.15rem;
		padding: 0.12rem 0.2rem;
		border-radius: 4px;
		border: 1px solid #5f6368;
		background: #161a20;
		color: #e8eaed;
	}
	.wizard-custom-variant-form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		align-items: center;
		margin-top: 0.3rem;
	}
	.wizard-custom-variant-input {
		font-size: 0.82rem;
		padding: 0.3rem 0.45rem;
		border-radius: 6px;
		border: 1px solid #3c4043;
		background: #161a20;
		color: #e8eaed;
		min-width: 5rem;
	}
	.wizard-custom-variant-grow {
		flex: 1;
		min-width: 140px;
	}
	.wizard-last-run {
		margin-top: 0.65rem;
		padding-top: 0.5rem;
		border-top: 1px solid #2a2f38;
	}
	.wizard-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0;
		color: #9aa0a6;
		font-size: 0.88rem;
	}
	.wizard-candidates {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 0.4rem;
	}
	.wizard-face-btn {
		background: none;
		border: 2px solid #2a2f38;
		border-radius: 8px;
		padding: 0.2rem;
		cursor: pointer;
		text-align: center;
		transition: border-color 0.15s;
	}
	.wizard-face-btn:hover {
		border-color: #5f6368;
	}
	.wizard-face-btn.selected {
		border-color: #1a73e8;
		box-shadow: 0 0 0 1px #1a73e8;
	}
	.wizard-face-btn img {
		width: 100px;
		height: 150px;
		object-fit: cover;
		border-radius: 6px;
		display: block;
	}
	.wizard-face-label {
		display: block;
		font-size: 0.75rem;
		color: #9aa0a6;
		margin-top: 0.2rem;
	}
	.wizard-variant-config {
		margin-top: 0.6rem;
		padding-top: 0.5rem;
		border-top: 1px solid #2a2f38;
	}
	.wizard-variant-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-top: 0.3rem;
	}
	.wizard-variant-result {
		text-align: center;
	}
	.wizard-variant-result img {
		width: 80px;
		height: 120px;
		object-fit: cover;
		border-radius: 6px;
		border: 1px solid #2a2f38;
	}
	.wizard-variant-result.failed {
		opacity: 0.5;
	}
	.portrait-placeholder {
		width: 80px;
		height: 120px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: #161a20;
		border: 1px solid #2a2f38;
		border-radius: 6px;
		font-size: 0.72rem;
		color: #9aa0a6;
	}
	.btn.danger {
		background: #5c2b2b;
		border-color: #8a3d3d;
		color: #fce8e6;
	}
	.rules-draft-list {
		list-style: none;
		padding: 0;
		margin: 0.5rem 0 0;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.rules-draft-row {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.5rem;
		padding: 0.45rem 0.5rem;
		background: #161a20;
		border: 1px solid #2a2f38;
		border-radius: 6px;
	}
	.rules-draft-summary {
		flex: 1;
		min-width: 140px;
		font-size: 0.82rem;
		color: #c4c7ce;
	}
	.rules-use-label {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		font-size: 0.72rem;
		color: #9aa0a6;
	}
	.rules-use-select {
		min-width: 7rem;
	}
</style>
