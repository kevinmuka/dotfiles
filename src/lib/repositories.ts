import { posix } from 'node:path';
import { Marked } from 'marked';
import sanitizeHtml from 'sanitize-html';
import { codeToHtml } from 'shiki';
import { repositories } from '../data/repositories';
import type { RepositoryKey } from '../data/repositories';

export { repositories, isRepositoryKey } from '../data/repositories';
export type { RepositoryKey } from '../data/repositories';
export type TreeEntry = { path: string; type: 'blob' | 'tree' | 'commit'; size?: number };
const treeCache = new Map<RepositoryKey, { at: number; tree: TreeEntry[] }>();

export function normalizePath(value: string): string | null {
  if (!value || value.includes('\\') || value.includes('\0')) return null;
  const segments = value.split('/');
  if (segments.some((segment) => !segment || segment === '.' || segment === '..')) return null;
  return segments.join('/');
}

function githubHeaders() {
  const token = process.env.GITHUB_TOKEN;
  return {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export function githubUrl(key: RepositoryKey, path = '', directory = false) {
  const repo = repositories[key];
  const encoded = path.split('/').map(encodeURIComponent).join('/');
  return `https://github.com/${repo.owner}/${repo.name}/${path ? `${directory ? 'tree' : 'blob'}/${repo.branch}/${encoded}` : ''}`.replace(/\/$/, '');
}

export function rawUrl(key: RepositoryKey, path: string) {
  const repo = repositories[key];
  return `https://raw.githubusercontent.com/${repo.owner}/${repo.name}/${repo.branch}/${path.split('/').map(encodeURIComponent).join('/')}`;
}

export async function getTree(key: RepositoryKey): Promise<TreeEntry[]> {
  const cached = treeCache.get(key);
  if (cached && Date.now() - cached.at < 15 * 60_000) return cached.tree;
  const repo = repositories[key];
  const response = await fetch(`https://api.github.com/repos/${repo.owner}/${repo.name}/git/trees/${repo.branch}?recursive=1`, { headers: githubHeaders() });
  if (!response.ok) throw new Error(`GitHub tree request failed (${response.status})`);
  const payload = await response.json() as { truncated?: boolean; tree?: TreeEntry[] };
  if (payload.truncated || !Array.isArray(payload.tree)) throw new Error('GitHub returned an incomplete file tree');
  const tree = payload.tree.filter((item) => (item.type === 'tree' || item.type === 'blob' || item.type === 'commit') && Boolean(normalizePath(item.path)));
  treeCache.set(key, { at: Date.now(), tree });
  return tree;
}

export function isImage(path: string) { return /\.(png|jpe?g|gif|webp|svg|avif)$/i.test(path); }
export function isMarkdown(path: string) { return /\.(md|markdown)$/i.test(path); }
export function isTextFile(path: string) {
  return /(^|\/)(README|LICENSE|Makefile|Dockerfile|\.gitignore|\.gitmodules|\.zshrc|\.zprofile|\.zshenv)$|\.(md|markdown|txt|sh|zsh|bash|lua|json|jsonc|ya?ml|toml|ini|conf|config|env|css|scss|html|xml|svg|js|jsx|ts|tsx|py|rs|go|c|h|cpp|hpp|java|gradle|properties|sql|vim|vimrc|gitignore)$/i.test(path);
}

export async function getFile(key: RepositoryKey, path: string): Promise<string> {
  const valid = normalizePath(path);
  if (!valid || !isTextFile(valid)) throw new Error('Preview unavailable for this file');
  const response = await fetch(rawUrl(key, valid));
  if (!response.ok) throw new Error(`GitHub file request failed (${response.status})`);
  const length = Number(response.headers.get('content-length') || 0);
  if (length > 300_000) throw new Error('This file is too large to preview');
  const content = await response.text();
  if (content.length > 300_000) throw new Error('This file is too large to preview');
  return content;
}

function resolveReadmeLink(key: RepositoryKey, currentPath: string, href: string, image: boolean) {
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href) || href.startsWith('#')) return href;
  const [pathAndQuery, fragment] = href.split('#', 2);
  const [relativePath, query] = pathAndQuery.split('?', 2);
  const resolved = posix.normalize(posix.join(posix.dirname(currentPath), relativePath)).replace(/\/$/, '');
  if (resolved.startsWith('../') || resolved === '..') return githubUrl(key);
  const suffix = `${query ? `?${query}` : ''}${fragment ? `#${fragment}` : ''}`;
  if (image) return `${rawUrl(key, resolved)}${suffix}`;
  if (key === 'dotfiles' && (resolved === 'home/.config/nvim' || resolved.startsWith('home/.config/nvim/'))) {
    const subpath = resolved.slice('home/.config/nvim'.length).replace(/^\//, '');
    return `/explore/nvim${subpath ? `/${subpath.split('/').map(encodeURIComponent).join('/')}` : ''}${suffix}`;
  }
  return `/explore/${key}/${resolved.split('/').map(encodeURIComponent).join('/')}${suffix}`;
}

export async function renderMarkdown(key: RepositoryKey, path: string, source: string) {
  const parser = new Marked({
    gfm: true,
    walkTokens(token) {
      if (token.type === 'link' || token.type === 'image') token.href = resolveReadmeLink(key, path, token.href, token.type === 'image');
    },
  });
  const rendered = await parser.parse(source);
  const clean = sanitizeHtml(rendered, {
    allowedTags: [...sanitizeHtml.defaults.allowedTags, 'img', 'input'],
    allowedAttributes: {
      ...sanitizeHtml.defaults.allowedAttributes,
      a: ['href', 'title', 'target', 'rel'],
      img: ['src', 'alt', 'title', 'width', 'height'],
      input: ['type', 'checked', 'disabled'],
      code: ['class'],
    },
    transformTags: {
      a: (tagName, attributes) => {
        const external = /^https?:\/\//i.test(attributes.href || '');
        return { tagName, attribs: { ...attributes, ...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {}) } };
      },
    },
  });
  return clean.replace(/<h([1-6])>(.*?)<\/h\1>/g, (_match, level: string, body: string) => {
    const slug = body.replace(/<[^>]+>/g, '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9 -]/g, '').trim().replace(/\s+/g, '-');
    return `<h${level} id="${slug}">${body}</h${level}>`;
  });
}

export async function renderCode(path: string, source: string) {
  const ext = path.split('.').pop()?.toLowerCase();
  const language = ({ sh: 'bash', zsh: 'bash', bash: 'bash', lua: 'lua', json: 'json', jsonc: 'jsonc', yaml: 'yaml', yml: 'yaml', toml: 'toml', js: 'javascript', jsx: 'jsx', ts: 'typescript', tsx: 'tsx', css: 'css', html: 'html', xml: 'xml', py: 'python', rs: 'rust', go: 'go', c: 'c', cpp: 'cpp', java: 'java', sql: 'sql', md: 'markdown' } as Record<string, string>)[ext || ''] || 'text';
  try {
    return await codeToHtml(source, { lang: language, themes: { light: 'github-light', dark: 'github-dark' } });
  } catch {
    return await codeToHtml(source, { lang: 'text', themes: { light: 'github-light', dark: 'github-dark' } });
  }
}
