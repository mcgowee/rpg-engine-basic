import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

/** Old portrait-only URL — character media now lives under /charactermedia/[storyId]/[characterKey]. */
export const load: PageLoad = ({ params }) => {
	throw redirect(307, `/stories/${params.id}/edit`);
};
