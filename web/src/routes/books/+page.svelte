<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import Icon from '$lib/components/Icon.svelte';
	import { toast } from '$lib/toast.svelte';
	import { coverImagePosition } from '$lib/coverDisplay';

	type BookRow = {
		id: number;
		story_id: number;
		title: string;
		genre: string;
		cover_image: string;
		created_at: string;
		updated_at: string;
	};

	let books = $state<BookRow[]>([]);
	let loading = $state(true);
	let error = $state('');

	function formatDate(s: string) {
		try { return new Date(s).toLocaleString(); } catch { return s; }
	}

	onMount(async () => {
		try {
			const r = await fetch('/api/books', { credentials: 'include' });
			if (r.ok) {
				books = await r.json();
			} else {
				error = `Failed to load books (${r.status})`;
			}
		} catch {
			error = 'Network error';
		} finally {
			loading = false;
		}
	});

	async function deleteBook(id: number) {
		if (!confirm('Delete this book?')) return;
		try {
			const r = await fetch(`/api/books/${id}`, { method: 'DELETE', credentials: 'include' });
			if (r.ok) {
				books = books.filter(b => b.id !== id);
				toast('Book deleted', 'success');
			}
		} catch { /* ignore */ }
	}
</script>

<svelte:head>
	<title>My Books — RPG Engine</title>
</svelte:head>

<section class="page">
	<div class="head-row">
		<h1><Icon name="book" size={24} /> My Books</h1>
	</div>
	<p class="page-desc">Stories you've played and transformed into prose. Each book is a polished rewrite of a play session.</p>

	{#if loading}
		<p class="muted"><span class="spinner"></span> Loading…</p>
	{:else if error}
		<p class="err">{error}</p>
	{:else if books.length === 0}
		<div class="empty">
			<img src="/images/empty-books.png" alt="Magical book waiting to be written" class="empty-illustration" />
			<p>No books yet.</p>
			<p class="muted">Play a story, then click <strong>Book</strong> on your stories list to create one.</p>
		</div>
	{:else}
		<ul class="book-grid">
			{#each books as book (book.id)}
				<li class="book-card">
					{#if book.cover_image}
						<div
							class="book-cover"
							style="background-image: url('/images/covers/{book.cover_image}'); background-position: {coverImagePosition(book.cover_image)};"
						></div>
					{:else if book.genre}
						<div class="book-cover" style="background-image: url('/images/genre-{book.genre}.png')"></div>
					{:else}
						<div class="book-cover book-cover-empty">
							<Icon name="book" size={32} />
						</div>
					{/if}
					<div class="book-info">
						<h2 class="book-title">{book.title}</h2>
						{#if book.genre}<span class="book-genre">{book.genre}</span>{/if}
						<p class="book-date">{formatDate(book.updated_at)}</p>
					</div>
					<div class="book-actions">
						<button type="button" class="btn sm primary" onclick={() => goto(`/stories/${book.story_id}/book`)}>
							<Icon name="book" size={12} /> Read
						</button>
						<button type="button" class="btn sm" onclick={() => deleteBook(book.id)}>
							<Icon name="trash" size={12} />
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.page { padding: 0 1rem 2rem; max-width: 900px; margin: 0 auto; }
	.head-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
	.head-row h1 { display: flex; align-items: center; gap: 0.5rem; margin: 0; }
	.page-desc { font-size: 0.88rem; color: #9aa0a6; line-height: 1.5; margin: 0 0 1.5rem; }
	.muted { color: #9aa0a6; }
	.err { color: #f28b82; }
	.empty { padding: 2rem; text-align: center; border: 1px solid #2a2f38; border-radius: 10px; background: #1a1d23; }
	.empty-illustration { width: 100%; max-width: 26rem; border-radius: 8px; border: 1px solid #2a2f38; margin: 0 auto 0.85rem; display: block; }
	.book-grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }
	.book-card { border: 1px solid #2a2f38; border-radius: 10px; overflow: hidden; background: #1a1d23; display: flex; flex-direction: column; }
	.book-cover { height: 120px; background-size: cover; background-position: center; opacity: 0.7; }
	.book-cover-empty { display: flex; align-items: center; justify-content: center; background: #13151a; color: #5f6368; opacity: 1; }
	.book-info { padding: 0.75rem 1rem; flex: 1; }
	.book-title { font-size: 1rem; margin: 0 0 0.25rem; line-height: 1.3; }
	.book-genre { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8ab4f8; }
	.book-date { font-size: 0.78rem; color: #9aa0a6; margin: 0.35rem 0 0; }
	.book-actions { padding: 0.5rem 1rem 0.75rem; display: flex; gap: 0.35rem; }
	.btn { padding: 0.45rem 0.85rem; border: 1px solid #3c4043; background: #2a2f38; color: #e8eaed; border-radius: 8px; font: inherit; font-size: 0.85rem; cursor: pointer; text-decoration: none; }
	.btn:hover { border-color: #5f6368; }
	.btn.primary { background: #1a73e8; border-color: #1a73e8; }
	.btn.sm { font-size: 0.8rem; padding: 0.35rem 0.65rem; }
	:global([data-theme="light"]) .empty { background: #f8fafc; border-color: #dfe3e8; color: #1f2937; }
	:global([data-theme="light"]) .empty-illustration { border-color: #dfe3e8; }
	:global([data-theme="light"]) .book-card { background: #fff; border-color: #dfe3e8; }
	:global([data-theme="light"]) .book-cover-empty { background: #f1f5f9; color: #6b7280; border-bottom: 1px solid #dfe3e8; }
	:global([data-theme="light"]) .btn { background: #f8fafc; border-color: #d1d5db; color: #1f2937; }
	:global([data-theme="light"]) .btn:hover { border-color: #9ca3af; }
</style>
