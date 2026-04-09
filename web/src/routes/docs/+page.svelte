<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
</script>

<svelte:head>
	<title>Docs — RPG Engine</title>
</svelte:head>

<section class="docs">
	<h1>Documentation</h1>
	<div class="doc-hero">
		<img src="/images/docs-stories-hero.png" alt="Story creator writing a magical adventure" />
	</div>
	<p class="lede">Everything you need to know about the RPG Engine, organized by what you want to do.</p>
	<p class="repo-docs-hint">
		<a
			href="https://github.com/mcgowee/rpg-engine-basic/blob/main/docs/INDEX.md"
			target="_blank"
			rel="noopener noreferrer"
			>Repository doc index</a
		>
		<span class="hint-rest"> — architecture, node status, deploy notes, and what to update when graphs change.</span>
	</p>

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

		<a href="/docs/subgraphs" class="doc-card">
			<div class="doc-icon"><Icon name="git-branch" size={28} /></div>
			<div>
				<h2>Subgraphs</h2>
				<p class="level">Choosing a pipeline</p>
				<p>Compare every builtin subgraph: what runs each turn, when routing skips NPCs or mood, and which story types fit best.</p>
			</div>
		</a>
	</div>
</section>

<style>
	.docs { padding: 0 1rem 2rem; max-width: 800px; margin: 0 auto; }
	.doc-hero { margin: 0 0 1rem; border-radius: 10px; overflow: hidden; border: 1px solid #2a2f38; max-width: 56rem; }
	.doc-hero img { width: 100%; height: clamp(160px, 23vw, 220px); object-fit: cover; object-position: center; display: block; }
	.lede { color: #9aa0a6; margin: 0 0 1rem; }
	.repo-docs-hint {
		font-size: 0.88rem;
		color: #9aa0a6;
		line-height: 1.5;
		margin: 0 0 1.75rem;
	}
	.repo-docs-hint a {
		color: #8ab4f8;
		font-weight: 600;
	}
	.hint-rest { color: #9aa0a6; font-weight: 400; }
	:global([data-theme='light']) .repo-docs-hint,
	:global([data-theme='light']) .hint-rest {
		color: #64748b;
	}
	:global([data-theme='light']) .repo-docs-hint a {
		color: #1a73e8;
	}
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
	:global([data-theme="light"]) .doc-card {
		background: #fff;
		border-color: #dfe3e8;
		color: #1f2937;
	}
	:global([data-theme="light"]) .doc-card:hover { border-color: #c5ccd6; }
	:global([data-theme="light"]) .doc-card p { color: #4b5563; }
	:global([data-theme="light"]) .doc-hero { border-color: #dfe3e8; }
</style>
