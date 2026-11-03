import type { APIRoute } from 'astro';
import { pages } from '../data/pages';
import { repositories } from '../data/repositories';

export const prerender = true;

export const GET: APIRoute = () => {
  const paths = [
    ...pages.map((page) => page.path),
    ...Object.keys(repositories).map((repo) => `/explore/${repo}`),
  ];
  const urls = paths.map((path) => `  <url><loc>${new URL(path, 'https://dotfiles.kevinmuka.dev').href}</loc></url>`);
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
