import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import vercel from '@astrojs/vercel';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://dotfiles.kevinmuka.dev',
  integrations: [react(), sitemap({ customPages: [
    'https://dotfiles.kevinmuka.dev/explore/dotfiles',
    'https://dotfiles.kevinmuka.dev/explore/nvim',
  ] })],
  adapter: vercel(),
  trailingSlash: 'never',
});
