import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({ bodySizeLimit: 100 * 1024 * 1024 }),
		csrf: {
			checkOrigin: false
		}
	}
};

export default config;
