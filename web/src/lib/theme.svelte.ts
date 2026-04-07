import { browser } from '$app/environment';

export type Theme = 'dark' | 'light';

export const themeState = $state({ current: 'dark' as Theme });

export function initTheme() {
	if (!browser) return;
	const saved = localStorage.getItem('rpg-theme');
	if (saved === 'light' || saved === 'dark') {
		themeState.current = saved;
	}
	applyTheme();
}

export function toggleTheme() {
	themeState.current = themeState.current === 'dark' ? 'light' : 'dark';
	if (browser) {
		localStorage.setItem('rpg-theme', themeState.current);
		applyTheme();
	}
}

function applyTheme() {
	if (!browser) return;
	document.documentElement.setAttribute('data-theme', themeState.current);
}
