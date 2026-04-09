/**
 * Contextual “training” (help) doc links for the current route.
 * Keep in sync with pages under src/routes/docs/.
 */

export type TrainingDocLink = {
	label: string;
	href: string;
	external?: boolean;
};

const REPO_BLOB = (repoPath: string) =>
	`https://github.com/mcgowee/rpg-engine-basic/blob/main/${repoPath}`;

/** Markdown served from /static/docs (see web/static/docs/). */
export const SUBGRAPHS_MD_STATIC = '/docs/SUBGRAPHS.md';

export function getTrainingDocLinks(pathname: string): TrainingDocLink[] {
	if (pathname === '/login') {
		return [{ label: 'Documentation', href: '/docs' }];
	}

	if (pathname === '/docs') {
		return [
			{ label: 'Player Guide', href: '/docs/playing' },
			{ label: 'Story Creator', href: '/docs/stories' },
			{ label: 'Engine Reference', href: '/docs/engine' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
		];
	}

	if (pathname.startsWith('/docs/subgraphs')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'SUBGRAPHS.md', href: SUBGRAPHS_MD_STATIC },
			{ label: 'Engine Reference', href: '/docs/engine' },
			{ label: 'GitHub', href: REPO_BLOB('docs/SUBGRAPHS.md'), external: true },
		];
	}

	if (pathname.startsWith('/docs/engine')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
			{ label: 'Creating Stories', href: '/docs/stories' },
		];
	}

	if (pathname.startsWith('/docs/stories')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
			{ label: 'Player Guide', href: '/docs/playing' },
		];
	}

	if (pathname.startsWith('/docs/playing')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Creating Stories', href: '/docs/stories' },
		];
	}

	if (pathname.startsWith('/docs')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Player Guide', href: '/docs/playing' },
			{ label: 'Engine Reference', href: '/docs/engine' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
		];
	}

	if (pathname.startsWith('/graphs')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Engine Reference', href: '/docs/engine' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
		];
	}

	if (pathname.startsWith('/stories')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Creating Stories', href: '/docs/stories' },
			{ label: 'Subgraphs', href: '/docs/subgraphs' },
		];
	}

	if (pathname.startsWith('/play')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Player Guide', href: '/docs/playing' },
		];
	}

	if (pathname.startsWith('/books')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Creating Stories', href: '/docs/stories' },
		];
	}

	if (pathname.startsWith('/playback')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Engine Reference', href: '/docs/engine' },
		];
	}

	if (pathname.startsWith('/settings')) {
		return [
			{ label: 'Docs home', href: '/docs' },
			{ label: 'Engine Reference', href: '/docs/engine' },
		];
	}

	// Lobby and everything else
	return [
		{ label: 'Docs home', href: '/docs' },
		{ label: 'Player Guide', href: '/docs/playing' },
		{ label: 'Story Creator', href: '/docs/stories' },
	];
}
