<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	type PublicStory = {
		id: number;
		title: string;
		description: string;
		genre: string;
		notes: string;
		author_uid: string;
		play_count: number;
		created_at: string;
	};

	let items = $state<PublicStory[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load() {
		loading = true;
		error = null;
		try {
			const r = await fetch('/api/stories/public', { credentials: 'include' });
			if (!r.ok) {
				error = `Failed to load public stories (${r.status})`;
				items = [];
				return;
			}
			const data = await r.json();
			const list = data.stories ?? data;
			items = Array.isArray(list) ? list : [];
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
			return new Date(s).toLocaleDateString();
		} catch {
			return s;
		}
	}
</script>

<svelte:head>
	<title>Browse Stories — RPG Engine</title>
</svelte:head>

<section class="page">
	<h1>Browse public stories</h1>
	<p class="lede">Stories shared by the community. Play them directly or copy to your account to customize. Each story's notes explain what engine features it demonstrates.</p>

	{#if loading}
		<p class="muted">Loading…</p>
	{:else if error}
		<p class="err">{error}</p>
		<button type="button" class="btn" onclick={() => load()}>Retry</button>
	{:else if items.length === 0}
		<p class="muted">No public stories yet.</p>
	{:else}
		<ul class="cards">
			{#each items as story (story.id)}
				<li class="card">
					<h2 class="card-title">{story.title}</h2>
					<p class="card-meta">
						<span class="author">by {story.author_uid}</span>
						<span class="dot">·</span>
						<span>{story.genre || '—'}</span>
						<span class="dot">·</span>
						<span>{story.play_count} plays</span>
						<span class="dot">·</span>
						<span>{formatWhen(story.created_at)}</span>
					</p>
					<p class="card-desc">{story.description || 'No description.'}</p>
					{#if story.notes}
						<p class="card-notes">{story.notes}</p>
					{/if}
					<p class="card-actions">
						<button type="button" class="btn primary" onclick={() => goto(`/play?story_id=${story.id}`)}>
							Play
						</button>
						<button type="button" class="btn" onclick={async () => {
							const r = await fetch(`/api/stories/${story.id}/copy`, {
								method: 'POST', credentials: 'include',
								headers: { 'Content-Type': 'application/json' },
							});
							if (r.ok) goto('/stories');
						}}>
							Copy to My Stories
						</button>
					</p>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.page { padding: 0 0.5rem 2rem; max-width: 54rem; }
	h1 { margin-top: 0; }
	.lede { color: #9aa0a6; margin-bottom: 1.25rem; line-height: 1.5; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.cards { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1rem; }
	.card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem 1.1rem; background: #1a1d23; }
	.card-title { margin: 0 0 0.35rem; font-size: 1.15rem; }
	.card-meta { margin: 0 0 0.75rem; font-size: 0.85rem; color: #9aa0a6; display: flex; flex-wrap: wrap; align-items: center; gap: 0.15rem; }
	.author { font-weight: 600; color: #bdc1c6; }
	.dot { color: #5f6368; }
	.card-desc { margin: 0; font-size: 0.95rem; line-height: 1.45; color: #bdc1c6; }
	.card-notes { margin: 0.35rem 0 0; font-size: 0.85rem; font-style: italic; color: #9aa0a6; }
	.card-actions { margin: 0.75rem 0 0; display: flex; gap: 0.5rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
</style>
