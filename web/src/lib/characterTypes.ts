/** Shared story character shape — used by StoryEditor and CharacterPortraitWizard. */

export type MoodAxis = { axis: string; low: string; high: string; value: number };

export type PortraitRule = {
	mood?: Record<string, [number, number]>;
	tags?: string[];
	use: string;
	priority?: number;
};

export type CharEntry = {
	key: string;
	prompt: string;
	first_line: string;
	model: string;
	moods: MoodAxis[];
	portrait?: string;
	portraits?: Record<string, string>;
	portrait_rules?: PortraitRule[];
	face_ref?: Record<string, string>;
	face_extra_details?: string;
};

export function charEntryFromStoryPayload(key: string, val: unknown): CharEntry | null {
	if (!val || typeof val !== 'object' || Array.isArray(val)) return null;
	const v = val as Record<string, unknown>;
	let moods: MoodAxis[] = [];
	if (Array.isArray(v.moods)) {
		moods = (v.moods as Record<string, unknown>[]).map((m) => ({
			axis: String(m.axis ?? 'mood'),
			low: String(m.low ?? 'low'),
			high: String(m.high ?? 'high'),
			value: Number(m.value ?? 5),
		}));
	} else if (v.mood !== undefined) {
		moods = [{ axis: 'mood', low: 'hostile', high: 'friendly', value: Number(v.mood ?? 5) }];
	}
	let face_ref: Record<string, string> | undefined;
	if (v.face_ref && typeof v.face_ref === 'object' && !Array.isArray(v.face_ref)) {
		face_ref = {};
		for (const [fk, fv] of Object.entries(v.face_ref as Record<string, unknown>)) {
			if (typeof fv === 'string' && fv) face_ref[fk] = fv;
		}
		if (Object.keys(face_ref).length === 0) face_ref = undefined;
	}
	return {
		key,
		prompt: String(v.prompt ?? ''),
		first_line: String(v.first_line ?? ''),
		model: String(v.model ?? 'default'),
		moods,
		portrait: String(v.portrait ?? ''),
		portraits: v.portraits && typeof v.portraits === 'object' ? (v.portraits as Record<string, string>) : {},
		portrait_rules: Array.isArray(v.portrait_rules) ? (v.portrait_rules as PortraitRule[]) : [],
		face_ref,
		face_extra_details: String(v.face_extra_details ?? '').trim() || undefined,
	};
}

export function charEntriesFromStoryCharacters(d: Record<string, unknown>): CharEntry[] {
	return Object.entries(d)
		.map(([k, v]) => charEntryFromStoryPayload(k, v))
		.filter((x): x is CharEntry => x != null);
}

export function mergeCharEntryFromServer(cur: CharEntry, serverChar: Record<string, unknown>): CharEntry {
	const next: CharEntry = { ...cur };
	if (typeof serverChar.portrait === 'string') next.portrait = serverChar.portrait;
	if (serverChar.portraits && typeof serverChar.portraits === 'object' && !Array.isArray(serverChar.portraits)) {
		next.portraits = { ...(cur.portraits ?? {}), ...(serverChar.portraits as Record<string, string>) };
	}
	if (serverChar.face_ref && typeof serverChar.face_ref === 'object' && !Array.isArray(serverChar.face_ref)) {
		next.face_ref = { ...(serverChar.face_ref as Record<string, string>) };
	}
	if (typeof serverChar.face_extra_details === 'string') {
		next.face_extra_details = serverChar.face_extra_details.trim() || undefined;
	}
	if (Array.isArray(serverChar.portrait_rules)) {
		const pr = serverChar.portrait_rules as unknown[];
		next.portrait_rules = pr.filter((x): x is PortraitRule => {
			if (!x || typeof x !== 'object' || Array.isArray(x)) return false;
			const o = x as Record<string, unknown>;
			return typeof o.use === 'string' && o.use.trim().length > 0;
		}) as PortraitRule[];
	}
	return next;
}
