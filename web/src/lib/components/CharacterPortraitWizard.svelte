<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import {
		FACE_REF_OPTIONS_STATIC,
		FACE_REF_FIELD_LABELS,
		FACE_REF_FIELD_ORDER,
		type FaceRefOptionsPayload,
	} from '$lib/faceRefOptions';
	import type { CharEntry, PortraitRule } from '$lib/characterTypes';
	import { mergeCharEntryFromServer } from '$lib/characterTypes';
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

	const faceRefFieldsSource = $derived(faceRefOptions ?? FACE_REF_OPTIONS_STATIC);

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

	async function persistCharacterPortraitFields(partial: {
		portrait?: string;
		portraits?: Record<string, string>;
		face_ref?: Record<string, string>;
		face_extra_details?: string;
		portrait_rules?: PortraitRule[];
	}) {
		const charKey = character.key.trim();
		if (!charKey) return;
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

	async function startFaceWizard() {
		hydrateFaceFormFromCharacter();
		wizardStep = 'generating_faces';
		wizardCandidates = [];
		wizardPickedFace = '';
		wizardVariantResults = [];
		wizardError = '';
		wizardVariantOk = '';
		const charKey = character.key.trim();
		if (!charKey) return;
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
				wizardStep = 'idle';
				return;
			}
			wizardCandidates = j.candidates || [];
			wizardStep = wizardCandidates.length > 0 ? 'pick_base' : 'idle';
			if (wizardCandidates.length === 0) wizardError = 'No faces generated';
			else {
				void persistCharacterPortraitFields({
					face_ref: { ...faceRefForm },
					face_extra_details: faceRefExtraDetails.trim(),
				});
			}
		} catch {
			wizardError = 'Network error';
			wizardStep = 'idle';
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

	async function generateVariantsFromRef() {
		wizardStep = 'generating_variants';
		wizardVariantResults = [];
		wizardError = '';
		wizardVariantOk = '';
		const charKey = character.key.trim();
		const enabledVariants = wizardVariants.filter((v) => v.enabled).map((v) => ({ key: v.key, prompt: v.prompt }));
		if (enabledVariants.length === 0) {
			wizardError = 'Select at least one variant';
			wizardStep = 'variants';
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
					reference: wizardPickedFace,
					variants: enabledVariants,
					weight: wizardWeight,
				}),
			});
			const j = await r.json().catch(() => ({}));
			if (!r.ok) {
				wizardError = j.error || 'Variant generation failed';
				wizardStep = 'variants';
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
				wizardStep = 'rules_suggest';
			} else {
				wizardStep = 'variants';
			}
			afterVariantsGenerated?.();
		} catch {
			wizardError = 'Network error';
			wizardStep = 'variants';
		}
	}

	function portraitSrc(portrait: string): string {
		return `/images/portraits/${portrait}`;
	}

	function resetWizard() {
		wizardStep = 'idle';
		wizardCandidates = [];
		wizardPickedFace = '';
		wizardVariantOk = '';
		wizardError = '';
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
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
		wizardStep = 'variants';
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
	}

	function dismissRulesSuggest() {
		portraitRulesDraft = [];
		variantKeysAfterRun = [];
		wizardStep = 'variants';
	}

	onMount(() => {
		void loadFaceRefOptions();
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

	{#if wizardStep === 'idle'}
		<div class="cover-btn-row" style="margin-top:0.5rem; flex-wrap:wrap">
			<button type="button"
				class="btn sm primary"
				disabled={!character.key.trim()}
				onclick={() => startFaceWizard()}
			>
				Phase 1 — Generate candidate faces
			</button>
			{#if character.portrait?.trim()}
				<button type="button" class="btn sm" disabled={!character.key.trim()} onclick={() => openVariantToolsOnly()}>
					Phase 2 — Expression variants only
				</button>
			{/if}
		</div>
		{#if wizardError}
			<p class="err" style="font-size:0.85rem">{wizardError}</p>
		{/if}
	{/if}

	{#if wizardStep === 'generating_faces'}
		<div class="wizard-phase-tag">Phase 1</div>
		<div class="wizard-status">
			<span class="spinner"></span> Generating forward-facing reference headshots (plain background)…
		</div>
	{/if}

	{#if wizardStep === 'pick_base'}
		<div class="wizard-phase-tag">Phase 1 — Pick base reference</div>
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
			<div class="cover-btn-row" style="margin-top:0.5rem">
				<button
					type="button"
					class="btn sm primary"
					disabled={!wizardPickedFace.trim()}
					onclick={() => goToVariantsPhase()}
				>
					Continue to phase 2 — Variants
				</button>
				<button type="button" class="btn sm" onclick={() => resetWizard()}>Cancel wizard</button>
			</div>
			{#if wizardError}
				<p class="err" style="font-size:0.85rem; margin-top:0.35rem">{wizardError}</p>
			{/if}
		</div>
	{/if}

	{#if wizardStep === 'variants'}
		<div class="wizard-phase-tag">Phase 2 — Expression variants</div>
		<p class="hint" style="margin-top:0.35rem">
			Reference image below is what IP-Adapter uses. Each run writes files under
			<code class="wizard-code">web/static/images/portraits/</code> and updates this character’s
			<strong>portraits</strong> map (mood keys). Adjust checkboxes and click <strong>Generate</strong> again anytime.
		</p>

		{#if wizardPickedFace}
			<div class="wizard-ref-row">
				<div>
					<span class="wizard-subcap">Base reference</span>
					<div class="wizard-ref-preview">
						<img src={`/images/portraits/${wizardPickedFace.split('?')[0]}`} alt="Reference face" />
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
									<img src={portraitSrc(vfile)} alt={vkey} />
									<span class="wizard-face-label">{vkey}</span>
								</div>
							{/each}
						</div>
					{/if}
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
					disabled={!wizardPickedFace.trim()}
					onclick={() => generateVariantsFromRef()}
				>
					Generate {wizardVariants.filter((v) => v.enabled).length} variant(s)
				</button>
				{#if wizardCandidates.length > 0}
					<button
						type="button"
						class="btn sm"
						onclick={() => {
							wizardStep = 'pick_base';
							wizardVariantOk = '';
							wizardError = '';
						}}>← Change base image</button>
				{/if}
				<button type="button" class="btn sm" onclick={() => resetWizard()}>Close wizard</button>
			</div>
		</div>
	{/if}

	{#if wizardStep === 'generating_variants'}
		<div class="wizard-phase-tag">Phase 2</div>
		<div class="wizard-status">
			<span class="spinner"></span> Generating variants with IP-Adapter ({wizardVariants.filter((v) => v.enabled).length}
			image(s))…
		</div>
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
	.wizard-variant-tile img {
		width: 72px;
		height: 108px;
		object-fit: cover;
		border-radius: 6px;
		border: 1px solid #2a2f38;
		display: block;
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
</style>
