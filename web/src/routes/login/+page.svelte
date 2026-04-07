<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { checkAuth, authState } from '$lib/auth.svelte';

	let uid = $state('');
	let password = $state('');
	let mode = $state<'login' | 'register'>('login');
	let error = $state('');

	onMount(() => {
		void (async () => {
			await checkAuth();
			if (authState.uid) await goto('/');
		})();
	});

	async function onsubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';

		if (!uid.trim()) {
			error = 'User id is required.';
			return;
		}
		if (mode === 'register' && password.length < 4) {
			error = 'Password must be at least 4 characters.';
			return;
		}

		const path = mode === 'login' ? '/api/login' : '/api/register';
		try {
			const r = await fetch(path, {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ uid: uid.trim(), password })
			});
			if (r.ok) {
				await checkAuth();
				await goto('/');
				return;
			}
			let msg = 'Request failed';
			try {
				const j = (await r.json()) as { error?: string; message?: string };
				msg = j.error ?? j.message ?? msg;
			} catch {
				/* use default */
			}
			error = msg;
		} catch {
			error = 'Network error';
		}
	}
</script>

<svelte:head>
	<title>{mode === 'login' ? 'Login' : 'Register'} — RPG Engine</title>
</svelte:head>

<div class="login-page">
<h1>{mode === 'login' ? 'Login' : 'Register'}</h1>

<p class="auth-notice">Accounts here are just to keep track of your stories and saves — pick any username and a simple password. No email required, no personal info collected.</p>

{#if error}
	<p class="err" role="alert" transition:fade={{ duration: 150 }}>{error}</p>
{/if}

<form onsubmit={onsubmit}>
	<label>
		User id
		<input type="text" name="uid" bind:value={uid} autocomplete="username" />
	</label>
	<label>
		Password
		<input type="password" name="password" bind:value={password} autocomplete="current-password" />
	</label>
	<button type="submit">{mode === 'login' ? 'Log in' : 'Register'}</button>
</form>

<p>
	<button
		type="button"
		class="toggle"
		onclick={() => {
			mode = mode === 'login' ? 'register' : 'login';
			error = '';
		}}
	>
		{mode === 'login' ? 'Need an account? Register' : 'Have an account? Log in'}
	</button>
</p>
</div>

<style>
	.login-page {
		min-height: calc(100vh - 8rem);
		background: linear-gradient(to right, rgba(15,17,20,0.92), rgba(15,17,20,0.6)), url('/images/login-bg.png') center/cover no-repeat;
		padding: 3rem 2rem;
		display: flex;
		flex-direction: column;
		max-width: 28rem;
	}
	form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		max-width: 20rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		color: #9aa0a6;
	}
	button[type="submit"] {
		background: #1a73e8;
		color: #fff;
		border: 1px solid #1a73e8;
		padding: 0.45rem 0.85rem;
		border-radius: 8px;
		font-size: 0.9rem;
	}
	button[type="submit"]:hover { opacity: 0.9; }
	.auth-notice { color: #9aa0a6; font-size: 0.88rem; max-width: 28rem; line-height: 1.5; margin-bottom: 1rem; }
	.err {
		color: #f28b82;
	}
	.toggle {
		background: none;
		border: none;
		padding: 0;
		color: #8ab4f8;
		cursor: pointer;
		text-decoration: underline;
		font: inherit;
	}
</style>
