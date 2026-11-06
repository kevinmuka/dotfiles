import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ChevronRight, ExternalLink, FileCode2, Folder, GitBranch, Search } from 'lucide-react';
import { repositories } from '../data/repositories';
import type { RepositoryKey } from '../data/repositories';
import type { TreeEntry } from '../lib/repositories';

type Props = { repo: RepositoryKey; selectedPath: string; initialTree: TreeEntry[] | null };
type Node = { name: string; path: string; type: TreeEntry['type']; children: Node[] };
type VisibleItem = { path: string; type: TreeEntry['type']; parent: string | null; firstChild: string | null };

function buildTree(entries: TreeEntry[]): Node[] {
  const root: Node = { name: '', path: '', type: 'tree', children: [] };
  const nodes = new Map<string, Node>([['', root]]);
  for (const entry of entries) {
    const parts = entry.path.split('/');
    for (let i = 0; i < parts.length; i++) {
      const path = parts.slice(0, i + 1).join('/');
      if (nodes.has(path)) continue;
      const node: Node = { name: parts[i], path, type: i === parts.length - 1 ? entry.type : 'tree', children: [] };
      nodes.get(parts.slice(0, i).join('/'))?.children.push(node);
      nodes.set(path, node);
    }
  }
  const sort = (list: Node[]) => {
    list.sort((a, b) => (a.type === 'tree' ? 0 : 1) - (b.type === 'tree' ? 0 : 1) || a.name.localeCompare(b.name));
    list.forEach((node) => sort(node.children));
  };
  sort(root.children);
  return root.children;
}

function ancestors(path: string) {
  const parts = path.split('/');
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'));
}

export default function RepositoryExplorer({ repo, selectedPath, initialTree }: Props) {
  const [activePath, setActivePath] = useState(selectedPath);
  const [entries, setEntries] = useState<TreeEntry[]>(initialTree ?? []);
  const [loading, setLoading] = useState(!initialTree);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Set<string>>(() => new Set(ancestors(activePath)));
  const [focusedPath, setFocusedPath] = useState(activePath);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef(new Map<string, HTMLElement>());
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const updatePath = () => {
      const prefix = `/explore/${repo}`;
      const pathname = window.location.pathname;
      if (pathname === prefix) setActivePath('README.md');
      else if (pathname.startsWith(`${prefix}/`)) {
        setActivePath(pathname.slice(prefix.length + 1).split('/').map(decodeURIComponent).join('/'));
      }
    };
    document.addEventListener('astro:after-swap', updatePath);
    return () => document.removeEventListener('astro:after-swap', updatePath);
  }, [repo]);

  useEffect(() => {
    const selectedDirectory = entries.some((entry) => entry.path === activePath && entry.type === 'tree') ? [activePath] : [];
    setOpen((previous) => new Set([...previous, ...ancestors(activePath), ...selectedDirectory]));
  }, [activePath, entries]);

  useEffect(() => {
    const controller = new AbortController();
    setQuery('');
    const cacheKey = `dotfiles-tree-${repo}`;
    if (initialTree) {
      setEntries(initialTree);
      setLoading(false);
      setError('');
      try { sessionStorage.setItem(cacheKey, JSON.stringify({ at: Date.now(), tree: initialTree })); } catch { /* Cache is optional. */ }
      return () => controller.abort();
    }
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey) || 'null') as { at: number; tree: TreeEntry[] } | null;
      if (cached && Date.now() - cached.at < 15 * 60_000) {
        setEntries(cached.tree);
        setLoading(false);
        setError('');
        return () => controller.abort();
      }
    } catch { /* Ignore unavailable session storage. */ }
    setLoading(true);
    fetch(`/api/repos/${repo}/tree.json`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('File list unavailable');
        return response.json() as Promise<{ tree: TreeEntry[] }>;
      })
      .then(({ tree }) => {
        setEntries(tree);
        setError('');
        try { sessionStorage.setItem(cacheKey, JSON.stringify({ at: Date.now(), tree })); } catch { /* Cache is optional. */ }
      })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'File list unavailable'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [repo, initialTree]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const nodes = useMemo(() => buildTree(entries), [entries]);
  const matches = useMemo(() => entries.filter((entry) => entry.type !== 'tree' && entry.path.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 80), [entries, query]);
  const visibleItems = useMemo<VisibleItem[]>(() => {
    if (query.trim()) return matches.map((entry) => ({ path: entry.path, type: entry.type, parent: null, firstChild: null }));
    const result: VisibleItem[] = [];
    const visit = (siblings: Node[], parent: string | null) => {
      for (const node of siblings) {
        result.push({ path: node.path, type: node.type, parent, firstChild: node.children[0]?.path ?? null });
        if (node.type === 'tree' && open.has(node.path)) visit(node.children, node.path);
      }
    };
    visit(nodes, null);
    return result;
  }, [matches, nodes, open, query]);
  const tabStop = visibleItems.some((item) => item.path === focusedPath) ? focusedPath
    : visibleItems.some((item) => item.path === activePath) ? activePath : visibleItems[0]?.path;
  const registerRow = (path: string) => (element: HTMLElement | null) => {
    if (element) rowRefs.current.set(path, element);
    else rowRefs.current.delete(path);
  };
  const focusRow = (path: string) => {
    setFocusedPath(path);
    rowRefs.current.get(path)?.focus();
  };
  const handleTreeKeyDown = (event: React.KeyboardEvent<HTMLUListElement>) => {
    const row = (event.target as HTMLElement).closest<HTMLElement>('[data-tree-path]');
    if (!row || !event.currentTarget.contains(row)) return;
    const index = visibleItems.findIndex((item) => item.path === row.dataset.treePath);
    if (index < 0) return;
    const current = visibleItems[index];
    let next: string | null = null;
    switch (event.key) {
      case 'ArrowDown': next = visibleItems[index + 1]?.path ?? null; break;
      case 'ArrowUp': next = visibleItems[index - 1]?.path ?? null; break;
      case 'ArrowRight':
        if (current.type === 'tree') {
          if (!open.has(current.path)) toggle(current.path);
          else next = current.firstChild;
        }
        break;
      case 'ArrowLeft':
        if (current.type === 'tree' && open.has(current.path)) toggle(current.path);
        else next = current.parent;
        break;
      case 'Home': next = visibleItems[0]?.path ?? null; break;
      case 'End': next = visibleItems.at(-1)?.path ?? null; break;
      default: return;
    }
    event.preventDefault();
    if (next) focusRow(next);
  };
  const toggle = (path: string) => setOpen((previous) => {
    const next = new Set(previous);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    return next;
  });

  const item = (node: Node, depth: number): React.ReactNode => {
    const directory = node.type === 'tree';
    const expanded = open.has(node.path);
    return <li key={node.path} role="none">
      {directory
        ? <button ref={registerRow(node.path)} className="tree-row" type="button" role="treeitem" data-tree-path={node.path} tabIndex={tabStop === node.path ? 0 : -1} aria-level={depth + 1} style={{ paddingLeft: `${12 + depth * 16}px` }} onFocus={() => setFocusedPath(node.path)} onClick={() => toggle(node.path)} aria-expanded={expanded}>
            <ChevronRight size={14} className={expanded ? 'tree-chevron is-open' : 'tree-chevron'} aria-hidden="true" />
            <Folder size={15} aria-hidden="true" />
            <span>{node.name}</span>
          </button>
        : <a ref={registerRow(node.path)} className="tree-row" role="treeitem" data-tree-path={node.path} tabIndex={tabStop === node.path ? 0 : -1} aria-level={depth + 1} style={{ paddingLeft: `${12 + depth * 16}px` }} onFocus={() => setFocusedPath(node.path)} href={repo === 'dotfiles' && node.type === 'commit' && node.path === 'home/.config/nvim' ? '/explore/nvim' : `/explore/${repo}/${node.path.split('/').map(encodeURIComponent).join('/')}`} aria-current={activePath === node.path ? 'page' : undefined}>
            <span className="tree-chevron" aria-hidden="true" />
            <FileCode2 size={15} aria-hidden="true" />
            <span>{node.name}</span>
          </a>}
      {directory && <AnimatePresence initial={false}>
        {expanded && <motion.ul className="tree-children" role="group" initial={reducedMotion ? false : { height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={reducedMotion ? undefined : { height: 0, opacity: 0 }} transition={{ duration: .22 }}>
          {node.children.map((child) => item(child, depth + 1))}
        </motion.ul>}
      </AnimatePresence>}
    </li>;
  };

  return <aside className="explorer-sidebar panel" aria-label="Repository files">
    <div className="explorer-sidebar-head">
      <div className="explorer-repo-tabs" aria-label="Repositories">
        {(Object.keys(repositories) as RepositoryKey[]).map((key) => <a key={key} href={`/explore/${key}`} aria-current={repo === key ? 'page' : undefined}>{repositories[key].label}</a>)}
      </div>
      <p><GitBranch size={14} aria-hidden="true" /> Public <code>{repositories[repo].branch}</code> branch</p>
    </div>
    <label className="explorer-search"><Search size={16} aria-hidden="true" /><input ref={searchRef} type="search" placeholder="Find a file" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => {
      if (event.key === 'Tab' && !event.shiftKey && visibleItems[0] && rowRefs.current.has(visibleItems[0].path)) {
        event.preventDefault();
        focusRow(visibleItems[0].path);
      }
    }} aria-label={`Find a file in ${repo}`} /><kbd>⌘K</kbd></label>
    <div className="explorer-tree" tabIndex={-1} aria-live="polite" onClick={(event) => {
      if ((event.target as HTMLElement).closest('[data-tree-path], a, button')) return;
      setFocusedPath(visibleItems[0]?.path ?? '');
      event.currentTarget.focus();
    }}>
      {loading && <p className="explorer-status">Loading files…</p>}
      {error && <p className="explorer-status">{error}. <a href={`https://github.com/${repositories[repo].owner}/${repositories[repo].name}`} target="_blank" rel="noopener noreferrer">Browse on GitHub <ExternalLink size={13} aria-hidden="true" /></a></p>}
      {!loading && !error && (query.trim()
        ? <ul className="tree-list search-results" role="tree" aria-label={`${repo} search results`} onKeyDown={handleTreeKeyDown}>{matches.map((entry) => <li key={entry.path} role="none"><a ref={registerRow(entry.path)} className="tree-row" role="treeitem" data-tree-path={entry.path} tabIndex={tabStop === entry.path ? 0 : -1} aria-level={1} onFocus={() => setFocusedPath(entry.path)} href={`/explore/${repo}/${entry.path.split('/').map(encodeURIComponent).join('/')}`} aria-current={activePath === entry.path ? 'page' : undefined}><FileCode2 size={15} aria-hidden="true" /><span>{entry.path}</span></a></li>)}{matches.length === 0 && <li className="explorer-status">No matching files.</li>}</ul>
        : <ul className="tree-list" role="tree" aria-label={`${repo} files`} onKeyDown={handleTreeKeyDown}>{nodes.map((node) => item(node, 0))}</ul>)}
    </div>
  </aside>;
}
