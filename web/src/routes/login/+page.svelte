<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
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

<h1>{mode === 'login' ? 'Login' : 'Register'}</h1>

{#if error}
	<p class="err" role="alert">{error}</p>
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

<style>
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
	}
	.err {
		color: #b00020;
	}
	.toggle {
		background: none;
		border: none;
		padding: 0;
		color: #0066cc;
		cursor: pointer;
		text-decoration: underline;
		font: inherit;
	}
</style>
