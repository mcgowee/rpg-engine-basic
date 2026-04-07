<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type StoryRow = {
		id: number;
		title: string;
		description: string;
		genre: string;
		is_public: boolean;
		play_count: number;
		created_at: string;
		updated_at: string;
	};

	let items = $state<StoryRow[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let importFileInput = $state<HTMLInputElement | undefined>(undefined);
	let importError = $state<string | null>(null);
	let importOk = $state<string | null>(null);

	async function load() {
		loading = true;
		error = null;
		try {
			const r = await fetch('/api/stories', { credentials: 'include' });
			if (!r.ok) {
				error = `Failed to load stories (${r.status})`;
				items = [];
				return;
			}
			const data = await r.json();
			items = Array.isArray(data) ? data : [];
		} catch {
			error = 'Network error';
			items = [];
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

	async function togglePublish(row: StoryRow) {
		try {
			const r = await fetch(`/api/stories/${row.id}/publish`, {
				method: 'POST',
				credentials: 'include'
			});
			const j = (await r.json().catch(() => ({}))) as { ok?: boolean; is_public?: boolean };
			if (!r.ok || !j.ok) {
				alert((j as { error?: string }).error ?? `Publish failed (${r.status})`);
				return;
			}
			items = items.map((x) =>
				x.id === row.id ? { ...x, is_public: Boolean(j.is_public) } : x
			);
		} catch {
			alert('Network error');
		}
	}

	async function deleteStory(row: StoryRow) {
		if (!confirm(`Delete "${row.title}"? This cannot be undone.`)) return;
		try {
			const r = await fetch(`/api/stories/${row.id}`, {
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

	function slugFilename(title: string) {
		const s = title
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '')
			.slice(0, 100);
		return (s || 'story') + '.json';
	}

	async function exportStory(row: StoryRow) {
		try {
			const r = await fetch(`/api/stories/${row.id}/export`, { credentials: 'include' });
			if (!r.ok) {
				const j = (await r.json().catch(() => ({}))) as { error?: string };
				alert(j.error ?? `Export failed (${r.status})`);
				return;
			}
			let filename = slugFilename(row.title);
			const cd = r.headers.get('Content-Disposition');
			if (cd) {
				const m = /filename="([^"]+)"/i.exec(cd) ?? /filename\*=UTF-8''([^;\s]+)/i.exec(cd);
				if (m) {
					try {
						filename = decodeURIComponent(m[1].trim());
					} catch {
						filename = m[1].trim();
					}
				}
			}
			const text = await r.text();
			const blob = new Blob([text], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			a.rel = 'noopener';
			a.click();
			URL.revokeObjectURL(url);
		} catch {
			alert('Network error');
		}
	}

	function openImportPicker() {
		importError = null;
		importOk = null;
		importFileInput?.click();
	}

	async function onImportFile(ev: Event) {
		const input = ev.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		importError = null;
		importOk = null;
		let parsed: unknown;
		try {
			const raw = await file.text();
			parsed = JSON.parse(raw);
		} catch {
			importError = 'Invalid JSON in file.';
			return;
		}
		if (typeof parsed !== 'object' || parsed === null) {
			importError = 'File must contain a JSON object.';
			return;
		}
		try {
			const r = await fetch('/api/stories/import', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(parsed)
			});
			const j = (await r.json().catch(() => ({}))) as {
				error?: string;
				errors?: string[];
				id?: number;
				title?: string;
			};
			if (!r.ok) {
				if (Array.isArray(j.errors) && j.errors.length) {
					importError = j.errors.join(' ');
				} else {
					importError = j.error ?? `Import failed (${r.status})`;
				}
				return;
			}
			importOk = `Imported “${j.title ?? 'story'}” (new id ${j.id ?? '?'})`;
			await load();
		} catch {
			importError = 'Network error';
		}
	}
</script>

<svelte:head>
	<title>My stories</title>
</svelte:head>

<section class="page">
	<input
		bind:this={importFileInput}
		type="file"
		accept=".json,application/json"
		class="sr-only"
		aria-hidden="true"
		onchange={onImportFile}
	/>
	<div class="head-row">
		<h1>My stories</h1>
		<div class="head-actions">
			<button type="button" class="btn" onclick={openImportPicker}>Import</button>
			<button type="button" class="btn primary" onclick={() => goto('/stories/create')}>
				New Story
			</button>
		</div>
	</div>

	{#if importError}<p class="err">{importError}</p>{/if}
	{#if importOk}<p class="ok">{importOk}</p>{/if}

	{#if loading}
		<p class="muted">Loading…</p>
	{:else if error}
		<p class="err">{error}</p>
		<button type="button" class="btn" onclick={() => load()}>Retry</button>
	{:else if items.length === 0}
		<p class="muted">No stories yet — create your first one.</p>
		<p><button type="button" class="btn primary" onclick={() => goto('/stories/create')}>New Story</button></p>
	{:else}
		<div class="table-wrap">
			<table class="tbl">
				<thead>
					<tr>
						<th>Title</th>
						<th>Description</th>
						<th>Genre</th>
						<th>Public</th>
						<th>Plays</th>
						<th>Updated</th>
						<th>Actions</th>
					</tr>
				</thead>
				<tbody>
					{#each items as row (row.id)}
						<tr>
							<td class="title-cell">{row.title}</td>
							<td>{row.description || '—'}</td>
							<td>{row.genre || '—'}</td>
							<td>{row.is_public ? 'yes' : 'no'}</td>
							<td>{row.play_count}</td>
							<td class="small">{formatWhen(row.updated_at)}</td>
							<td class="actions">
								<button
									type="button"
									class="linkish"
									onclick={() => goto(`/play?story_id=${row.id}`)}
								>
									Play
								</button>
								<button type="button" class="linkish" onclick={() => exportStory(row)}>
									Export
								</button>
								<button
									type="button"
									class="linkish"
									onclick={() => goto(`/stories/${row.id}/edit`)}
								>
									Edit
								</button>
								<button type="button" class="linkish" onclick={() => togglePublish(row)}>
									{row.is_public ? 'Unpublish' : 'Publish'}
								</button>
								<button type="button" class="linkish danger" onclick={() => deleteStory(row)}>
									Delete
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>

<style>
	.page {
		padding: 0 0.5rem;
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
	.head-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
	.ok {
		color: #0a6b0a;
		margin: 0 0 0.75rem;
	}
	h1 {
		margin: 0;
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
	.title-cell {
		font-weight: 600;
		max-width: 12rem;
	}
	.small {
		font-size: 0.8rem;
		white-space: nowrap;
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
