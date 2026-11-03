export const repositories = {
  dotfiles: { owner: 'kevinmuka', name: 'dotfiles', branch: 'main', label: 'dotfiles', description: 'Shell, terminal, backup, and the configuration that joins them.' },
  nvim: { owner: 'kevinmuka', name: 'nvim', branch: 'main', label: 'nvim', description: 'Neovim modules, plugins, mappings, and shared theme.' },
} as const;

export type RepositoryKey = keyof typeof repositories;

export function isRepositoryKey(value: string): value is RepositoryKey {
  return Object.hasOwn(repositories, value);
}
