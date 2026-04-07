import { browser } from '$app/environment';

export type Toast = {
	id: number;
	message: string;
	type: 'info' | 'success' | 'error' | 'warning';
};

let nextId = 0;
export const toasts = $state<Toast[]>([]);

export function toast(message: string, type: Toast['type'] = 'info', duration = 4000) {
	if (!browser) return;
	const id = nextId++;
	toasts.push({ id, message, type });
	setTimeout(() => {
		const idx = toasts.findIndex((t) => t.id === id);
		if (idx >= 0) toasts.splice(idx, 1);
	}, duration);
}

export function toastSuccess(message: string) { toast(message, 'success'); }
export function toastError(message: string) { toast(message, 'error', 6000); }
export function toastWarning(message: string) { toast(message, 'warning', 5000); }
