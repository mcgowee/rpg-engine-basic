<script lang="ts">
	import { page } from '$app/state';
	import Icon from '$lib/components/Icon.svelte';
	import { getTrainingDocLinks } from '$lib/trainingDocs';

	let pathname = $derived(page.url.pathname);
	let links = $derived(getTrainingDocLinks(pathname));
</script>

<nav class="training-docs-bar" aria-label="Related documentation and guides">
	<span class="training-docs-title">
		<Icon name="book" size={15} />
		<span>Guides</span>
	</span>
	<div class="training-docs-scroll">
		{#each links as item (item.href + item.label)}
			<a
				href={item.href}
				class="training-docs-link"
				target={item.external ? '_blank' : undefined}
				rel={item.external ? 'noopener noreferrer' : undefined}
			>
				{item.label}
				{#if item.external}
					<Icon name="external" size={12} />
				{/if}
			</a>
		{/each}
	</div>
</nav>

<style>
	.training-docs-bar {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		flex-wrap: nowrap;
		padding: 0.4rem 1rem;
		margin: 0 0 0;
		border-bottom: 1px solid #2a2f38;
		background: linear-gradient(180deg, #16181d 0%, #13151a 100%);
		font-size: 0.8rem;
		line-height: 1.3;
	}
	.training-docs-title {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		flex-shrink: 0;
		color: #9aa0a6;
		font-weight: 600;
		letter-spacing: 0.02em;
		text-transform: uppercase;
		font-size: 0.72rem;
	}
	.training-docs-scroll {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-wrap: wrap;
		min-width: 0;
		row-gap: 0.35rem;
	}
	.training-docs-link {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.28rem 0.55rem;
		border-radius: 6px;
		border: 1px solid #3c4043;
		background: #1a1d23;
		color: #e8eaed !important;
		text-decoration: none !important;
		font-weight: 500;
		white-space: nowrap;
		transition: border-color 0.15s, background 0.15s;
	}
	.training-docs-link:hover {
		border-color: #5f6368;
		background: #252a33;
		text-decoration: none !important;
	}
	:global([data-theme='light']) .training-docs-bar {
		border-bottom-color: #dfe3e8;
		background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
	}
	:global([data-theme='light']) .training-docs-title {
		color: #64748b;
	}
	:global([data-theme='light']) .training-docs-link {
		background: #fff;
		border-color: #d1d5db;
		color: #1e293b !important;
	}
	:global([data-theme='light']) .training-docs-link:hover {
		border-color: #94a3b8;
		background: #f1f5f9;
	}
</style>
