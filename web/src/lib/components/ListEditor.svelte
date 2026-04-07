<script lang="ts">
	let {
		items = $bindable<string[]>([]),
		placeholder = ''
	}: {
		items?: string[];
		placeholder?: string;
	} = $props();

	let draft = $state('');

	function add() {
		const x = draft.trim();
		if (!x || items.includes(x)) return;
		items = [...items, x];
		draft = '';
	}

	function remove(i: number) {
		items = items.filter((_, j) => j !== i);
	}
</script>

<div class="row">
	<input type="text" class="inp" bind:value={draft} {placeholder} onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), add())} />
	<button type="button" class="btn sm" onclick={add}>Add</button>
</div>
<div class="chips">
	{#each items as it, i (i)}
		<span class="chip"
			>{it}
			<button type="button" class="chip-x" onclick={() => remove(i)} aria-label="Remove">×</button></span
		>
	{/each}
</div>

<style>
	.row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.inp {
		padding: 0.35rem 0.5rem;
		border: 1px solid #aaa;
		border-radius: 4px;
		font: inherit;
		min-width: 8rem;
		flex: 1;
	}
	.btn {
		padding: 0.35rem 0.65rem;
		cursor: pointer;
		border: 1px solid #999;
		background: #fff;
		border-radius: 4px;
		font: inherit;
	}
	.btn.sm {
		font-size: 0.85rem;
		padding: 0.2rem 0.45rem;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-top: 0.35rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		background: #e8e8e8;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-size: 0.9rem;
	}
	.chip-x {
		border: none;
		background: none;
		cursor: pointer;
		font-size: 1rem;
		line-height: 1;
		padding: 0;
	}
</style>
