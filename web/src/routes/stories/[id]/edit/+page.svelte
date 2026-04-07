<script lang="ts">
	import { page } from '$app/state';
	import StoryEditor from '$lib/components/StoryEditor.svelte';

	const storyId = $derived.by(() => {
		const raw = page.params.id ?? '';
		const n = Number(raw);
		return Number.isFinite(n) ? n : NaN;
	});
</script>

<svelte:head>
	<title>Edit Story — RPG Engine</title>
</svelte:head>

{#if Number.isNaN(storyId)}
	<section class="pad">
		<p class="err">Invalid story id.</p>
		<p><a href="/stories">← Back to stories</a></p>
	</section>
{:else}
	<StoryEditor mode="edit" storyId={storyId} />
{/if}

<style>
	.pad {
		padding: 1rem;
	}
	.err { color: #f28b82; }
</style>
