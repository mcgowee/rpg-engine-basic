import { proxyFlask } from '$lib/server/flask';
import type { RequestHandler } from './$types';

const proxy: RequestHandler = async ({ request, params }) => {
	const path = params.path ?? '';
	const basePath = path ? `/${path}` : '/';
	const search = new URL(request.url).search;
	const flaskPath = `${basePath}${search}`;

	const method = request.method;

	if (method === 'GET' || method === 'HEAD') {
		return proxyFlask(request, flaskPath, { method });
	}

	const text = await request.text();
	return proxyFlask(request, flaskPath, {
		method,
		body: text
	});
};

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
