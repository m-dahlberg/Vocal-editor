import type { Handle } from '@sveltejs/kit';

const API_BACKEND = process.env.API_BACKEND || 'http://localhost:5000';

export const handle: Handle = async ({ event, resolve }) => {
	if (event.url.pathname.startsWith('/api/')) {
		const target = `${API_BACKEND}${event.url.pathname}${event.url.search}`;
		const headers = new Headers(event.request.headers);
		headers.delete('host');

		const response = await fetch(target, {
			method: event.request.method,
			headers,
			body: event.request.method !== 'GET' ? await event.request.arrayBuffer() : undefined,
			// @ts-ignore - duplex needed for streaming request bodies
			duplex: 'half'
		});

		return new Response(response.body, {
			status: response.status,
			statusText: response.statusText,
			headers: response.headers
		});
	}

	return resolve(event);
};
