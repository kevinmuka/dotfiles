# Kevin Muka Dotfiles site

Public site for the `dotfiles` and `nvim` repositories, deployed at <https://dotfiles.kevinmuka.dev> from this repository's `site` branch.

## Development

```sh
npm ci
npm run dev
npm run check
npm run build
```

Astro owns routes, metadata, shared layout, and the existing documentation pages. The repository explorer is a React island; Motion animates its interactive file tree. Astro's client router handles page transitions. The theme uses CSS tokens and a small script so every route renders in the selected colors before the content appears.

## Repository content

`src/data/repositories.ts` defines the public repositories. Explorer pages fetch file contents from the configured branch on GitHub at request time. The tree API and rendered pages carry cache headers; the browser also keeps a short session cache for the file list. Set `GITHUB_TOKEN` in the Vercel environment if unauthenticated GitHub API limits become a problem. The token is read only on the server and must never use a `PUBLIC_` prefix.

The HTML fragments in `src/content/pages/` preserve the original site copy and long translated guides. Page titles, descriptions, languages, and URLs live in `src/data/pages.ts`. The shared header and footer live in `src/layouts/SiteLayout.astro`.
