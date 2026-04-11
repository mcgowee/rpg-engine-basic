<script lang="ts">
	type TrainingImage = { filename: string; caption: string; url: string };

	type Props = {
		storyId: number;
		characterKey: string;
		/** Portrait filename (no query) for FaceID reference; required to generate. */
		referencePortrait?: string | null;
	};

	let { storyId, characterKey, referencePortrait = '' }: Props = $props();

	let triggerWord = $state('');
	let loraWeight = $state(0.85);
	let images = $state<TrainingImage[]>([]);
	let trainingDir = $state<string | null>(null);
	let listLoading = $state(false);
	let listError = $state('');

	let selected = $state<Record<string, boolean>>({});
	let generating = $state(false);
	let generateError = $state('');
	let generateSummary = $state('');

	let exporting = $state(false);
	let exportError = $state('');
	let exportResult = $state<{
		copied: number;
		epochs: number;
		steps_estimate: number;
		training_command: string;
		output_model: string;
	} | null>(null);

	let copyFeedback = $state('');

	const refBasename = $derived((referencePortrait ?? '').split('?')[0].trim());

	function apiImageSrc(url: string): string {
		if (url.startsWith('/ai/')) return `/api${url}`;
		if (url.startsWith('/')) return `/api${url}`;
		return url;
	}

	const selectedCount = $derived(
		images.reduce((n, im) => n + (selected[im.filename] ? 1 : 0), 0),
	);
	const totalCount = $derived(images.length);

	function setAll(on: boolean) {
		const next: Record<string, boolean> = {};
		for (const im of images) next[im.filename] = on;
		selected = next;
	}

	async function fetchTrainingList() {
		listError = '';
		listLoading = true;
		try {
			const ck = encodeURIComponent(characterKey.trim());
			const r = await fetch(`/api/ai/lora-training-data/${storyId}/${ck}`, {
				credentials: 'include',
			});
			const j = (await r.json().catch(() => ({}))) as {
				images?: TrainingImage[];
				training_dir?: string | null;
				error?: string;
			};
			if (!r.ok) {
				listError = j.error ?? `Could not load training data (${r.status}).`;
				images = [];
				trainingDir = null;
				selected = {};
				return;
			}
			const list = Array.isArray(j.images) ? j.images : [];
			images = list;
			trainingDir = j.training_dir ?? null;
			const nextSel: Record<string, boolean> = {};
			for (const im of list) nextSel[im.filename] = true;
			selected = nextSel;
		} catch {
			listError = 'Network error loading training data.';
			images = [];
			trainingDir = null;
			selected = {};
		} finally {
			listLoading = false;
		}
	}

	async function generateTraining() {
		generateError = '';
		generateSummary = '';
		exportResult = null;
		const tw = triggerWord.trim();
		if (!tw) {
			generateError = 'Enter a trigger word.';
			return;
		}
		if (!refBasename) {
			generateError = 'Set a base portrait in Phase 1 first (reference image required).';
			return;
		}
		generating = true;
		try {
			const r = await fetch('/api/ai/generate-lora-training-data', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: characterKey.trim(),
					trigger_word: tw,
					reference: refBasename,
					weight: loraWeight,
				}),
			});
			const j = (await r.json().catch(() => ({}))) as {
				ok?: boolean;
				total?: number;
				success?: number;
				error?: string;
			};
			if (!r.ok) {
				generateError = j.error ?? `Generation failed (${r.status}).`;
				return;
			}
			generateSummary = `Generated ${j.success ?? '?'}/${j.total ?? '?'} images (including reference).`;
			await fetchTrainingList();
		} catch {
			generateError = 'Network error during generation.';
		} finally {
			generating = false;
		}
	}

	async function exportToKohya() {
		exportError = '';
		exportResult = null;
		copyFeedback = '';
		const tw = triggerWord.trim();
		if (!tw) {
			exportError = 'Enter a trigger word.';
			return;
		}
		const filenames = images.filter((im) => selected[im.filename]).map((im) => im.filename);
		if (filenames.length === 0) {
			exportError = 'Select at least one image to export.';
			return;
		}
		exporting = true;
		try {
			const r = await fetch('/api/ai/export-lora-training', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					story_id: storyId,
					character_key: characterKey.trim(),
					trigger_word: tw,
					selected: filenames,
				}),
			});
			const j = (await r.json().catch(() => ({}))) as {
				ok?: boolean;
				copied?: number;
				epochs?: number;
				steps_estimate?: number;
				training_command?: string;
				output_model?: string;
				error?: string;
			};
			if (!r.ok || !j.ok) {
				exportError = j.error ?? `Export failed (${r.status}).`;
				return;
			}
			exportResult = {
				copied: j.copied ?? 0,
				epochs: j.epochs ?? 0,
				steps_estimate: j.steps_estimate ?? 0,
				training_command: j.training_command ?? '',
				output_model: j.output_model ?? '',
			};
		} catch {
			exportError = 'Network error during export.';
		} finally {
			exporting = false;
		}
	}

	async function copyTrainingCommand() {
		const cmd = exportResult?.training_command ?? '';
		if (!cmd) return;
		try {
			await navigator.clipboard.writeText(cmd);
			copyFeedback = 'Copied!';
			setTimeout(() => {
				copyFeedback = '';
			}, 2000);
		} catch {
			copyFeedback = 'Copy failed';
			setTimeout(() => {
				copyFeedback = '';
			}, 2000);
		}
	}

	$effect(() => {
		const sid = storyId;
		const ck = characterKey.trim();
		triggerWord = `${ck.toLowerCase()}char`;
		if (!Number.isFinite(sid) || !ck) return;
		void fetchTrainingList();
	});
</script>

<div class="wizard-section lora-section">
	<div class="wizard-phase-tag">Phase 3 — LoRA Training Data</div>
	<p class="hint lora-lead">
		Diverse poses, angles, and lighting for SDXL LoRA training (Kohya). Independent from expression variants above.
	</p>

	<label class="field-sm">
		<span>Trigger word</span>
		<input
			class="lora-input"
			type="text"
			autocomplete="off"
			placeholder="e.g. alexchar"
			bind:value={triggerWord}
			disabled={generating}
		/>
	</label>

	<label class="field-sm">
		<span>Face similarity (weight: {loraWeight.toFixed(2)})</span>
		<input
			type="range"
			class="lora-range"
			min="0.4"
			max="1"
			step="0.05"
			bind:value={loraWeight}
			disabled={generating}
		/>
	</label>

	<div class="cover-btn-row lora-actions-top">
		<button
			type="button"
			class="btn sm primary"
			disabled={generating || !characterKey.trim() || !refBasename}
			onclick={() => void generateTraining()}
		>
			{#if generating}
				<span class="spinner"></span> Generating…
			{:else}
				Generate 18 Training Images
			{/if}
		</button>
	</div>

	{#if !refBasename}
		<p class="muted small lora-hint">Complete Phase 1 and set a base portrait before generating training images.</p>
	{/if}

	{#if generating}
		<div class="lora-generate-status" role="status" aria-live="polite">
			<span class="spinner"></span>
			<span
				>Generating diverse poses and angles… This usually takes <strong>~3.5 minutes</strong> (17 sequential
				ComfyUI runs plus the copied reference — <strong>18</strong> images total).</span
			>
		</div>
	{/if}

	{#if generateError}
		<p class="err small">{generateError}</p>
	{/if}
	{#if generateSummary}
		<p class="ok small">{generateSummary}</p>
	{/if}

	{#if listLoading && images.length === 0 && !generating}
		<p class="muted small"><span class="spinner"></span> Loading training images…</p>
	{/if}
	{#if listError}
		<p class="err small">{listError}</p>
	{/if}

	{#if trainingDir && images.length > 0}
		<p class="muted small lora-dir"><code class="wizard-code">{trainingDir}</code></p>
	{/if}

	{#if images.length > 0}
		<div class="lora-toolbar">
			<div class="cover-btn-row">
				<button type="button" class="btn sm" onclick={() => setAll(true)} disabled={exporting || generating}>
					Select all
				</button>
				<button type="button" class="btn sm" onclick={() => setAll(false)} disabled={exporting || generating}>
					Deselect all
				</button>
			</div>
			<span class="lora-count">{selectedCount}/{totalCount} selected</span>
		</div>

		<div class="lora-grid" role="list">
			{#each images as im (im.filename)}
				<label
					class="lora-card"
					class:lora-card-on={selected[im.filename]}
					class:lora-card-off={!selected[im.filename]}
				>
					<input
						type="checkbox"
						class="lora-card-check"
						checked={Boolean(selected[im.filename])}
						disabled={exporting || generating}
						onchange={(e) => {
							const on = (e.currentTarget as HTMLInputElement).checked;
							selected = { ...selected, [im.filename]: on };
						}}
					/>
					<span class="lora-thumb-wrap">
						<img src={apiImageSrc(im.url)} alt="" loading="lazy" decoding="async" />
					</span>
					<span class="lora-caption" title={im.caption}>{im.caption || '—'}</span>
				</label>
			{/each}
		</div>

		<div class="cover-btn-row lora-export-row">
			<button
				type="button"
				class="btn sm primary"
				disabled={exporting || generating || selectedCount === 0}
				onclick={() => void exportToKohya()}
			>
				{#if exporting}
					<span class="spinner"></span> Exporting…
				{:else}
					Export to Kohya
				{/if}
			</button>
		</div>
	{/if}

	{#if exportError}
		<p class="err small">{exportError}</p>
	{/if}

	{#if exportResult}
		<div class="lora-export-result">
			<p class="ok small">
				Copied <strong>{exportResult.copied}</strong> image(s). Estimated training:
				<strong>{exportResult.epochs}</strong> epoch(s), <strong>{exportResult.steps_estimate}</strong> steps.
			</p>
			<p class="muted small">Expected model output:</p>
			<p class="lora-path"><code class="wizard-code">{exportResult.output_model}</code></p>
			<div class="lora-cmd-block">
				<div class="lora-cmd-head">
					<span class="wizard-subcap" style="margin:0">Training command</span>
					<button type="button" class="btn sm" onclick={() => void copyTrainingCommand()}>
						{copyFeedback || 'Copy'}
					</button>
				</div>
				<pre class="lora-cmd-pre"><code>{exportResult.training_command}</code></pre>
			</div>
		</div>
	{/if}
</div>

<style>
	.lora-section {
		margin-top: 1rem;
	}
	.lora-lead {
		margin-top: 0.45rem;
	}
	.lora-input {
		width: 100%;
		max-width: 20rem;
		box-sizing: border-box;
		font-size: 0.85rem;
		padding: 0.35rem 0.5rem;
		border-radius: 6px;
		border: 1px solid #3c4043;
		background: #161a20;
		color: #e8eaed;
	}
	.lora-range {
		width: 12rem;
		max-width: 100%;
		accent-color: #1a73e8;
	}
	.lora-actions-top {
		margin-top: 0.5rem;
	}
	.lora-hint {
		margin: 0.35rem 0 0;
	}
	.lora-generate-status {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		margin-top: 0.65rem;
		padding: 0.65rem 0.75rem;
		border-radius: 8px;
		background: #1a3a5c33;
		border: 1px solid #2a4a6e;
		font-size: 0.82rem;
		color: #c4c7ce;
		line-height: 1.45;
	}
	.lora-dir {
		margin: 0.65rem 0 0;
		word-break: break-all;
	}
	.lora-toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 0.85rem;
		padding-top: 0.65rem;
		border-top: 1px solid #2a2f38;
	}
	.lora-count {
		font-size: 0.82rem;
		color: #9aa0a6;
		font-weight: 600;
	}
	.lora-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 0.65rem;
		margin-top: 0.65rem;
	}
	.lora-card {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		margin: 0;
		padding: 0.45rem;
		padding-top: 1.85rem;
		border-radius: 8px;
		cursor: pointer;
		transition:
			opacity 0.15s,
			border-color 0.15s,
			box-shadow 0.15s;
		font-size: 0.72rem;
		color: #9aa0a6;
	}
	.lora-card-on {
		border: 2px solid #81c995;
		background: #0f1a12;
		opacity: 1;
	}
	.lora-card-off {
		border: 2px solid #3c4043;
		background: #161a20;
		opacity: 0.55;
	}
	.lora-card-off:hover {
		opacity: 0.75;
	}
	.lora-card-check {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		width: 1.05rem;
		height: 1.05rem;
		accent-color: #81c995;
		cursor: pointer;
		z-index: 1;
	}
	.lora-thumb-wrap {
		display: block;
		width: 100%;
		aspect-ratio: 3 / 4;
		border-radius: 6px;
		overflow: hidden;
		background: #0b0e12;
		border: 1px solid #2a2f38;
	}
	.lora-thumb-wrap img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.lora-caption {
		display: -webkit-box;
		line-clamp: 3;
		-webkit-line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.35;
		word-break: break-word;
	}
	.lora-export-row {
		margin-top: 0.85rem;
	}
	.lora-export-result {
		margin-top: 0.85rem;
		padding-top: 0.65rem;
		border-top: 1px solid #2a2f38;
	}
	.lora-path {
		margin: 0.25rem 0 0.65rem;
		font-size: 0.78rem;
		word-break: break-all;
	}
	.lora-cmd-block {
		margin-top: 0.35rem;
	}
	.lora-cmd-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.35rem;
	}
	.lora-cmd-pre {
		margin: 0;
		padding: 0.65rem 0.75rem;
		border-radius: 8px;
		background: #0b0e12;
		border: 1px solid #2a2f38;
		overflow-x: auto;
		font-family: ui-monospace, monospace;
		font-size: 0.72rem;
		line-height: 1.4;
		color: #c4c7ce;
		white-space: pre-wrap;
		word-break: break-word;
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
	.hint {
		display: block;
		font-size: 0.82rem;
		color: #9aa0a6;
		margin-bottom: 0.3rem;
		line-height: 1.45;
	}
	.muted {
		color: #9aa0a6;
	}
	.small {
		font-size: 0.85rem;
	}
	.err {
		color: #f28b82;
		margin: 0.35rem 0 0;
	}
	.ok {
		color: #81c995;
		margin: 0.35rem 0 0;
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
		margin-top: 0;
	}
	.cover-btn-row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.wizard-section {
		border: 1px solid #2a3a50;
		border-radius: 8px;
		padding: 0.75rem;
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
		background: #111827;
	}
	.wizard-phase-tag {
		display: inline-block;
		margin-top: 0.15rem;
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
</style>
