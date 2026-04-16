<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import { authState } from '$lib/auth.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import StoryCardBanner from '$lib/components/StoryCardBanner.svelte';

	type MyStory = {
		id: number;
		title: string;
		genre: string;
		cover_image: string;
		updated_at: string;
	};

	type PublicStory = {
		id: number;
		title: string;
		description: string;
		genre: string;
		cover_image: string;
		author_uid: string;
		play_count: number;
	};

	const MY_PREVIEW = 6;
	const PUBLIC_PREVIEW = 6;

	let loading = $state(true);
	let myStories = $state<MyStory[]>([]);
	let publicStories = $state<PublicStory[]>([]);
	let myStoriesError = $state<string | null>(null);
	let publicStoriesError = $state<string | null>(null);

	let myPreview = $derived(myStories.slice(0, MY_PREVIEW));
	let publicPreview = $derived(publicStories.slice(0, PUBLIC_PREVIEW));
	let hasMoreMine = $derived(myStories.length > MY_PREVIEW);
	let hasMorePublic = $derived(publicStories.length > PUBLIC_PREVIEW);
	let networkError = $state<string | null>(null);

	function formatWhen(s: string) {
		try {
			return new Date(s).toLocaleString();
		} catch {
			return s;
		}
	}

	onMount(() => {
		void load();
	});

	async function load() {
		loading = true;
		networkError = null;
		myStoriesError = null;
		publicStoriesError = null;
		try {
			const [rMine, rPublic] = await Promise.all([
				fetch('/api/stories', { credentials: 'include' }),
				fetch('/api/stories/public', { credentials: 'include' })
			]);

			if (rMine.ok) {
				const data = await rMine.json();
				myStories = Array.isArray(data) ? data : [];
			} else {
				myStories = [];
				myStoriesError =
					rMine.status === 401
						? 'Sign in again to load your stories.'
						: `Could not load your stories (${rMine.status}).`;
			}

			if (rPublic.ok) {
				const data = await rPublic.json();
				publicStories = Array.isArray(data) ? data : (Array.isArray(data?.stories) ? data.stories : []);
			} else {
				publicStories = [];
				publicStoriesError = `Could not load community stories (${rPublic.status}).`;
			}
		} catch {
			networkError = 'Network error — check your connection and try again.';
			myStories = [];
			publicStories = [];
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Lobby — RPG Engine</title>
</svelte:head>

<section class="lobby">
	{#if loading}
		<p class="muted center">Loading dashboard…</p>
	{:else}
		{#if networkError}
			<p class="err banner">{networkError}</p>
			<p><button type="button" class="btn" onclick={() => load()}>Retry</button></p>
		{/if}

		<div class="section welcome hero">
			<h1>⚔ RPG Engine</h1>
			<p class="lede">
				Welcome back, <strong>{authState.uid ?? 'player'}</strong>. Play a story, create your own, or explore how the engine works.
			</p>
			<p class="flow-note"><strong>Quick start:</strong> Create a story → Play it to generate turns → Open Playback to replay and evaluate sessions.</p>
			<div class="quick-actions">
				<button type="button" class="btn primary" onclick={() => goto('/stories/create')}><Icon name="plus" size={14} /> New Story</button>
				<button type="button" class="btn" onclick={() => goto('/stories')}><Icon name="book" size={14} /> My Stories</button>
				<button type="button" class="btn" onclick={() => goto('/stories/browse')}><Icon name="search" size={14} /> Browse Community</button>
				<button type="button" class="btn" onclick={() => goto('/graphs')}><Icon name="git-branch" size={14} /> Graph Editor</button>
			</div>
		</div>

		<div class="section play-cta">
			<div class="play-cta-inner">
				<div class="play-cta-text">
					<h2>Ready to play?</h2>
					<p>Browse <strong>{publicStories.length} community {publicStories.length === 1 ? 'story' : 'stories'}</strong> — mystery, adventure, thriller, comedy, and more. Pick one and start playing instantly.</p>
				</div>
				<button type="button" class="btn primary lg" onclick={() => goto('/stories/browse')}>
					<Icon name="play" size={18} /> Browse & Play
				</button>
			</div>
		</div>

		<div class="section">
			<div class="section-head">
				<h2>My stories</h2>
			</div>
			<p class="section-desc">Stories you've created or copied. Click Play to jump in, or Edit to change them.</p>
			{#if myStoriesError}
				<p class="err">{myStoriesError}</p>
			{:else if myStories.length === 0}
				<p class="muted">No stories yet.</p>
				<button type="button" class="btn primary" onclick={() => goto('/stories/create')}>
					Create your first story
				</button>
			{:else}
				<ul class="card-grid">
					{#each myPreview as s (s.id)}
						<li class="card">
							<StoryCardBanner coverImage={s.cover_image} genre={s.genre} height={100} />
							<h3 class="card-title">{s.title}</h3>
							<p class="card-meta">
								{s.genre || '—'} · {formatWhen(s.updated_at)}
							</p>
							<div class="card-actions">
								<button type="button" class="btn sm" onclick={() => goto(`/play?story_id=${s.id}`)}>
									<Icon name="play" size={12} /> Play
								</button>
								<button type="button" class="btn sm" onclick={() => goto(`/stories/${s.id}/edit`)}>
									<Icon name="edit" size={12} /> Edit
								</button>
							</div>
						</li>
					{/each}
				</ul>
				{#if hasMoreMine}
					<p class="more"><a href="/stories">View all →</a></p>
				{/if}
			{/if}
		</div>

		<div class="section">
			<div class="section-head">
				<h2>Community stories</h2>
			</div>
			<p class="section-desc">Public stories shared by the community. Play them or copy to your account to customize.</p>
			{#if publicStoriesError}
				<p class="err">{publicStoriesError}</p>
			{:else if publicStories.length === 0}
				<p class="muted">No community stories yet.</p>
			{:else}
				<ul class="card-grid public">
					{#each publicPreview as s (s.id)}
						<li class="card">
							<StoryCardBanner coverImage={s.cover_image} genre={s.genre} height={100} />
							<h3 class="card-title">{s.title}</h3>
							<p class="card-desc">{s.description || 'No description.'}</p>
							<p class="card-meta">
								{s.genre || '—'} · by {s.author_uid} · {s.play_count} plays
							</p>
							<div class="card-actions">
								<button type="button" class="btn sm primary" onclick={() => goto(`/play?story_id=${s.id}`)}>
									<Icon name="play" size={12} /> Play
								</button>
							</div>
						</li>
					{/each}
				</ul>
				{#if hasMorePublic}
					<p class="more"><a href="/stories/browse">Browse all →</a></p>
				{/if}
			{/if}
		</div>
	{/if}
</section>

<style>
	.lobby {
		padding: 0 1rem 2rem;
		max-width: 54rem;
		margin: 0 auto;
	}
	.center { text-align: center; padding: 2rem; }
	h1 { margin: 0 0 0.35rem; font-size: 1.65rem; }
	h2 { margin: 0; font-size: 1.15rem; }
	.section { margin-bottom: 2rem; }
	.section-head { margin-bottom: 0.75rem; padding-bottom: 0.35rem; border-bottom: 1px solid #2a2f38; }
	.play-cta {
		background: linear-gradient(135deg, #162a1e 0%, #0f1a14 100%);
		border: 2px solid #3a7d54;
		border-radius: 12px;
		padding: 1.25rem 1.5rem;
	}
	.play-cta-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1.5rem;
	}
	.play-cta-text h2 { font-size: 1.25rem; margin-bottom: 0.3rem; color: #6ee7a0; }
	.play-cta-text p { color: #b0c4b8; margin: 0; line-height: 1.45; font-size: 0.92rem; }
	.btn.lg { padding: 0.7rem 1.6rem; font-size: 1.05rem; white-space: nowrap; }
	@media (max-width: 600px) {
		.play-cta-inner { flex-direction: column; text-align: center; }
	}
	.hero {
		background: linear-gradient(to bottom, rgba(0,0,0,0.3), rgba(15,17,20,0.85)), url('/images/hero.png') center/cover no-repeat;
		border: 1px solid #2a2f38;
		border-radius: 12px;
		padding: 2.5rem 1.5rem;
		margin-bottom: 2rem;
		position: relative;
		overflow: hidden;
	}
	.welcome .lede { margin: 0 0 1rem; color: #9aa0a6; line-height: 1.5; }
	.quick-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.flow-note { margin: 0 0 0.9rem; font-size: 0.86rem; color: #c9d1dd; background: rgba(19, 31, 48, 0.65); border: 1px solid #2b3f5f; border-radius: 8px; padding: 0.42rem 0.62rem; display: inline-block; }
	.btn {
		padding: 0.45rem 0.85rem;
		border: 1px solid #3c4043;
		background: #2a2f38;
		color: #e8eaed;
		border-radius: 8px;
		font: inherit;
		font-size: 0.85rem;
	}
	.btn:hover { border-color: #5f6368; transition: border-color 0.18s ease, background-color 0.18s ease; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.sm { font-size: 0.85rem; padding: 0.25rem 0.55rem; }
	.card-grid {
		list-style: none; margin: 0; padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
		gap: 0.75rem;
	}
	.card {
		border: 1px solid #2a2f38;
		border-radius: 10px;
		overflow: hidden;
		background: #1a1d23;
		transition: border-color 0.18s ease, transform 0.18s ease;
	}
	.card:hover { border-color: #46505e; transform: translateY(-1px); }
	.card-title { margin: 0.6rem 1rem 0.35rem; font-size: 1rem; line-height: 1.3; }
	.card-desc {
		margin: 0 0 0.5rem; padding: 0 1rem; font-size: 0.88rem; line-height: 1.4;
		color: #bdc1c6;
		display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3;
		-webkit-box-orient: vertical; overflow: hidden;
	}
	.card-meta { margin: 0 0 0.5rem; padding: 0 1rem; font-size: 0.8rem; color: #9aa0a6; }
	.card-actions { display: flex; flex-wrap: wrap; gap: 0.35rem; padding: 0 1rem 0.75rem; }
	.more { margin: 0.75rem 0 0; font-size: 0.95rem; }
	.section-desc { font-size: 0.88rem; color: #9aa0a6; margin: 0 0 0.75rem; line-height: 1.45; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.err.banner {
		padding: 0.5rem 0.75rem;
		background: #2a1515;
		border-radius: 8px;
		border: 1px solid #5c2020;
	}
	:global([data-theme="light"]) .flow-note { color: #1f3f69; background: rgba(237, 246, 255, 0.95); border-color: #cddff8; }
	:global([data-theme="light"]) .card:hover { border-color: #cfd7e3; }
</style>
