<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type SubgraphRow = {
		id: number;
		user_id: number;
		name: string;
		description: string;
		is_public: boolean;
		is_builtin: boolean;
		created_at: string;
		updated_at: string;
		node_count: number;
		owned: boolean;
		/** false when the server could not compile this subgraph (e.g. missing nodes). */
		compiled?: boolean;
	};

	type MainTemplateRow = {
		id: number;
		user_id: number;
		name: string;
		description: string;
		is_public: boolean;
		created_at: string;
		updated_at: string;
		phase_count: number;
		owned: boolean;
	};

	let items = $state<SubgraphRow[]>([]);
	let templates = $state<MainTemplateRow[]>([]);
	let loading = $state(true);
	let subgraphError = $state<string | null>(null);
	let templateError = $state<string | null>(null);

	async function load() {
		loading = true;
		subgraphError = null;
		templateError = null;
		try {
			const [rs, rt] = await Promise.all([
				fetch('/api/subgraphs', { credentials: 'include' }),
				fetch('/api/main-graph-templates', { credentials: 'include' })
			]);
			if (rs.ok) {
				const data = await rs.json();
				items = Array.isArray(data) ? data : [];
			} else {
				subgraphError = `Failed to load subgraphs (${rs.status})`;
				items = [];
			}
			if (rt.ok) {
				const data = await rt.json();
				templates = Array.isArray(data) ? data : [];
			} else {
				templateError = `Failed to load main graph templates (${rt.status})`;
				templates = [];
			}
		} catch {
			subgraphError = subgraphError || 'Network error';
			templateError = templateError || 'Network error';
			items = [];
			templates = [];
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void load();
	});

	function formatWhen(s: string) {
		try {
			return new Date(s).toLocaleString();
		} catch {
			return s;
		}
	}

	async function deleteSubgraph(row: SubgraphRow) {
		if (!confirm(`Delete subgraph "${row.name}"? This cannot be undone.`)) return;
		try {
			const r = await fetch(`/api/subgraphs/${row.id}`, {
				method: 'DELETE',
				credentials: 'include'
			});
			if (!r.ok) {
				const j = (await r.json().catch(() => ({}))) as { error?: string };
				alert(j.error ?? `Delete failed (${r.status})`);
				return;
			}
			items = items.filter((x) => x.id !== row.id);
		} catch {
			alert('Network error');
		}
	}

	async function deleteTemplate(row: MainTemplateRow) {
		if (!confirm(`Delete main graph template "${row.name}"? This cannot be undone.`)) return;
		try {
			const r = await fetch(`/api/main-graph-templates/${row.id}`, {
				method: 'DELETE',
				credentials: 'include'
			});
			if (!r.ok) {
				const j = (await r.json().catch(() => ({}))) as { error?: string };
				alert(j.error ?? `Delete failed (${r.status})`);
				return;
			}
			templates = templates.filter((x) => x.id !== row.id);
		} catch {
			alert('Network error');
		}
	}
</script>

<svelte:head>
	<title>Graphs</title>
</svelte:head>

{#if loading}
	<p class="muted hub hub-loading">Loading…</p>
{:else}
<section class="hub">
	<div class="head-row">
		<h1>Subgraphs</h1>
		<button type="button" class="btn primary" onclick={() => goto('/graphs/subgraph')}>
			New Subgraph
		</button>
	</div>

		{#if subgraphError}
			<p class="err">{subgraphError}</p>
			<button type="button" class="btn" onclick={() => load()}>Retry</button>
		{:else if items.length === 0}
			<p class="muted">No subgraphs yet.</p>
		{:else}
			<div class="table-wrap">
				<table class="tbl">
					<thead>
						<tr>
							<th>Name</th>
							<th>Description</th>
							<th>Nodes</th>
							<th>Flags</th>
							<th>Yours</th>
							<th>Created</th>
							<th>Updated</th>
							<th>Actions</th>
						</tr>
					</thead>
					<tbody>
						{#each items as row (row.id)}
							<tr
								class:builtin-row={row.is_builtin}
								class:not-compiled-row={row.compiled === false}
							>
								<td class="mono">{row.name}</td>
								<td>{row.description || '—'}</td>
								<td>{row.node_count}</td>
								<td>
									<div class="flags">
										{#if row.is_builtin}
											<span class="badge">[builtin]</span>
										{/if}
										{#if row.compiled === false}
											<span
												class="badge warn"
												title="This subgraph did not compile on the server (often missing nodes in NODE_REGISTRY). It cannot run until fixed or nodes are ported."
												>[not compiled]</span
											>
										{/if}
										{#if !row.is_builtin && row.compiled !== false}
											<span class="dash">—</span>
										{/if}
									</div>
								</td>
								<td>{row.owned ? 'yes' : 'no'}</td>
								<td class="small">{formatWhen(row.created_at)}</td>
								<td class="small">{formatWhen(row.updated_at)}</td>
								<td class="actions">
									{#if row.owned && !row.is_builtin}
										<button
											type="button"
											class="linkish"
											onclick={() => goto(`/graphs/subgraph?id=${row.id}`)}
										>
											Edit
										</button>
									{/if}
									<button
										type="button"
										class="linkish"
										onclick={() => goto(`/graphs/subgraph?clone=${row.id}`)}
									>
										Clone
									</button>
									{#if row.owned && !row.is_builtin}
										<button type="button" class="linkish danger" onclick={() => deleteSubgraph(row)}>
											Delete
										</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
</section>

<hr class="sep" />

<section class="hub hub-templates">
	<div class="head-row">
		<h2>Main Graph Templates</h2>
		<button type="button" class="btn primary" onclick={() => goto('/graphs/main')}>
			New Main Graph
		</button>
	</div>

		{#if templateError}
			<p class="err">{templateError}</p>
			<button type="button" class="btn" onclick={() => load()}>Retry</button>
		{:else if templates.length === 0}
			<p class="muted">No main graph templates yet.</p>
		{:else}
			<div class="table-wrap">
				<table class="tbl">
					<thead>
						<tr>
							<th>Name</th>
							<th>Description</th>
							<th>Phases</th>
							<th>Yours</th>
							<th>Created</th>
							<th>Updated</th>
							<th>Actions</th>
						</tr>
					</thead>
					<tbody>
						{#each templates as row (row.id)}
							<tr>
								<td class="mono">{row.name}</td>
								<td>{row.description || '—'}</td>
								<td>{row.phase_count}</td>
								<td>{row.owned ? 'yes' : 'no'}</td>
								<td class="small">{formatWhen(row.created_at)}</td>
								<td class="small">{formatWhen(row.updated_at)}</td>
								<td class="actions">
									{#if row.owned}
										<button
											type="button"
											class="linkish"
											onclick={() => goto(`/graphs/main?id=${row.id}`)}
										>
											Edit
										</button>
									{/if}
									<button
										type="button"
										class="linkish"
										onclick={() => goto(`/graphs/main?clone=${row.id}`)}
									>
										Clone
									</button>
									{#if row.owned}
										<button type="button" class="linkish danger" onclick={() => deleteTemplate(row)}>
											Delete
										</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
</section>
{/if}

<style>
	.hub {
		padding: 0 0.5rem;
		max-width: 1200px;
	}
	.hub-loading {
		margin: 1rem 0.5rem;
	}
	.hub-templates {
		margin-top: 0.5rem;
	}
	.sep {
		margin: 2rem 0.5rem;
		border: none;
		border-top: 1px solid #ccc;
		max-width: 1200px;
	}
	.head-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}
	.hub-templates h2 {
		margin: 0;
		font-size: 1.35rem;
	}
	.muted {
		color: #666;
	}
	.err {
		color: #b00020;
	}
	.table-wrap {
		overflow-x: auto;
	}
	.tbl {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	.tbl th,
	.tbl td {
		border: 1px solid #ccc;
		padding: 0.4rem 0.5rem;
		text-align: left;
		vertical-align: top;
	}
	.tbl th {
		background: #f5f5f5;
	}
	.builtin-row {
		background: #f9f9ef;
	}
	.mono {
		font-family: ui-monospace, monospace;
	}
	.small {
		font-size: 0.8rem;
		white-space: nowrap;
	}
	.flags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		align-items: center;
	}
	.badge {
		font-size: 0.85rem;
		font-weight: 600;
	}
	.badge.warn {
		color: #a34d00;
		font-weight: 600;
	}
	.dash {
		color: #888;
	}
	.not-compiled-row {
		background: #fff8f0;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.btn {
		padding: 0.35rem 0.75rem;
		cursor: pointer;
		border: 1px solid #999;
		background: #fff;
		border-radius: 4px;
	}
	.btn.primary {
		background: #1a1a8c;
		color: #fff;
		border-color: #1a1a8c;
	}
	.linkish {
		background: none;
		border: none;
		padding: 0;
		color: #0066cc;
		cursor: pointer;
		text-decoration: underline;
		font: inherit;
	}
	.linkish.danger {
		color: #b00020;
	}
</style>
