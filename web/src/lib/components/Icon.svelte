<script lang="ts">
	type Props = {
		name: string;
		size?: number;
	};
	let { name, size = 16 }: Props = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
	stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"
	aria-hidden="true">
	{#if name === 'edit'}
		<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
		<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
	{:else if name === 'play'}
		<polygon points="5 3 19 12 5 21 5 3" />
	{:else if name === 'plus'}
		<line x1="12" y1="5" x2="12" y2="19" />
		<line x1="5" y1="12" x2="19" y2="12" />
	{:else if name === 'book'}
		<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
		<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
	{:else if name === 'grid'}
		<rect x="3" y="3" width="7" height="7" />
		<rect x="14" y="3" width="7" height="7" />
		<rect x="3" y="14" width="7" height="7" />
		<rect x="14" y="14" width="7" height="7" />
	{:else if name === 'compass'}
		<circle cx="12" cy="12" r="10" />
		<polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
	{:else if name === 'users'}
		<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
		<circle cx="9" cy="7" r="4" />
		<path d="M23 21v-2a4 4 0 0 0-3-3.87" />
		<path d="M16 3.13a4 4 0 0 1 0 7.75" />
	{:else if name === 'user'}
		<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
		<circle cx="12" cy="7" r="4" />
	{:else if name === 'mic'}
		<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
		<path d="M19 10v2a7 7 0 0 1-14 0v-2" />
		<line x1="12" y1="19" x2="12" y2="23" />
		<line x1="8" y1="23" x2="16" y2="23" />
	{:else if name === 'brain'}
		<path d="M9.5 2A5.5 5.5 0 0 0 5 9.23V10a2 2 0 0 0 2 2h1v3a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-3h1a2 2 0 0 0 2-2v-.77A5.5 5.5 0 0 0 14.5 2h-5z" />
	{:else if name === 'message-square'}
		<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
	{:else if name === 'heart'}
		<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
	{:else if name === 'zap'}
		<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
	{:else if name === 'settings'}
		<circle cx="12" cy="12" r="3" />
		<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
	{:else if name === 'share'}
		<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
		<polyline points="16 6 12 2 8 6" />
		<line x1="12" y1="2" x2="12" y2="15" />
	{:else if name === 'download'}
		<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
		<polyline points="7 10 12 15 17 10" />
		<line x1="12" y1="15" x2="12" y2="3" />
	{:else if name === 'upload'}
		<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
		<polyline points="17 8 12 3 7 8" />
		<line x1="12" y1="3" x2="12" y2="15" />
	{:else if name === 'git-branch'}
		<line x1="6" y1="3" x2="6" y2="15" />
		<circle cx="18" cy="6" r="3" />
		<circle cx="6" cy="18" r="3" />
		<path d="M18 9a9 9 0 0 1-9 9" />
	{:else if name === 'layout'}
		<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
		<line x1="3" y1="9" x2="21" y2="9" />
		<line x1="9" y1="21" x2="9" y2="9" />
	{:else if name === 'file-text'}
		<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
		<polyline points="14 2 14 8 20 8" />
		<line x1="16" y1="13" x2="8" y2="13" />
		<line x1="16" y1="17" x2="8" y2="17" />
		<polyline points="10 9 9 9 8 9" />
	{:else if name === 'save'}
		<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
		<polyline points="17 21 17 13 7 13 7 21" />
		<polyline points="7 3 7 8 15 8" />
	{:else if name === 'pause'}
		<rect x="6" y="4" width="4" height="16" />
		<rect x="14" y="4" width="4" height="16" />
	{:else if name === 'home'}
		<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
		<polyline points="9 22 9 12 15 12 15 22" />
	{:else if name === 'search'}
		<circle cx="11" cy="11" r="8" />
		<line x1="21" y1="21" x2="16.65" y2="16.65" />
	{:else if name === 'copy'}
		<rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
		<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
	{:else if name === 'trash'}
		<polyline points="3 6 5 6 21 6" />
		<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
	{:else if name === 'arrow-left'}
		<line x1="19" y1="12" x2="5" y2="12" />
		<polyline points="12 19 5 12 12 5" />
	{:else if name === 'external'}
		<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
		<polyline points="15 3 21 3 21 9" />
		<line x1="10" y1="14" x2="21" y2="3" />
	{/if}
</svg>

<style>
	.icon { display: inline-block; vertical-align: middle; flex-shrink: 0; }
</style>
