<script lang="ts">
	import { page } from '$app/state';
	import CharacterPortraitWizard from '$lib/components/CharacterPortraitWizard.svelte';
	import { charEntryFromStoryPayload, type CharEntry } from '$lib/characterTypes';
	import Icon from '$lib/components/Icon.svelte';

	const storyId = $derived.by(() => {
		const raw = page.params.storyId ?? '';
		const n = Number(raw);
		return Number.isFinite(n) ? n : NaN;
	});

	const characterKey = $derived(decodeURIComponent(page.params.characterKey ?? ''));

	let loadDone = $state(false);
	let loadError = $state<string | null>(null);
	let storyTitle = $state('');
	let character = $state<CharEntry | null>(null);
	let brokenPortrait = $state(false);

	const editBackHref = $derived(
		Number.isFinite(storyId) ? `/stories/${storyId}/edit` : '/stories',
	);

	async function load() {
		loadError = null;
		loadDone = false;
		if (!Number.isFinite(storyId) || !characterKey.trim()) {
			loadError = 'Invalid story or character.';
			loadDone = true;
			return;
		}
		try {
			const r = await fetch(`/api/stories/${storyId}`, { credentials: 'include' });
			if (!r.ok) {
				loadError = r.status === 404 ? 'Story not found.' : `Could not load story (${r.status}).`;
				loadDone = true;
				return;
			}
			const s = await r.json();
			storyTitle = s.title ?? '';
			const rawChars = s.characters;
			if (!rawChars || typeof rawChars !== 'object' || Array.isArray(rawChars)) {
				loadError = 'Story has no characters.';
				loadDone = true;
				return;
			}
			const entry = charEntryFromStoryPayload(characterKey, (rawChars as Record<string, unknown>)[characterKey]);
			if (!entry) {
				loadError = `No character “${characterKey}” in this story. Add them on the story editor first.`;
				loadDone = true;
				return;
			}
			character = entry;
		} catch {
			loadError = 'Network error.';
		} finally {
			loadDone = true;
		}
	}

	function onCharacterChange(next: CharEntry) {
		character = next;
	}

	$effect(() => {
		const _sid = storyId;
		const _ck = characterKey;
		void load();
	});
</script>

<svelte:head>
	<title>Character media — {characterKey || '…'} — RPG Engine</title>
</svelte:head>

<section class="page">
	{#if !loadDone}
		<p class="muted"><span class="spinner"></span> Loading…</p>
	{:else if loadError}
		<p class="err">{loadError}</p>
		<p><a href={editBackHref}>← Back to story editor</a></p>
	{:else if character}
		<header class="head">
			<div>
				<h1>Image &amp; media</h1>
				<p class="muted meta">
					Character <code class="key">{character.key}</code>
					· Story <strong>{storyTitle.trim() || 'Untitled'}</strong>
				</p>
			</div>
			<a class="btn back" href={editBackHref}>← Back to story edit</a>
		</header>

		<p class="lead">
			Base portraits and expression variants for this cast member. Changes are saved on the story when you pick a face or
			run generation. Return anytime via the same link from the story editor.
		</p>

		<div class="field">
			<strong>Default portrait</strong>
			{#if character.portrait && !brokenPortrait}
				<div class="portrait-preview">
					<img
						src={`/images/portraits/${character.portrait}`}
						alt="{character.key} portrait"
						loading="lazy"
						decoding="async"
						onerror={() => (brokenPortrait = true)}
					/>
				</div>
			{:else if character.portrait}
				<div class="portrait-preview">
					<div class="image-placeholder">
						<Icon name="user" size={20} />
						<span>Portrait unavailable</span>
					</div>
				</div>
			{:else}
				<p class="muted small">No portrait yet — run Phase 1 below.</p>
			{/if}
		</div>

		<CharacterPortraitWizard
			storyId={storyId}
			character={character}
			onCharacterChange={onCharacterChange}
		/>
	{/if}
</section>

<style>
	.page {
		padding: 1rem;
		max-width: 720px;
	}
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
	}
	h1 {
		margin: 0 0 0.25rem;
		font-size: 1.35rem;
	}
	.meta {
		margin: 0;
		font-size: 0.88rem;
		line-height: 1.5;
	}
	.key {
		background: #2a2f38;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		font-size: 0.85rem;
	}
	.lead {
		font-size: 0.9rem;
		color: #9aa0a6;
		line-height: 1.5;
		margin: 0 0 1.25rem;
	}
	.muted {
		color: #9aa0a6;
	}
	.small {
		font-size: 0.88rem;
	}
	.err {
		color: #f28b82;
	}
	.field {
		margin-bottom: 1rem;
	}
	.field strong {
		display: block;
		margin-bottom: 0.35rem;
	}
	.portrait-preview {
		max-width: 200px;
	}
	.portrait-preview img {
		width: 100%;
		height: auto;
		border-radius: 8px;
		border: 1px solid #2a2f38;
		display: block;
	}
	.image-placeholder {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.35rem;
		padding: 1.5rem;
		border: 1px dashed #394250;
		border-radius: 8px;
		color: #9aa0a6;
		font-size: 0.85rem;
	}
	.btn {
		display: inline-block;
		padding: 0.45rem 0.85rem;
		border: 1px solid #3c4043;
		background: #2a2f38;
		color: #e8eaed;
		border-radius: 8px;
		font: inherit;
		font-size: 0.85rem;
		text-decoration: none;
	}
	.btn:hover {
		border-color: #5f6368;
	}
	.back {
		flex-shrink: 0;
	}
	a {
		color: #8ab4f8;
	}
</style>
