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

<a href="#main-content" class="skip-link">Skip to content</a>

{#if !authState.checked}
	<div class="loading-screen">
		<span class="spinner"></span> Loading…
	</div>
{:else}
	<nav class="nav" aria-label="Main navigation">
		{#if authState.uid}
			<a href="/">Lobby</a>
			<a href="/stories">Stories</a>
			<a href="/stories/browse">Browse</a>
			<a href="/graphs">Graphs</a>
			<a href="/docs">Docs</a>
			<span class="spacer"></span>
			{#if authState.uid}
				<span class="who">{authState.uid}</span>
			{/if}
			<button type="button" class="linkish" onclick={() => logout()}>Logout</button>
		{:else}
			<a href="/login">Login</a>
		{/if}
	</nav>
	<div id="main-content">
		{#if authState.uid || page.url.pathname === '/login'}
			{@render children()}
		{/if}
	</div>
	<footer class="footer">
		<p>RPG Engine · Built with <a href="https://langchain-ai.github.io/langgraph/" target="_blank" rel="noopener">LangGraph</a>, <a href="https://flask.palletsprojects.com/" target="_blank" rel="noopener">Flask</a>, and <a href="https://svelte.dev/" target="_blank" rel="noopener">SvelteKit</a></p>
	</footer>
{/if}

<style>
	.loading-screen {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 3rem;
		color: #9aa0a6;
		font-size: 0.95rem;
	}
	.nav {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.65rem 1rem;
		background: #13151a;
		border-bottom: 1px solid #2a2f38;
		margin-bottom: 0;
	}
	.nav a {
		color: #8ab4f8;
		font-size: 0.9rem;
		font-weight: 500;
		text-decoration: none;
	}
	.nav a:hover { text-decoration: underline; }
	.spacer { flex: 1; }
	.who {
		font-size: 0.82rem;
		color: #9aa0a6;
		max-width: 10rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.linkish {
		background: none;
		border: 1px solid #3c4043;
		padding: 0.35rem 0.65rem;
		font: inherit;
		font-size: 0.8rem;
		color: #e8eaed;
		cursor: pointer;
		border-radius: 6px;
		text-decoration: none;
	}
	.linkish:hover { border-color: #5f6368; }
	#main-content {
		min-height: calc(100vh - 8rem);
		padding-top: 1rem;
	}
	.footer {
		border-top: 1px solid #2a2f38;
		padding: 1.25rem 1rem;
		text-align: center;
		font-size: 0.78rem;
		color: #5f6368;
	}
	.footer a { color: #8ab4f8; }
</style>
