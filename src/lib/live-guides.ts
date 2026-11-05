import { getFile, renderMarkdown } from './repositories';
import type { RepositoryKey } from './repositories';

export type GuideHeading = { level: number; id: string; label: string };

export async function getLiveGuide(repo: RepositoryKey, path: string) {
  const source = await getFile(repo, path, AbortSignal.timeout(5000));
  const headings: GuideHeading[] = [];
  const usedIds = new Map<string, number>();
  const rendered = await renderMarkdown(repo, path, source);
  const html = rendered.replace(/<h([1-3]) id="([^"]+)">([\s\S]*?)<\/h\1>/g, (_match, depth: string, baseId: string, body: string) => {
    const count = usedIds.get(baseId) ?? 0;
    usedIds.set(baseId, count + 1);
    const id = count ? `${baseId}-${count}` : baseId;
    headings.push({ level: Number(depth), id, label: body.replace(/<[^>]+>/g, '') });
    return `<h${depth} id="${id}">${body}</h${depth}>`;
  });
  return { html, headings };
}
