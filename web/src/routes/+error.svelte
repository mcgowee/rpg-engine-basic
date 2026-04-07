<script lang="ts">
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>Error — RPG Engine</title>
</svelte:head>

<section class="error-page">
	<h1>{page.status}</h1>
	<p class="message">{page.error?.message || 'Something went wrong.'}</p>
	<div class="actions">
		<a href="/" class="btn">Back to Lobby</a>
		<a href="/stories" class="btn">My Stories</a>
	</div>
</section>

<style>
	.error-page {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 50vh;
		text-align: center;
		padding: 2rem;
	}
	h1 {
		font-size: 4rem;
		margin: 0 0 0.5rem;
		color: #e8eaed;
	}
	.message {
		font-size: 1.1rem;
		color: #9aa0a6;
		margin: 0 0 2rem;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
	}
	.btn {
		padding: 0.45rem 1rem;
		border: 1px solid #3c4043;
		background: #2a2f38;
		color: #e8eaed;
		border-radius: 8px;
		text-decoration: none;
		font-size: 0.9rem;
	}
	.btn:hover { border-color: #5f6368; }
</style>
