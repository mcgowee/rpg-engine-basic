/**
 * CSS object-position / background-position for cropped story covers.
 * Use when the important subject sits high in the frame (wide banners crop vertically).
 */
const COVER_POSITION_BY_FILENAME: Record<string, string> = {
	'story_midnight_lighthouse.png': 'center top',
};

export function coverImagePosition(filename: string | null | undefined): string {
	if (!filename) return 'center';
	return COVER_POSITION_BY_FILENAME[filename] ?? 'center';
}
