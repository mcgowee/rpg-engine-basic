<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	type GraphDefinition = {
		name: string;
		description: string;
		nodes: string[];
		entry_point: { router: string; mapping: Record<string, string> };
		edges: { from: string; to: string }[];
		conditional_edges: {
			from: string;
			router: string;
			mapping: Record<string, string>;
		}[];
	};

	let registryNodes = $state<string[]>([]);
	let registryRouters = $state<string[]>([]);
	let registryReady = $state(false);
	let registryError = $state<string | null>(null);

	let rowId = $state<number | null>(null);
	let nameReadOnly = $state(false);
	let pageLoadError = $state<string | null>(null);
	let hydrating = $state(false);

	let name = $state('');
	let description = $state('');
	let selectedNodes = $state<string[]>([]);
	let entryRouter = $state('');
	let entryMappingRows = $state<{ k: string; v: string }[]>([{ k: '', v: '' }]);
	let edgeRows = $state<{ from: string; to: string }[]>([{ from: '', to: '' }]);
	let condEdgeRows = $state<
		{ from: string; router: string; mappingRows: { k: string; v: string }[] }[]
	>([]);

	let saveErrors = $state<string[]>([]);
	let saving = $state(false);

	type TraceStep = {
		node: string;
		updates: Record<string, unknown>;
		state_after: Record<string, unknown>;
	};

	type TestApiResult = {
		initial_state?: unknown;
		trace?: TraceStep[];
		error?: string;
	};

	let testMessage = $state('I look around the room');
	let testRunning = $state(false);
	let testResult = $state<TestApiResult | null>(null);
	let testClientError = $state<string | null>(null);

	type StoryListItem = { id: number; title: string };
	let testStateSource = $state<'dummy' | 'story'>('dummy');
	let storiesForTest = $state<StoryListItem[]>([]);
	let storiesLoading = $state(false);
	let storiesLoadError = $state<string | null>(null);
	let testStoryIdStr = $state('');

	const nodeOptionsForDropdown = $derived(
		[...selectedNodes].sort((a, b) => a.localeCompare(b))
	);
	const toOptions = $derived([...nodeOptionsForDropdown, '__end__']);

	const definitionPreview = $derived.by(() => {
		try {
			return JSON.stringify(buildDefinition(), null, 2);
		} catch {
			return '{}';
		}
	});

	function toggleNode(node: string, checked: boolean) {
		if (checked) {
			if (!selectedNodes.includes(node)) selectedNodes = [...selectedNodes, node];
		} else {
			selectedNodes = selectedNodes.filter((n) => n !== node);
		}
	}

	function buildDefinition(): GraphDefinition {
		const entry_mapping: Record<string, string> = {};
		for (const row of entryMappingRows) {
			const k = row.k.trim();
			if (k) entry_mapping[k] = row.v.trim();
		}
		const edges = edgeRows
			.filter((e) => e.from && e.to)
			.map((e) => ({ from: e.from, to: e.to }));
		const conditional_edges = condEdgeRows
			.filter((ce) => ce.from && ce.router)
			.map((ce) => {
				const m: Record<string, string> = {};
				for (const r of ce.mappingRows) {
					const k = r.k.trim();
					if (k) m[k] = r.v.trim();
				}
				return { from: ce.from, router: ce.router, mapping: m };
			});
		return {
			name: name.trim(),
			description: description.trim(),
			nodes: [...selectedNodes].sort((a, b) => a.localeCompare(b)),
			entry_point: { router: entryRouter, mapping: entry_mapping },
			edges,
			conditional_edges
		};
	}

	function applyDefinition(def: GraphDefinition) {
		name = def.name;
		description = typeof def.description === 'string' ? def.description : '';
		selectedNodes = Array.isArray(def.nodes) ? [...def.nodes] : [];
		entryRouter = def.entry_point?.router ?? '';
		const em = def.entry_point?.mapping ?? {};
		const emEntries = Object.entries(em);
		entryMappingRows =
			emEntries.length > 0
				? emEntries.map(([k, v]) => ({ k, v: String(v) }))
				: [{ k: '', v: '' }];
		const eds = def.edges ?? [];
		edgeRows =
			eds.length > 0
				? eds.map((e) => ({ from: e.from, to: e.to }))
				: [{ from: '', to: '' }];
		const ces = def.conditional_edges ?? [];
		condEdgeRows = ces.map((ce) => ({
			from: ce.from,
			router: ce.router,
			mappingRows:
				Object.keys(ce.mapping ?? {}).length > 0
					? Object.entries(ce.mapping).map(([k, v]) => ({ k, v: String(v) }))
					: [{ k: '', v: '' }]
		}));
	}

	function blankForm() {
		name = '';
		description = '';
		selectedNodes = [];
		entryRouter = registryRouters[0] ?? '';
		entryMappingRows = [{ k: '', v: '' }];
		edgeRows = [{ from: '', to: '' }];
		condEdgeRows = [];
		rowId = null;
		nameReadOnly = false;
		pageLoadError = null;
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
			pageLoadError = 'Invalid subgraph id';
			blankForm();
			return;
		}
		hydrating = true;
		try {
			const r = await fetch(`/api/subgraphs/${num}`, { credentials: 'include' });
			if (epoch !== hydrateEpoch) return;
			if (!r.ok) {
				pageLoadError = `Failed to load subgraph (${r.status})`;
				blankForm();
				return;
			}
			const body = (await r.json()) as { definition?: GraphDefinition };
			if (epoch !== hydrateEpoch) return;
			const def = body.definition;
			if (!def || typeof def !== 'object') {
				pageLoadError = 'Invalid response';
				blankForm();
				return;
			}
			applyDefinition(def);
			if (cloneParam) {
				name = `${def.name} (copy)`;
				rowId = null;
				nameReadOnly = false;
			} else {
				rowId = num;
				nameReadOnly = true;
			}
		} catch {
			if (epoch !== hydrateEpoch) return;
			pageLoadError = 'Network error loading subgraph';
			blankForm();
		} finally {
			if (epoch === hydrateEpoch) hydrating = false;
		}
	}

	onMount(() => {
		void (async () => {
			registryError = null;
			try {
				const r = await fetch('/api/graph-registry', { credentials: 'include' });
				if (!r.ok) {
					registryError = `Failed to load graph registry (${r.status})`;
					return;
				}
				const j = (await r.json()) as { nodes?: string[]; routers?: Record<string, string[]> | string[] };
				registryNodes = Array.isArray(j.nodes) ? j.nodes : [];
				if (Array.isArray(j.routers)) {
					registryRouters = j.routers;
				} else if (j.routers && typeof j.routers === 'object') {
					registryRouters = Object.keys(j.routers);
				} else {
					registryRouters = [];
				}
				if (!entryRouter && registryRouters.length) entryRouter = registryRouters[0];
			} catch {
				registryError = 'Network error loading graph registry';
			} finally {
				registryReady = true;
			}
		})();
	});

	$effect(() => {
		if (!registryReady) return;
		const idParam = page.url.searchParams.get('id');
		const cloneParam = page.url.searchParams.get('clone');
		const epoch = ++hydrateEpoch;
		void hydrateFromQuery(idParam, cloneParam, epoch);
	});

	const namePattern = '^[a-zA-Z0-9_-]+$';

	async function save() {
		saveErrors = [];
		const def = buildDefinition();
		if (!def.name.trim()) {
			saveErrors = ['Name is required.'];
			return;
		}
		if (!new RegExp(namePattern).test(def.name)) {
			saveErrors = ['Name must use only letters, numbers, underscores, and hyphens.'];
			return;
		}
		if (!def.nodes.length) {
			saveErrors = ['Select at least one node.'];
			return;
		}
		saving = true;
		try {
			const url = rowId != null ? `/api/subgraphs/${rowId}` : '/api/subgraphs';
			const method = rowId != null ? 'PUT' : 'POST';
			const r = await fetch(url, {
				method,
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(def)
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

	function jsonForDisplay(obj: unknown, maxHistoryItems = 16): string {
		if (obj !== null && typeof obj === 'object' && !Array.isArray(obj) && 'history' in obj) {
			const o = { ...(obj as Record<string, unknown>) };
			const h = o.history;
			if (Array.isArray(h) && h.length > maxHistoryItems) {
				const rest = h.length - maxHistoryItems;
				o.history = [...h.slice(0, maxHistoryItems), `… (${rest} more entr${rest === 1 ? 'y' : 'ies'} truncated for display)`];
			}
			return JSON.stringify(o, null, 2);
		}
		return JSON.stringify(obj, null, 2);
	}

	function updatesLooksEmpty(u: Record<string, unknown>): boolean {
		return Object.keys(u).length === 0;
	}

	async function loadStoriesForTest() {
		if (storiesForTest.length > 0 || storiesLoading) return;
		storiesLoading = true;
		storiesLoadError = null;
		try {
			// Fetch own stories and public stories in parallel
			const [ownR, pubR] = await Promise.all([
				fetch('/api/stories', { credentials: 'include' }),
				fetch('/api/stories/public', { credentials: 'include' }),
			]);
			const ownJ = await ownR.json().catch(() => []);
			const pubJ = await pubR.json().catch(() => ({}));
			const ownList = Array.isArray(ownJ) ? ownJ : [];
			const pubList = Array.isArray(pubJ) ? pubJ : (pubJ.stories ?? []);

			const seen = new Set<number>();
			const next: StoryListItem[] = [];
			for (const raw of [...ownList, ...pubList]) {
				const s = raw as { id?: unknown; title?: unknown };
				const id = typeof s.id === 'number' ? s.id : Number(s.id);
				if (!Number.isFinite(id) || id <= 0 || seen.has(id)) continue;
				seen.add(id);
				const title =
					typeof s.title === 'string' && s.title.trim() !== ''
						? s.title
						: `Story ${id}`;
				next.push({ id, title });
			}
			storiesForTest = next;
		} catch {
			storiesLoadError = 'Network error loading stories';
		} finally {
			storiesLoading = false;
		}
	}

	async function runSubgraphTest() {
		if (rowId == null) return;
		const msg = testMessage.trim();
		if (!msg) {
			testClientError = 'Enter a test message.';
			return;
		}
		if (testStateSource === 'story') {
			const sid = parseInt(testStoryIdStr, 10);
			if (!Number.isFinite(sid) || sid <= 0) {
				testClientError = 'Select a story.';
				return;
			}
		}
		testClientError = null;
		testRunning = true;
		testResult = null;
		try {
			const body: { message: string; story_id?: number } = { message: msg };
			if (testStateSource === 'story') {
				body.story_id = parseInt(testStoryIdStr, 10);
			}
			const r = await fetch(`/api/subgraphs/${rowId}/test`, {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			const j = (await r.json().catch(() => ({}))) as TestApiResult & {
				error?: string;
				errors?: string[];
			};
			if (!r.ok) {
				if (Array.isArray(j.errors) && j.errors.length) {
					testClientError = j.errors.join('; ');
				} else {
					testClientError = j.error ?? `Test failed (${r.status})`;
				}
				return;
			}
			testResult = j;
		} catch {
			testClientError = 'Network error';
		} finally {
			testRunning = false;
		}
	}

	$effect(() => {
		if (testStateSource === 'story') {
			void loadStoriesForTest();
		}
	});
</script>

<svelte:head>
	<title>Subgraph Editor — RPG Engine</title>
</svelte:head>

<section class="editor-page">
	<p class="back">
		<a href="/graphs">← Back to subgraphs</a>
	</p>

	{#if registryError}
		<p class="err">{registryError}</p>
	{/if}

	{#if !registryReady}
		<p class="muted">Loading registry…</p>
	{:else if hydrating}
		<p class="muted">Loading subgraph…</p>
	{:else if pageLoadError}
		<p class="err">{pageLoadError}</p>
	{:else}
		<h1>
			{#if rowId != null}
				Edit subgraph
			{:else if page.url.searchParams.has('clone')}
				Clone subgraph
			{:else}
				New subgraph
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
						placeholder="e.g. my_subgraph"
						autocomplete="off"
						pattern={namePattern}
						title="Letters, numbers, underscores, and hyphens only"
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
					<h2 class="sub">Nodes</h2>
					<p class="hint">Edges and mappings only list nodes you include here.</p>
					<div class="node-grid">
						{#each registryNodes as node (node)}
							<label class="chk">
								<input
									type="checkbox"
									checked={selectedNodes.includes(node)}
									onchange={(e) =>
										toggleNode(node, (e.currentTarget as HTMLInputElement).checked)}
								/>
								{node}
							</label>
						{/each}
					</div>
				</div>

				<div class="graph-section">
					<h2 class="sub">Entry point</h2>
					<label class="row block">
						<span class="lbl">Router</span>
						<select class="inp wide" bind:value={entryRouter}>
							{#each registryRouters as r (r)}
								<option value={r}>{r}</option>
							{/each}
						</select>
					</label>
					<p class="hint">Mapping: router return value → next node (or __end__).</p>
					<div class="map-header" aria-hidden="true">
						<span>Router returns</span>
						<span class="mid"></span>
						<span>Goes to</span>
					</div>
					{#each entryMappingRows as row, i (i)}
						<div class="map-row">
							<select class="inp" bind:value={row.k} aria-label="Router returns">
								<option value="">— router return —</option>
								{#if row.k && !toOptions.includes(row.k)}
									<option value={row.k}>{row.k} (not in graph)</option>
								{/if}
								{#each toOptions as t (t)}
									<option value={t}>{t}</option>
								{/each}
							</select>
							<span class="arrow">→</span>
							<select class="inp" bind:value={row.v} aria-label="Target node">
								<option value="">— choose —</option>
								{#each toOptions as t (t)}
									<option value={t}>{t}</option>
								{/each}
							</select>
							<button
								type="button"
								class="btn sm"
								onclick={() => {
									entryMappingRows = entryMappingRows.filter((_, j) => j !== i);
									if (entryMappingRows.length === 0) entryMappingRows = [{ k: '', v: '' }];
								}}>Remove</button
							>
						</div>
					{/each}
					<button
						type="button"
						class="btn"
						onclick={() => {
							entryMappingRows = [...entryMappingRows, { k: '', v: '' }];
						}}>Add mapping row</button
					>
				</div>

				<div class="graph-section">
					<h2 class="sub">Unconditional edges</h2>
					<p class="hint">Static edges. Use <code>__end__</code> to stop.</p>
					{#each edgeRows as row, i (i)}
						<div class="map-row">
							<select class="inp" bind:value={row.from}>
								<option value="">— from —</option>
								{#each nodeOptionsForDropdown as n (n)}
									<option value={n}>{n}</option>
								{/each}
							</select>
							<span class="arrow">→</span>
							<select class="inp" bind:value={row.to}>
								<option value="">— to —</option>
								{#each toOptions as t (t)}
									<option value={t}>{t}</option>
								{/each}
							</select>
							<button
								type="button"
								class="btn sm"
								onclick={() => {
									edgeRows = edgeRows.filter((_, j) => j !== i);
									if (edgeRows.length === 0) edgeRows = [{ from: '', to: '' }];
								}}>Remove</button
							>
						</div>
					{/each}
					<button
						type="button"
						class="btn"
						onclick={() => {
							edgeRows = [...edgeRows, { from: '', to: '' }];
						}}>Add edge</button
					>
				</div>

				<div class="graph-section">
					<h2 class="sub">Conditional edges</h2>
					<p class="hint">Per source node: router chooses the next step.</p>
					{#each condEdgeRows as ce, ci (ci)}
						<div class="cond-card">
							<div class="map-row">
								<label class="inline">
									From
									<select
										class="inp"
										value={ce.from}
										onchange={(e) => {
											const v = (e.currentTarget as HTMLSelectElement).value;
											condEdgeRows = condEdgeRows.map((c, j) =>
												j === ci ? { ...c, from: v } : c
											);
										}}
									>
										<option value="">— from —</option>
										{#each nodeOptionsForDropdown as n (n)}
											<option value={n}>{n}</option>
										{/each}
									</select>
								</label>
								<label class="inline">
									Router
									<select
										class="inp"
										value={ce.router}
										onchange={(e) => {
											const v = (e.currentTarget as HTMLSelectElement).value;
											condEdgeRows = condEdgeRows.map((c, j) =>
												j === ci ? { ...c, router: v } : c
											);
										}}
									>
										<option value="">— router —</option>
										{#each registryRouters as r (r)}
											<option value={r}>{r}</option>
										{/each}
									</select>
								</label>
								<button
									type="button"
									class="btn sm danger"
									onclick={() => {
										condEdgeRows = condEdgeRows.filter((_, j) => j !== ci);
									}}>Remove edge</button
								>
							</div>
							<div class="nested">
								<div class="map-header small" aria-hidden="true">
									<span>Router returns</span>
									<span class="mid"></span>
									<span>Goes to</span>
								</div>
								{#each ce.mappingRows as mr, mi (mi)}
									<div class="map-row">
										<select
											class="inp"
											value={mr.k}
											aria-label="Router returns"
											onchange={(e) => {
												const keyVal = (e.currentTarget as HTMLSelectElement).value;
												condEdgeRows = condEdgeRows.map((c, j) =>
													j !== ci
														? c
														: {
																...c,
																mappingRows: c.mappingRows.map((x, k) =>
																	k === mi ? { ...x, k: keyVal } : x
																)
															}
												);
											}}
										>
											<option value="">— router return —</option>
											{#if mr.k && !toOptions.includes(mr.k)}
												<option value={mr.k}>{mr.k} (not in graph)</option>
											{/if}
											{#each toOptions as t (t)}
												<option value={t}>{t}</option>
											{/each}
										</select>
										<span class="arrow">→</span>
										<select
											class="inp"
											value={mr.v}
											aria-label="Goes to"
											onchange={(e) => {
												const toVal = (e.currentTarget as HTMLSelectElement).value;
												condEdgeRows = condEdgeRows.map((c, j) =>
													j !== ci
														? c
														: {
																...c,
																mappingRows: c.mappingRows.map((x, k) =>
																	k === mi ? { ...x, v: toVal } : x
																)
															}
												);
											}}
										>
											<option value="">— to —</option>
											{#each toOptions as t (t)}
												<option value={t}>{t}</option>
											{/each}
										</select>
										<button
											type="button"
											class="btn sm"
											onclick={() => {
												condEdgeRows = condEdgeRows.map((c, j) => {
													if (j !== ci) return c;
													const mappingRows = c.mappingRows.filter((_, k) => k !== mi);
													return {
														...c,
														mappingRows:
															mappingRows.length > 0 ? mappingRows : [{ k: '', v: '' }]
													};
												});
											}}>Remove</button
										>
									</div>
								{/each}
								<button
									type="button"
									class="btn"
									onclick={() => {
										condEdgeRows = condEdgeRows.map((c, j) =>
											j !== ci
												? c
												: { ...c, mappingRows: [...c.mappingRows, { k: '', v: '' }] }
										);
									}}>Add mapping row</button
								>
							</div>
						</div>
					{/each}
					<button
						type="button"
						class="btn"
						onclick={() => {
							condEdgeRows = [
								...condEdgeRows,
								{ from: '', router: '', mappingRows: [{ k: '', v: '' }] }
							];
						}}>Add conditional edge</button
					>
				</div>

				<div class="actions">
					<button type="button" class="btn primary" disabled={saving} onclick={() => save()}>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<a class="cancel" href="/graphs">Cancel</a>
				</div>

				<div class="graph-section test-section">
					<h2 class="sub">Test</h2>
					{#if rowId == null}
						<p class="hint">Save the subgraph first to enable testing.</p>
					{:else}
						<p class="hint test-note">
							Tests run against the <strong>last saved</strong> version in the database — not unsaved edits
							in this form.
						</p>
						<fieldset class="test-mode-fieldset">
							<legend class="lbl test-mode-legend">Initial state source</legend>
							<div class="test-mode-radios">
								<label class="chk">
									<input
										type="radio"
										bind:group={testStateSource}
										value="dummy"
										disabled={testRunning}
									/>
									Dummy state
								</label>
								<label class="chk">
									<input
										type="radio"
										bind:group={testStateSource}
										value="story"
										disabled={testRunning}
									/>
									From story
								</label>
							</div>
						</fieldset>
						{#if testStateSource === 'story'}
							{#if storiesLoading}
								<p class="hint">Loading stories…</p>
							{:else if storiesLoadError}
								<p class="err test-err">{storiesLoadError}</p>
								<button
									type="button"
									class="btn sm"
									disabled={testRunning}
									onclick={() => {
										storiesForTest = [];
										void loadStoriesForTest();
									}}>Retry</button
								>
							{:else}
								<label class="row block">
									<span class="lbl">Story</span>
									<select class="inp wide" bind:value={testStoryIdStr} disabled={testRunning}>
										<option value="">Select a story…</option>
										{#each storiesForTest as s (s.id)}
											<option value={String(s.id)}>{s.title}</option>
										{/each}
									</select>
								</label>
							{/if}
						{/if}
						<label class="row block">
							<span class="lbl">Test message</span>
							<textarea
								class="inp wide ta"
								rows="2"
								placeholder="e.g. I look around the room"
								bind:value={testMessage}
								disabled={testRunning}
							></textarea>
						</label>
						<button
							type="button"
							class="btn"
							disabled={testRunning}
							onclick={() => runSubgraphTest()}
						>
							{testRunning ? 'Running…' : 'Run Test'}
						</button>
						{#if testClientError}<p class="err test-err">{testClientError}</p>{/if}

						{#if testResult}
							<div class="test-results">
								<details class="test-details">
									<summary>Initial state</summary>
									<pre class="trace-pre">{jsonForDisplay(testResult.initial_state)}</pre>
								</details>

								{#each testResult.trace ?? [] as step, si (si)}
									<div class="trace-step">
										<h3 class="trace-node">{step.node}</h3>
										<p class="trace-label">Updates</p>
										{#if updatesLooksEmpty(step.updates ?? {})}
											<p class="muted trace-empty">No state changes</p>
										{:else}
											<pre class="trace-pre trace-pre-highlight">{jsonForDisplay(step.updates)}</pre>
										{/if}
										<details class="test-details">
											<summary>Full state after</summary>
											<pre class="trace-pre">{jsonForDisplay(step.state_after)}</pre>
										</details>
									</div>
								{/each}

								{#if testResult.error}
									<p class="err trace-fatal">{testResult.error}</p>
								{/if}
							</div>
						{/if}
					{/if}
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
	.inp { padding: 0.35rem 0.5rem; font: inherit; }
	.inp.wide { width: 100%; box-sizing: border-box; }
	.row.block { display: block; margin-bottom: 0.5rem; }
	.lbl { display: block; font-size: 0.85rem; margin-bottom: 0.25rem; color: #9aa0a6; }
	.node-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr)); gap: 0.35rem 0.75rem; }
	.chk { display: flex; align-items: center; gap: 0.35rem; font-size: 0.9rem; }
	.map-header { display: grid; grid-template-columns: 1fr auto 1fr; gap: 0.5rem; font-size: 0.75rem; color: #9aa0a6; margin: 0.5rem 0 0.25rem; }
	.map-header.small { font-size: 0.7rem; }
	.map-header .mid { width: 1.5rem; }
	.map-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; margin-bottom: 0.35rem; }
	.arrow { color: #9aa0a6; }
	.inline { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.85rem; }
	.cond-card { border: 1px solid #2a2f38; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.75rem; background: #1a1d23; }
	.nested { margin-top: 0.5rem; padding-left: 0.5rem; border-left: 2px solid #2a2f38; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.danger { border-color: #c5221f; color: #f28b82; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; }
	.cancel { color: #8ab4f8; }
	.test-section { margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2f38; }
	.test-note strong { font-weight: 600; }
	.ta { resize: vertical; min-height: 2.5rem; font-family: inherit; }
	.test-err { margin-top: 0.75rem; }
	.test-results { margin-top: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
	.test-details { margin: 0.35rem 0 0; }
	.test-details summary { cursor: pointer; font-size: 0.9rem; }
	.trace-step { border: 1px solid #2a2f38; border-radius: 8px; padding: 0.75rem 1rem; background: #1a1d23; }
	.trace-node { margin: 0 0 0.5rem; font-size: 1rem; font-weight: 700; }
	.trace-label { margin: 0 0 0.25rem; font-size: 0.8rem; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.03em; }
	.trace-empty { margin: 0 0 0.5rem; font-size: 0.9rem; color: #9aa0a6; }
	.trace-pre { margin: 0; padding: 0.5rem 0.65rem; background: #0f1114; color: #d4d4d4; font-size: 0.72rem; line-height: 1.35; overflow: auto; max-height: 14rem; border-radius: 8px; border: 1px solid #2a2f38; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, monospace; }
	.trace-pre-highlight { border-color: #81c995; box-shadow: 0 0 0 1px rgba(129, 201, 149, 0.15); }
	.trace-fatal { margin-top: 0.5rem; padding: 0.5rem 0.65rem; background: #2a1515; border-radius: 8px; color: #f28b82; }
	.test-mode-fieldset { border: 1px solid #2a2f38; border-radius: 8px; padding: 0.65rem 0.85rem 0.85rem; margin: 0 0 0.75rem; background: #1a1d23; }
	.test-mode-legend { padding: 0 0.35rem; }
	.test-mode-radios { display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem; }
	:global([data-theme="light"]) .panel,
	:global([data-theme="light"]) .cond-card,
	:global([data-theme="light"]) .trace-step,
	:global([data-theme="light"]) .test-mode-fieldset { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .json-pre,
	:global([data-theme="light"]) .trace-pre { background: #f8fafc; border-color: #dfe3e8; color: #334155; }
	:global([data-theme="light"]) .nested { border-left-color: #dfe3e8; }
	:global([data-theme="light"]) .test-section { border-top-color: #dfe3e8; }
	:global([data-theme="light"]) .btn { background: #f8fafc; border-color: #d1d5db; color: #1f2937; }
	:global([data-theme="light"]) .btn:hover { border-color: #9ca3af; }
	:global([data-theme="light"]) .err-box,
	:global([data-theme="light"]) .trace-fatal { background: #fff1f2; border-color: #fecdd3; }
	:global([data-theme="light"]) .editor-hero { border-color: #dfe3e8; }
</style>
