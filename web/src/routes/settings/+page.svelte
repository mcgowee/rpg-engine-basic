<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { toast } from '$lib/toast.svelte';
	import Icon from '$lib/components/Icon.svelte';

	type ModelInfo = {
		id: string;
		name: string;
		size: string;
		family: string;
		quantization: string;
	};

	type ProviderInfo = {
		available: boolean;
		models: ModelInfo[];
	};

	type RoleDefaults = {
		creative: string;
		dialogue: string;
		classification: string;
		summarization: string;
		tools: string;
	};

	let providers = $state<Record<string, ProviderInfo>>({});
	let roles = $state<RoleDefaults>({ creative: '', dialogue: '', classification: '', summarization: '', tools: '' });
	let defaultModel = $state('');
	let activeProvider = $state('');
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');

	// All available models flattened
	let allModels = $derived.by((): { id: string; label: string; provider: string }[] => {
		const out: { id: string; label: string; provider: string }[] = [];
		for (const [provName, prov] of Object.entries(providers)) {
			if (!prov.available) continue;
			for (const m of prov.models) {
				const sizeTag = m.size ? ` (${m.size})` : '';
				out.push({
					id: m.id,
					label: `${m.name}${sizeTag}`,
					provider: provName,
				});
			}
		}
		return out;
	});

	// Group models by provider for dropdown optgroups
	let modelsByProvider = $derived.by((): Record<string, { id: string; label: string }[]> => {
		const groups: Record<string, { id: string; label: string }[]> = {};
		for (const m of allModels) {
			if (!groups[m.provider]) groups[m.provider] = [];
			groups[m.provider].push({ id: m.id, label: m.label });
		}
		return groups;
	});

	const ROLE_INFO: Record<string, { label: string; description: string; examples: string }> = {
		creative: {
			label: 'Creative Writing',
			description: 'Narrator scene descriptions, narrator coda, book prose generation',
			examples: 'Best with larger, more creative models (12B+)',
		},
		dialogue: {
			label: 'Character Dialogue',
			description: 'NPC responses in character — 1-2 sentences each',
			examples: 'Medium models work well — needs personality but short output',
		},
		classification: {
			label: 'Classification',
			description: 'Mood axis evaluation — returns only UP, DOWN, or SAME',
			examples: 'Smallest/fastest model works fine — only outputs one word',
		},
		summarization: {
			label: 'Summarization',
			description: 'Condense node — compresses story history into ~100 word summary',
			examples: 'Medium models — needs comprehension but not creativity',
		},
		tools: {
			label: 'AI Tools',
			description: 'Improve, instruct, suggest, generate story, generate book',
			examples: 'Smart instruction-following model — needs to output JSON and structured text',
		},
	};

	onMount(async () => {
		try {
			const r = await fetch('/api/models', { credentials: 'include' });
			if (!r.ok) { error = `Failed to load models (${r.status})`; loading = false; return; }
			const data = await r.json();
			providers = data.providers ?? {};
			roles = data.roles ?? roles;
			defaultModel = data.default ?? '';
			activeProvider = data.active_provider ?? '';
		} catch {
			error = 'Network error';
		} finally {
			loading = false;
		}
	});

	async function saveRoles() {
		saving = true;
		try {
			const r = await fetch('/api/settings/models', {
				method: 'PUT', credentials: 'include',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ roles }),
			});
			if (r.ok) {
				toast('Model settings saved', 'success');
			} else {
				const j = await r.json().catch(() => ({}));
				toast(j.error ?? 'Save failed', 'error');
			}
		} catch {
			toast('Network error', 'error');
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Settings — RPG Engine</title>
</svelte:head>

<section class="settings">
	<h1><Icon name="settings" size={24} /> Settings</h1>
	<p class="lede">Configure which AI models are used for each role in the engine.</p>
	<div class="settings-hero">
		<img src="/images/settings-models.png" alt="Model configuration illustration" />
	</div>

	{#if loading}
		<p class="muted"><span class="spinner"></span> Loading models…</p>
	{:else if error}
		<p class="err">{error}</p>
	{:else}
		<div class="section">
			<h2>Available Models</h2>
			<p class="hint">Models discovered from your configured providers.</p>

			{#each Object.entries(providers) as [provName, prov] (provName)}
				<div class="provider-block">
					<h3>
						{provName === 'ollama' ? 'Ollama (Local)' : provName === 'azure' ? 'Azure OpenAI' : provName}
						{#if prov.available}
							<span class="status-badge online">online</span>
						{:else}
							<span class="status-badge offline">offline</span>
						{/if}
					</h3>
					{#if prov.available && prov.models.length > 0}
						<table class="model-table">
							<thead>
								<tr><th>Model</th><th>Size</th><th>Family</th><th>Quantization</th></tr>
							</thead>
							<tbody>
								{#each prov.models as m (m.id)}
									<tr class:is-default={m.id === defaultModel}>
										<td class="model-name">{m.id} {#if m.id === defaultModel}<span class="default-badge">default</span>{/if}</td>
										<td>{m.size || '—'}</td>
										<td>{m.family || '—'}</td>
										<td>{m.quantization || '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{:else if prov.available}
						<p class="muted">No models found.</p>
					{:else}
						<p class="muted">Provider not reachable.</p>
					{/if}
				</div>
			{/each}

			<p class="hint">Active provider: <strong>{activeProvider}</strong> · Default model: <strong>{defaultModel}</strong></p>
		</div>

		<div class="section">
			<h2>Role Defaults</h2>
			<p class="hint">Choose which model handles each type of LLM call. Stories and characters can override these per-story.</p>

			<div class="role-grid">
				{#each Object.entries(ROLE_INFO) as [roleKey, info] (roleKey)}
					<div class="role-card">
						<label class="role-label">
							<strong>{info.label}</strong>
							<span class="role-desc">{info.description}</span>
							<span class="role-hint">{info.examples}</span>
							<select bind:value={roles[roleKey as keyof RoleDefaults]}>
								<option value={defaultModel}>(default: {defaultModel.split('/').pop()})</option>
								{#each Object.entries(modelsByProvider) as [provName, models] (provName)}
									<optgroup label={provName === 'ollama' ? 'Ollama' : provName === 'azure' ? 'Azure' : provName}>
										{#each models as m (m.id)}
											<option value={m.id}>{m.label}</option>
										{/each}
									</optgroup>
								{/each}
							</select>
						</label>
					</div>
				{/each}
			</div>

			<div class="save-bar">
				<button type="button" class="btn primary" disabled={saving} onclick={() => saveRoles()}>
					<Icon name="save" size={14} /> {saving ? 'Saving…' : 'Save Model Settings'}
				</button>
			</div>
		</div>

		<div class="section">
			<h2>How Models Are Resolved</h2>
			<div class="cascade-diagram">
				<div class="cascade-step">Per-character model <span class="cascade-arrow">↓</span></div>
				<div class="cascade-step">Per-story model <span class="cascade-arrow">↓</span></div>
				<div class="cascade-step active">Site role default <span class="cascade-arrow">↓</span></div>
				<div class="cascade-step">DEFAULT_MODEL from .env</div>
			</div>
			<p class="hint">Each level falls back to the next. Most users only need to set the role defaults above.</p>
		</div>
	{/if}
</section>

<style>
	.settings { max-width: 800px; margin: 0 auto; padding: 0 1rem 3rem; }
	.lede { color: #9aa0a6; margin: 0 0 2rem; }
	.settings-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.settings-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.section { margin-bottom: 2.5rem; }
	.section h2 { font-size: 1.2rem; margin: 0 0 0.5rem; border-bottom: 1px solid #2a2f38; padding-bottom: 0.3rem; }
	.hint { font-size: 0.82rem; color: #9aa0a6; margin: 0.3rem 0; line-height: 1.5; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }

	.provider-block { margin-bottom: 1.5rem; }
	.provider-block h3 { font-size: 1rem; margin: 0 0 0.5rem; display: flex; align-items: center; gap: 0.5rem; }
	.status-badge { font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 12px; font-weight: 600; letter-spacing: 0.03em; }
	.status-badge.online { background: #1a3a1a; color: #81c995; }
	.status-badge.offline { background: #3a1a1a; color: #f28b82; }

	.model-table { width: 100%; font-size: 0.85rem; margin-bottom: 0.5rem; }
	.model-table th { font-size: 0.75rem; }
	.model-name { font-family: ui-monospace, monospace; font-size: 0.82rem; }
	.is-default { background: #1a2a1a; }
	.default-badge { font-size: 0.65rem; background: #1a73e8; color: #fff; padding: 0.1rem 0.3rem; border-radius: 3px; margin-left: 0.3rem; vertical-align: middle; }

	.role-grid { display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem; }
	.role-card { border: 1px solid #2a2f38; border-radius: 10px; padding: 1rem; background: #1a1d23; }
	.role-label { display: flex; flex-direction: column; gap: 0.3rem; }
	.role-label strong { font-size: 0.95rem; }
	.role-desc { font-size: 0.85rem; color: #bdc1c6; }
	.role-hint { font-size: 0.78rem; color: #9aa0a6; font-style: italic; }
	.role-label select { margin-top: 0.5rem; width: 100%; }

	.save-bar { margin-top: 1.5rem; display: flex; gap: 0.5rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; cursor: pointer; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }

	.cascade-diagram { display: flex; flex-direction: column; align-items: center; gap: 0.25rem; margin: 1rem 0; }
	.cascade-step { padding: 0.5rem 1.25rem; border: 1px solid #2a2f38; border-radius: 8px; background: #1a1d23; font-size: 0.88rem; text-align: center; }
	.cascade-step.active { border-color: #1a73e8; background: #111827; }
	.cascade-arrow { display: block; color: #5f6368; font-size: 0.75rem; margin-top: 0.15rem; }
	:global([data-theme="light"]) .section h2 { border-bottom-color: #dfe3e8; }
	:global([data-theme="light"]) .role-card { background: #f8fafc; border-color: #dfe3e8; }
	:global([data-theme="light"]) .role-desc { color: #334155; }
	:global([data-theme="light"]) .is-default { background: #eefbf0; }
	:global([data-theme="light"]) .model-table th { background: #f1f5f9; color: #4b5563; }
	:global([data-theme="light"]) .btn { background: #f8fafc; border-color: #d1d5db; color: #1f2937; }
	:global([data-theme="light"]) .btn:hover { border-color: #9ca3af; }
	:global([data-theme="light"]) .cascade-step { background: #f8fafc; border-color: #dfe3e8; color: #1f2937; }
	:global([data-theme="light"]) .cascade-step.active { background: #e8f1ff; border-color: #1a73e8; color: #0b3f84; }
	:global([data-theme="light"]) .settings-hero { border-color: #dfe3e8; }
</style>
