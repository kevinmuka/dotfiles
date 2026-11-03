import type { APIRoute } from 'astro';
import { getTree, isRepositoryKey } from '../../../../lib/repositories';

export const prerender = false;

export const GET: APIRoute = async ({ params }) => {
  const repo = params.repo || '';
  if (!isRepositoryKey(repo)) return Response.json({ error: 'Unknown repository' }, { status: 404 });
  try {
    const tree = await getTree(repo);
    return Response.json({ tree }, { headers: { 'Cache-Control': 'public, s-maxage=900, stale-while-revalidate=3600' } });
  } catch {
    return Response.json({ error: 'The repository file list is temporarily unavailable' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
  }
};
