<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { checkAuth, logout, authState } from '$lib/auth.svelte';
	import { themeState, initTheme, toggleTheme } from '$lib/theme.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { toasts } from '$lib/toast.svelte';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	let currentPath = $derived(page.url.pathname);
	let isLoginPage = $derived(currentPath === '/login');

	onMount(() => {
		initTheme();
		void checkAuth();
	});

	$effect(() => {
		if (!browser || !authState.checked) return;
		if (!authState.uid && !isLoginPage) {
			void goto('/login');
		}
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<a href="#main-content" class="skip-link">Skip to content</a>

<!-- Toast notifications -->
{#if toasts.length > 0}
	<div class="toast-container">
		{#each toasts as t (t.id)}
			<div class="toast-item toast-{t.type}" transition:fade={{ duration: 150 }}>
				{t.message}
			</div>
		{/each}
	</div>
{/if}

{#if !authState.checked}
	<div class="loading-screen" transition:fade={{ duration: 150 }}>
		<span class="spinner"></span> Loading…
	</div>
{:else}
	<header class="header">
		<div class="header-brand">
			<a href="/" class="brand-link">
				<span class="brand-icon">⚔</span>
				<span class="brand-text">RPG Engine</span>
			</a>
			<span class="brand-tag">Text Adventure Builder</span>
		</div>

		{#if authState.uid}
			<nav class="nav" aria-label="Main navigation">
				<a href="/" class:active={currentPath === '/'}>Lobby</a>
				<a href="/stories" class:active={currentPath.startsWith('/stories') && !currentPath.includes('browse')}>Stories</a>
				<a href="/stories/browse" class:active={currentPath.includes('browse')}>Browse</a>
				<a href="/books" class:active={currentPath === '/books'}>Books</a>
				<a href="/graphs" class:active={currentPath.startsWith('/graphs')}>Graphs</a>
				<a href="/docs" class:active={currentPath.startsWith('/docs')}>Docs</a>
				<a href="/playback" class:active={currentPath === '/playback'}>Playback</a>
				<a href="/settings" class:active={currentPath === '/settings'}><Icon name="settings" size={14} /></a>
			</nav>
		{/if}

		<div class="header-right">
			<button type="button" class="theme-toggle" onclick={toggleTheme}
				title={themeState.current === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
				aria-label="Toggle theme">
				{themeState.current === 'dark' ? '☀️' : '🌙'}
			</button>
			{#if authState.uid}
				<span class="who" title={authState.uid}>{authState.uid}</span>
				<button type="button" class="header-btn" onclick={() => logout()}>Logout</button>
			{:else if !isLoginPage}
				<a href="/login" class="header-btn">Login</a>
			{/if}
		</div>
	</header>

	<div id="main-content">
		{#if authState.uid || isLoginPage}
			{@render children()}
		{/if}
	</div>

	<footer class="footer">
		<div class="footer-content">
			<p class="footer-brand">⚔ RPG Engine</p>
			<p class="footer-links">
				<a href="/docs">Documentation</a> ·
				<a href="/docs/playing">Player Guide</a> ·
				<a href="/docs/stories">Story Creator Guide</a> ·
				<a href="/docs/engine">Engine Reference</a>
			</p>
			<p class="footer-tech">Built with <a href="https://langchain-ai.github.io/langgraph/" target="_blank" rel="noopener">LangGraph</a>, <a href="https://flask.palletsprojects.com/" target="_blank" rel="noopener">Flask</a>, and <a href="https://svelte.dev/" target="_blank" rel="noopener">SvelteKit</a></p>
		</div>
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
	/* Header */
	.header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 1rem;
		background: #13151a;
		border-bottom: 1px solid #2a2f38;
	}
	:global([data-theme="light"]) .header {
		background: #fff;
		border-bottom-color: #e0e0e0;
	}
	.header-brand {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-right: 0.5rem;
	}
	.brand-link {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		text-decoration: none;
		color: #e8eaed;
	}
	:global([data-theme="light"]) .brand-link { color: #1a1a1a; }
	.brand-link:hover { text-decoration: none; }
	.brand-icon { font-size: 1.1rem; }
	.brand-text { font-weight: 700; font-size: 0.95rem; white-space: nowrap; }
	.brand-tag {
		font-size: 0.7rem;
		color: #5f6368;
		white-space: nowrap;
		display: none;
	}
	@media (min-width: 768px) {
		.brand-tag { display: inline; }
	}
	/* Nav */
	.nav {
		display: flex;
		align-items: center;
		gap: 0.15rem;
		flex: 1;
		min-width: 0;
	}
	.nav a {
		color: #9aa0a6;
		font-size: 0.85rem;
		font-weight: 500;
		text-decoration: none;
		padding: 0.35rem 0.6rem;
		border-radius: 6px;
		white-space: nowrap;
		transition: background 0.1s, color 0.1s;
	}
	.nav a:hover { color: #e8eaed; background: #2a2f38; text-decoration: none; }
	.nav a.active { color: #8ab4f8; background: #1a2a4a; }
	:global([data-theme="light"]) .nav a { color: #555; }
	:global([data-theme="light"]) .nav a:hover { color: #1a1a1a; background: #f0f0f0; }
	:global([data-theme="light"]) .nav a.active { color: #1a73e8; background: #e3f2fd; }
	/* Header right */
	.header-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-left: auto;
	}
	.theme-toggle {
		background: none;
		border: 1px solid #3c4043;
		padding: 0.25rem 0.4rem;
		border-radius: 6px;
		font-size: 0.9rem;
		line-height: 1;
		cursor: pointer;
		transition: border-color 0.15s;
	}
	.theme-toggle:hover { border-color: #5f6368; }
	:global([data-theme="light"]) .theme-toggle { border-color: #ccc; }
	:global([data-theme="light"]) .theme-toggle:hover { border-color: #999; }
	.who {
		font-size: 0.82rem;
		color: #9aa0a6;
		max-width: 8rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.header-btn {
		background: none;
		border: 1px solid #3c4043;
		padding: 0.3rem 0.6rem;
		font: inherit;
		font-size: 0.8rem;
		color: #e8eaed;
		cursor: pointer;
		border-radius: 6px;
		text-decoration: none;
		white-space: nowrap;
	}
	.header-btn:hover { border-color: #5f6368; text-decoration: none; }
	:global([data-theme="light"]) .header-btn { color: #333; border-color: #ccc; }
	:global([data-theme="light"]) .header-btn:hover { border-color: #999; }
	/* Main */
	#main-content {
		min-height: calc(100vh - 8rem);
		padding-top: 1rem;
	}
	/* Footer */
	.footer {
		border-top: 1px solid #2a2f38;
		padding: 1.5rem 1rem;
		text-align: center;
	}
	:global([data-theme="light"]) .footer { border-top-color: #e0e0e0; }
	.footer-content { max-width: 40rem; margin: 0 auto; }
	.footer-brand { font-weight: 700; font-size: 0.85rem; margin: 0 0 0.5rem; color: #9aa0a6; }
	:global([data-theme="light"]) .footer-brand { color: #555; }
	.footer-links { margin: 0 0 0.5rem; font-size: 0.78rem; }
	.footer-links a { color: #8ab4f8; }
	:global([data-theme="light"]) .footer-links a { color: #1a73e8; }
	.footer-tech { font-size: 0.72rem; color: #5f6368; margin: 0; }
	.footer-tech a { color: #8ab4f8; }
	:global([data-theme="light"]) .footer-tech a { color: #1a73e8; }
	/* Responsive */
	@media (max-width: 640px) {
		.header { flex-wrap: wrap; gap: 0.35rem; }
		.nav { order: 3; width: 100%; overflow-x: auto; padding-top: 0.25rem; border-top: 1px solid #2a2f38; }
		.header-right { order: 2; }
		.brand-tag { display: none; }
	}
</style>
