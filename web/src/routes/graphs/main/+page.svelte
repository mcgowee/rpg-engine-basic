<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	type SubgraphListItem = {
		name: string;
	};

	type TransitionType = 'milestone' | 'rules' | 'turns' | 'location' | 'manual';

	type PhaseRow = {
		phaseName: string;
		subgraph: string;
		transitionType: TransitionType;
		condition: string;
	};

	const TRANSITION_TYPES: TransitionType[] = [
		'milestone',
		'rules',
		'turns',
		'location',
		'manual'
	];

	const CONDITION_HINTS: Record<TransitionType, string> = {
		milestone: 'Milestone string to match in player message',
		rules: 'Triggers when player wins via rules node',
		turns: 'Number of turns before transition',
		location: 'Location key the player must reach',
		manual: 'Text the player types to trigger transition'
	};

	let subgraphNames = $state<string[]>([]);
	let subgraphsReady = $state(false);
	let subgraphsError = $state<string | null>(null);

	let rowId = $state<number | null>(null);
	let nameReadOnly = $state(false);
	let pageLoadError = $state<string | null>(null);
	let hydrating = $state(false);

	let name = $state('');
	let description = $state('');
	let phases = $state<PhaseRow[]>([]);

	let saveErrors = $state<string[]>([]);
	let saving = $state(false);

	function normalizeAfterReorder(rows: PhaseRow[]): PhaseRow[] {
		return rows.map((p, i, arr) => {
			if (i === arr.length - 1) return { ...p };
			return {
				...p,
				transitionType: p.transitionType || 'turns',
				condition: p.condition !== undefined && p.condition !== '' ? p.condition : '10'
			};
		});
	}

	function buildDefinition(): { phases: object[] } {
		return {
			phases: phases.map((p, i, arr) => ({
				name: p.phaseName.trim(),
				subgraph: p.subgraph,
				transition:
					i === arr.length - 1 ? null : { type: p.transitionType, condition: p.condition }
			}))
		};
	}

	const definitionPreview = $derived.by(() => {
		try {
			return JSON.stringify(buildDefinition(), null, 2);
		} catch {
			return '{}';
		}
	});

	function blankForm() {
		const sg = subgraphNames[0] ?? '';
		name = '';
		description = '';
		phases = [{ phaseName: 'intro', subgraph: sg, transitionType: 'turns', condition: '10' }];
		rowId = null;
		nameReadOnly = false;
		pageLoadError = null;
	}

	function applyFromApi(body: {
		name?: string;
		description?: string;
		definition?: { phases?: object[] };
	}) {
		name = body.name ?? '';
		description = typeof body.description === 'string' ? body.description : '';
		const raw = body.definition?.phases;
		const arr = Array.isArray(raw) ? raw : [];
		phases = arr.map((ph: unknown, i: number, list: unknown[]) => {
			const p = ph as {
				name?: string;
				subgraph?: string;
				transition?: { type?: string; condition?: string } | null;
			};
			const isLast = i === list.length - 1;
			const tr = p.transition;
			return {
				phaseName: p.name ?? '',
				subgraph: p.subgraph ?? '',
				transitionType: (isLast
					? 'turns'
					: TRANSITION_TYPES.includes(tr?.type as TransitionType)
						? (tr!.type as TransitionType)
						: 'turns') as TransitionType,
				condition:
					!isLast && tr && typeof tr.condition === 'string' ? tr.condition : '10'
			};
		});
		if (phases.length === 0) {
			blankForm();
		}
	}

	let hydrateEpoch = 0;

	async function hydrateFromQuery(
		idParam: string | null,
		cloneParam: string | null,
		epoch: number
	) {
		pageLoadError = null;
		if (!idParam && !cloneParam) {
			if (epoch !== hydrateEpoch) return;
			hydrating = false;
			blankForm();
			return;
		}
		const raw = cloneParam ?? idParam;
		const num = raw ? parseInt(raw, 10) : NaN;
		if (!Number.isFinite(num)) {
			if (epoch !== hydrateEpoch) return;
			hydrating = false;
			pageLoadError = 'Invalid template id';
			blankForm();
			return;
		}
		hydrating = true;
		try {
			const r = await fetch(`/api/main-graph-templates/${num}`, { credentials: 'include' });
			if (epoch !== hydrateEpoch) return;
			if (!r.ok) {
				pageLoadError = `Failed to load template (${r.status})`;
				blankForm();
				return;
			}
			const body = (await r.json()) as {
				name?: string;
				description?: string;
				definition?: { phases?: object[] };
			};
			if (epoch !== hydrateEpoch) return;
			applyFromApi(body);
			if (cloneParam) {
				name = `${body.name ?? ''} (copy)`;
				rowId = null;
				nameReadOnly = false;
			} else {
				rowId = num;
				nameReadOnly = true;
			}
		} catch {
			if (epoch !== hydrateEpoch) return;
			pageLoadError = 'Network error loading template';
			blankForm();
		} finally {
			if (epoch === hydrateEpoch) hydrating = false;
		}
	}

	onMount(() => {
		void (async () => {
			subgraphsError = null;
			try {
				const r = await fetch('/api/subgraphs', { credentials: 'include' });
				if (!r.ok) {
					subgraphsError = `Failed to load subgraphs (${r.status})`;
					return;
				}
				const list = (await r.json()) as SubgraphListItem[];
				const names = Array.isArray(list)
					? list.map((x) => x.name).filter(Boolean)
					: [];
				subgraphNames = [...names].sort((a, b) => a.localeCompare(b));
			} catch {
				subgraphsError = 'Network error loading subgraphs';
			} finally {
				subgraphsReady = true;
			}
		})();
	});

	$effect(() => {
		if (!subgraphsReady) return;
		const idParam = page.url.searchParams.get('id');
		const cloneParam = page.url.searchParams.get('clone');
		const epoch = ++hydrateEpoch;
		void hydrateFromQuery(idParam, cloneParam, epoch);
	});

	function movePhaseUp(i: number) {
		if (i <= 0) return;
		const next = [...phases];
		[next[i - 1], next[i]] = [next[i], next[i - 1]];
		phases = normalizeAfterReorder(next);
	}

	function movePhaseDown(i: number) {
		if (i >= phases.length - 1) return;
		const next = [...phases];
		[next[i], next[i + 1]] = [next[i + 1], next[i]];
		phases = normalizeAfterReorder(next);
	}

	function addPhase() {
		const first = subgraphNames[0] ?? '';
		const promoted = phases.map((p, i, arr) => {
			if (i === arr.length - 1) {
				return {
					...p,
					transitionType: (p.transitionType || 'turns') as TransitionType,
					condition: p.condition || '10'
				};
			}
			return p;
		});
		phases = [
			...promoted,
			{
				phaseName: `phase_${promoted.length + 1}`,
				subgraph: first,
				transitionType: 'turns',
				condition: '10'
			}
		];
	}

	function removePhase(i: number) {
		if (phases.length <= 1) return;
		const next = phases.filter((_, j) => j !== i);
		phases = normalizeAfterReorder(next);
	}

	async function save() {
		saveErrors = [];
		const def = buildDefinition();
		if (!name.trim()) {
			saveErrors = ['Name is required.'];
			return;
		}
		saving = true;
		try {
			const payload = {
				name: name.trim(),
				description: description.trim(),
				definition: def
			};
			const url =
				rowId != null ? `/api/main-graph-templates/${rowId}` : '/api/main-graph-templates';
			const method = rowId != null ? 'PUT' : 'POST';
			const r = await fetch(url, {
				method,
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			const data = (await r.json().catch(() => ({}))) as {
				errors?: string[];
				error?: string;
			};
			if (!r.ok) {
				if (Array.isArray(data.errors) && data.errors.length) {
					saveErrors = data.errors;
				} else {
					saveErrors = [data.error ?? `Save failed (${r.status})`];
				}
				return;
			}
			await goto('/graphs');
		} catch {
			saveErrors = ['Network error while saving.'];
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Main Graph Editor — RPG Engine</title>
</svelte:head>

<section class="editor-page">
	<p class="back">
		<a href="/graphs">← Back to graphs</a>
	</p>

	{#if subgraphsError}
		<p class="err">{subgraphsError}</p>
	{/if}

	{#if !subgraphsReady}
		<p class="muted">Loading subgraphs…</p>
	{:else if hydrating}
		<p class="muted">Loading template…</p>
	{:else if pageLoadError}
		<p class="err">{pageLoadError}</p>
	{:else}
		<h1>
			{#if rowId != null}
				Edit main graph template
			{:else if page.url.searchParams.has('clone')}
				Clone main graph template
			{:else}
				New main graph template
			{/if}
		</h1>
		<div class="editor-hero">
			<img src="/images/graph-empty.png" alt="Graph blueprint illustration" />
		</div>

		{#if saveErrors.length}
			<div class="err-box" role="alert">
				<strong>Could not save:</strong>
				<ul>
					{#each saveErrors as e (e)}
						<li>{e}</li>
					{/each}
				</ul>
			</div>
		{/if}

		<div class="panels">
			<div class="panel form-panel">
				<div class="graph-section">
					<h2 class="sub">Name</h2>
					<input
						type="text"
						class="inp wide"
						bind:value={name}
						disabled={nameReadOnly}
						placeholder="e.g. my_campaign_flow"
						autocomplete="off"
					/>
					{#if nameReadOnly}
						<p class="hint">Name cannot be changed after creation.</p>
					{/if}
				</div>

				<div class="graph-section">
					<h2 class="sub">Description</h2>
					<input
						type="text"
						class="inp wide"
						bind:value={description}
						placeholder="Short description"
						autocomplete="off"
					/>
				</div>

				<div class="graph-section">
					<h2 class="sub">Phases</h2>
					<p class="hint">Order matters. The last phase has no transition.</p>

					{#each phases as phase, i (i)}
						<div class="phase-card">
							<div class="phase-head">
								<span class="phase-label">Phase {i + 1}</span>
								<div class="reorder">
									<button
										type="button"
										class="btn sm"
										disabled={i === 0}
										onclick={() => movePhaseUp(i)}>↑</button
									>
									<button
										type="button"
										class="btn sm"
										disabled={i === phases.length - 1}
										onclick={() => movePhaseDown(i)}>↓</button
									>
								</div>
							</div>

							<label class="block">
								<span class="lbl">Phase name</span>
								<input
									type="text"
									class="inp wide"
									bind:value={phase.phaseName}
									placeholder="e.g. exploration"
								/>
							</label>

							<label class="block">
								<span class="lbl">Subgraph</span>
								<select class="inp wide" bind:value={phase.subgraph}>
									{#if subgraphNames.length === 0}
										<option value="">— no subgraphs —</option>
									{:else}
										{#each subgraphNames as sn (sn)}
											<option value={sn}>{sn}</option>
										{/each}
									{/if}
								</select>
							</label>

							{#if i === phases.length - 1}
								<p class="final-note">Final phase (no transition)</p>
							{:else}
								<div class="transition-block">
									<label class="block">
										<span class="lbl">Transition type</span>
										<select class="inp wide" bind:value={phase.transitionType}>
											{#each TRANSITION_TYPES as t (t)}
												<option value={t}>{t}</option>
											{/each}
										</select>
									</label>
									<label class="block">
										<span class="lbl">Condition</span>
										<input
											type="text"
											class="inp wide"
											bind:value={phase.condition}
											placeholder={CONDITION_HINTS[phase.transitionType]}
										/>
									</label>
									<p class="hint small-hint">{CONDITION_HINTS[phase.transitionType]}</p>
								</div>
							{/if}

							<button
								type="button"
								class="btn sm danger"
								disabled={phases.length <= 1}
								onclick={() => removePhase(i)}>Remove phase</button
							>
						</div>
					{/each}

					<button type="button" class="btn" onclick={() => addPhase()}>Add phase</button>
				</div>

				<div class="actions">
					<button type="button" class="btn primary" disabled={saving} onclick={() => save()}>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<a class="cancel" href="/graphs">Cancel</a>
				</div>
			</div>

			<div class="panel json-panel">
				<h2 class="sub">JSON preview</h2>
				<pre class="json-pre">{definitionPreview}</pre>
			</div>
		</div>
	{/if}
</section>

<style>
	.editor-page { padding: 0 0.5rem 2rem; max-width: 1400px; }
	.back { margin: 0 0 1rem; }
	h1 { margin-top: 0; }
	.editor-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.editor-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.err-box { background: #2a1515; border: 1px solid #5c2020; padding: 0.75rem 1rem; margin-bottom: 1rem; border-radius: 8px; }
	.err-box ul { margin: 0.5rem 0 0; padding-left: 1.25rem; }
	.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; align-items: start; }
	@media (max-width: 960px) { .panels { grid-template-columns: 1fr; } }
	.panel { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; background: #1a1d23; }
	.json-panel { position: sticky; top: 0.5rem; }
	.json-pre { margin: 0; padding: 0.75rem; background: #0f1114; color: #d4d4d4; font-size: 0.75rem; overflow: auto; max-height: min(80vh, 900px); border-radius: 8px; border: 1px solid #2a2f38; white-space: pre-wrap; word-break: break-word; }
	.graph-section { margin-bottom: 1.5rem; }
	.sub { font-size: 1rem; margin: 0 0 0.5rem; }
	.hint { font-size: 0.82rem; color: #9aa0a6; margin: 0 0 0.5rem; }
	.small-hint { margin-top: 0.25rem; }
	.inp { padding: 0.35rem 0.5rem; font: inherit; }
	.inp.wide { width: 100%; box-sizing: border-box; }
	.block { display: block; margin-bottom: 0.65rem; }
	.lbl { display: block; font-size: 0.85rem; margin-bottom: 0.25rem; color: #9aa0a6; }
	.phase-card { border: 1px solid #2a2f38; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.phase-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
	.phase-label { font-weight: 600; font-size: 0.9rem; }
	.reorder { display: flex; gap: 0.25rem; }
	.final-note { font-size: 0.85rem; color: #9aa0a6; font-style: italic; margin: 0.5rem 0; }
	.transition-block { margin: 0.5rem 0; padding: 0.5rem; background: #13151a; border-radius: 6px; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.danger { border-color: #c5221f; color: #f28b82; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; }
	.cancel { color: #8ab4f8; }
	:global([data-theme="light"]) .panel,
	:global([data-theme="light"]) .phase-card { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .json-pre { background: #f8fafc; border-color: #dfe3e8; color: #334155; }
	:global([data-theme="light"]) .transition-block { background: #f8fafc; }
	:global([data-theme="light"]) .btn { background: #f8fafc; border-color: #d1d5db; color: #1f2937; }
	:global([data-theme="light"]) .btn:hover { border-color: #9ca3af; }
	:global([data-theme="light"]) .err-box { background: #fff1f2; border-color: #fecdd3; }
	:global([data-theme="light"]) .editor-hero { border-color: #dfe3e8; }
</style>
