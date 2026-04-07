<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
</script>

<svelte:head>
	<title>Docs — RPG Engine</title>
</svelte:head>

<section class="docs">
	<h1>Documentation</h1>
	<p class="lede">Everything you need to know about the RPG Engine, organized by what you want to do.</p>

	<div class="cards">
		<a href="/docs/playing" class="doc-card">
			<div class="doc-icon"><Icon name="play" size={28} /></div>
			<div>
				<h2>Playing Stories</h2>
				<p class="level">For players</p>
				<p>How to browse and play stories, what the sidebar shows, how saves work, and how character moods affect the game.</p>
			</div>
		</a>

		<a href="/docs/stories" class="doc-card">
			<div class="doc-icon"><Icon name="edit" size={28} /></div>
			<div>
				<h2>Creating Stories</h2>
				<p class="level">For story creators</p>
				<p>How to build your own stories, define characters with mood axes, pick the right subgraph, and use AI generation. Includes a guide to every builtin story.</p>
			</div>
		</a>

		<a href="/docs/engine" class="doc-card">
			<div class="doc-icon"><Icon name="settings" size={28} /></div>
			<div>
				<h2>Engine Reference</h2>
				<p class="level">For graph builders</p>
				<p>How nodes, routers, edges, and state work together. Build custom subgraphs, test them, and understand the LangGraph pipeline.</p>
			</div>
		</a>
	</div>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.lede { color: #9aa0a6; margin: 0 0 2rem; }
	.cards { display: flex; flex-direction: column; gap: 1rem; }
	.doc-card {
		display: flex;
		gap: 1rem;
		align-items: flex-start;
		border: 1px solid #2a2f38;
		border-radius: 10px;
		padding: 1.25rem 1.5rem;
		background: #1a1d23;
		text-decoration: none;
		color: #e8eaed;
		transition: border-color 0.15s, transform 0.1s;
	}
	.doc-card:hover { border-color: #5f6368; text-decoration: none; transform: translateY(-1px); }
	.doc-icon { color: #8ab4f8; flex-shrink: 0; margin-top: 0.2rem; }
	.doc-card h2 { margin: 0 0 0.15rem; font-size: 1.15rem; }
	.doc-card p { margin: 0.3rem 0 0; font-size: 0.9rem; color: #bdc1c6; line-height: 1.5; }
	.level { font-size: 0.78rem !important; color: #8ab4f8 !important; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; margin: 0 0 0.4rem !important; }
</style>
