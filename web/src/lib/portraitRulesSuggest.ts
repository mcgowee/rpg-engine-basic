/**
 * Heuristic portrait_rules from mood axes + generated variant keys.
 * Optional fine-tuning; runtime expression_picker uses LLM without these.
 */
import type { MoodAxis, PortraitRule } from '$lib/characterTypes';

function normAxis(s: string): string {
	return s.trim().toLowerCase().replace(/\s+/g, '_');
}

function hasKey(keys: Set<string>, k: string): boolean {
	return keys.has(k.toLowerCase());
}

/**
 * Build suggested rules. Only emits rules for variant keys that exist on the character.
 */
export function suggestPortraitRules(moods: MoodAxis[], variantKeys: string[]): PortraitRule[] {
	const keys = new Set(variantKeys.map((k) => k.toLowerCase()));
	const rules: PortraitRule[] = [];
	let prio = 0;

	for (const axis of moods) {
		const an = normAxis(axis.axis);
		if (an === 'mood') {
			if (hasKey(keys, 'angry')) {
				rules.push({ mood: { mood: [1, 3] }, use: 'angry', priority: prio++ });
			}
			if (hasKey(keys, 'neutral')) {
				rules.push({ mood: { mood: [4, 6] }, use: 'neutral', priority: prio++ });
			}
			if (hasKey(keys, 'happy')) {
				rules.push({ mood: { mood: [7, 8] }, use: 'happy', priority: prio++ });
			}
			if (hasKey(keys, 'flirty')) {
				rules.push({ mood: { mood: [9, 10] }, use: 'flirty', priority: prio++ });
			}
			continue;
		}
		if (an === 'arousal') {
			if (hasKey(keys, 'neutral')) {
				rules.push({ mood: { arousal: [1, 3] }, use: 'neutral', priority: prio++ });
			}
			if (hasKey(keys, 'flirty')) {
				rules.push({ mood: { arousal: [7, 10] }, use: 'flirty', priority: prio++ });
			}
		}
	}

	return rules;
}

export function ruleSummary(rule: PortraitRule): string {
	const parts: string[] = [];
	if (rule.mood && Object.keys(rule.mood).length > 0) {
		for (const [ax, range] of Object.entries(rule.mood)) {
			if (Array.isArray(range) && range.length >= 2) {
				parts.push(`${ax} ${range[0]}–${range[1]}`);
			}
		}
	}
	if (rule.tags?.length) {
		parts.push(`tags: ${rule.tags.join(', ')}`);
	}
	const cond = parts.length ? parts.join(', ') : '(no condition)';
	return `${cond} → ${rule.use}`;
}
