import { env } from '$env/dynamic/private';

const DEFAULT_FLASK_API_URL = 'http://127.0.0.1:5051';

function flaskBaseUrl(): string {
	const raw = env.FLASK_API_URL?.trim();
	if (raw) return raw.replace(/\/$/, '');
	return DEFAULT_FLASK_API_URL;
}

/** Relay Set-Cookie from an upstream response (undici: getSetCookie(); fallback: get). */
export function relaySetCookies(source: Headers, target: Headers): void {
	const src = source as Headers & { getSetCookie?: () => string[] };
	if (typeof src.getSetCookie === 'function') {
		for (const cookie of src.getSetCookie()) {
			target.append('Set-Cookie', cookie);
		}
		return;
	}
	const fallback = source.get('set-cookie');
	if (fallback) target.append('Set-Cookie', fallback);
}

function buildFlaskUrl(flaskPath: string): string {
	const path = flaskPath.startsWith('/') ? flaskPath : `/${flaskPath}`;
	return `${flaskBaseUrl()}${path}`;
}

function mergeResponseHeaders(upstream: Headers): Headers {
	const out = new Headers();
	upstream.forEach((value, key) => {
		if (key.toLowerCase() === 'set-cookie') return;
		out.append(key, value);
	});
	relaySetCookies(upstream, out);
	out.delete('transfer-encoding');
	out.delete('connection');
	return out;
}

/**
 * Proxies a SvelteKit request to Flask: forwards Cookie, relays Set-Cookie, preserves status/body.
 */
export async function proxyFlask(
	request: Request,
	flaskPath: string,
	init?: RequestInit
): Promise<Response> {
	const url = buildFlaskUrl(flaskPath);
	const method = init?.method ?? request.method;

	const headers = new Headers(init?.headers ?? undefined);
	const cookie = request.headers.get('cookie');
	if (cookie) headers.set('Cookie', cookie);

	let body: BodyInit | null | undefined;
	if (init?.body !== undefined) {
		body = init.body;
	} else if (!['GET', 'HEAD'].includes(method.toUpperCase())) {
		const buf = await request.arrayBuffer();
		body = buf.byteLength > 0 ? buf : undefined;
	}

	if (
		body != null &&
		!headers.has('Content-Type') &&
		!(body instanceof FormData) &&
		!(body instanceof URLSearchParams) &&
		!(body instanceof ReadableStream)
	) {
		headers.set('Content-Type', 'application/json');
	}

	const fetchInit: RequestInit & { duplex?: 'half' } = {
		method,
		headers,
		redirect: init?.redirect ?? 'manual'
	};
	if (init?.signal !== undefined) fetchInit.signal = init.signal;
	if (init?.integrity !== undefined) fetchInit.integrity = init.integrity;
	if (init?.keepalive !== undefined) fetchInit.keepalive = init.keepalive;
	if (body !== undefined && body !== null) {
		fetchInit.body = body;
		if (body instanceof ReadableStream) fetchInit.duplex = 'half';
	}

	try {
		const upstream = await fetch(url, fetchInit);
		return new Response(upstream.body, {
			status: upstream.status,
			statusText: upstream.statusText,
			headers: mergeResponseHeaders(upstream.headers)
		});
	} catch {
		return Response.json({ error: 'Backend unreachable' }, { status: 502 });
	}
}
