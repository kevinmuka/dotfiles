export function withGuideUpdated(html: string, updatedAt: string | undefined, lang: 'en' | 'it'): string {
  const withoutOldDate = html.replace(
    /(<h1\b[^>]*>[\s\S]*?<\/h1>)\s*<p>(?:Document updated on|Documento aggiornato il)\s+[^<]*<\/p>/,
    '$1',
  );
  if (!updatedAt) return withoutOldDate;

  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) return withoutOldDate;
  const formatted = new Intl.DateTimeFormat(lang === 'it' ? 'it-IT' : 'en-US', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  }).format(date);
  const label = lang === 'it' ? `Documento aggiornato il ${formatted}.` : `Document updated on ${formatted}.`;
  const stamp = `<p class="guide-updated"><time datetime="${date.toISOString().slice(0, 10)}">${label}</time></p>`;
  return withoutOldDate.replace(/(<h1\b[^>]*>[\s\S]*?<\/h1>)/, `$1\n${stamp}`);
}
