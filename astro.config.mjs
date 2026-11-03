import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import vercel from '@astrojs/vercel';

export default defineConfig({
  site: 'https://dotfiles.kevinmuka.dev',
  integrations: [react()],
  adapter: vercel(),
  trailingSlash: 'never',
});
