<script lang="ts">
	import { SvelteSet } from 'svelte/reactivity';
	import { coverImagePosition } from '$lib/coverDisplay';

	type BannerStage = 'cover' | 'genre' | 'placeholder';

	let { coverImage, genre, height = 120 }: { coverImage: string; genre: string; height?: number } = $props();

	let normalizedGenre = $derived(
		genre
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '')
	);
	let coverSrc = $derived(coverImage ? `/images/covers/${encodeURIComponent(coverImage)}` : '');
	let genreSrc = $derived(normalizedGenre ? `/images/genre-${normalizedGenre}.png` : '');

	let failedSources = new SvelteSet<string>();

	/** Prefer custom cover in /images/covers/; otherwise use /images/genre-{genre}.png when the story has no cover file. */
	let stage = $derived.by<BannerStage>(() => {
		if (coverSrc && !failedSources.has(coverSrc)) return 'cover';
		if (genreSrc && !failedSources.has(genreSrc)) return 'genre';
		return 'placeholder';
	});
</script>

<div class="card-banner" style:height={`${height}px`}>
	{#if stage === 'cover'}
		<img
			class="card-banner-img"
			src={coverSrc}
			alt=""
			loading="lazy"
			decoding="async"
			style:object-position={coverImagePosition(coverImage)}
			onerror={() => failedSources.add(coverSrc)}
		/>
	{:else if stage === 'genre'}
		<img
			class="card-banner-img"
			src={genreSrc}
			alt=""
			loading="lazy"
			decoding="async"
			onerror={() => failedSources.add(genreSrc)}
		/>
	{:else}
		<div class="card-banner-placeholder" aria-hidden="true">
			<span class="card-banner-icon">IMG</span>
			<span>No image available</span>
		</div>
	{/if}
</div>

<style>
	.card-banner {
		position: relative;
		overflow: hidden;
		background: #1f242c;
	}
	.card-banner-img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0.88;
	}
	.card-banner-placeholder {
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		font-size: 0.8rem;
		color: #8a929d;
	}
	.card-banner-icon {
		font-size: 0.95rem;
		line-height: 1;
	}
</style>
