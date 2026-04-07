<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { checkAuth, logout, authState } from '$lib/auth.svelte';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	onMount(() => {
		void checkAuth();
	});

	$effect(() => {
		if (!browser || !authState.checked) return;
		if (!authState.uid && page.url.pathname !== '/login') {
			void goto('/login');
		}
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if !authState.checked}
	<p>Loading...</p>
{:else}
	<nav class="nav">
		{#if authState.uid}
			<a href="/">Lobby</a>
			<a href="/stories">Stories</a>
			<a href="/stories/browse">Browse</a>
			<a href="/graphs">Graphs</a>
			<a href="/docs">Docs</a>
			<button type="button" class="linkish" onclick={() => logout()}>Logout</button>
		{:else}
			<a href="/login">Login</a>
		{/if}
	</nav>
	{#if authState.uid || page.url.pathname === '/login'}
		{@render children()}
	{/if}
{/if}

<style>
	.nav {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid #ccc;
		margin-bottom: 1rem;
	}
	.nav a {
		color: inherit;
	}
	.linkish {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: #0066cc;
		cursor: pointer;
		text-decoration: underline;
	}
</style>
