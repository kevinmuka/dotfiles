import page0 from '../content/pages/home.html?raw';
import page1 from '../content/pages/macbackup.html?raw';
import page2 from '../content/pages/macbackup-privacy.html?raw';
import page3 from '../content/pages/macbackup-docs.html?raw';
import page4 from '../content/pages/macbackup-docs-it.html?raw';
import page5 from '../content/pages/nvim.html?raw';
import page6 from '../content/pages/nvim-docs.html?raw';
import page7 from '../content/pages/nvim-docs-it.html?raw';
import page8 from '../content/pages/symlinks.html?raw';
import page9 from '../content/pages/theme.html?raw';

export const pages = [
  { ...{"slug": "", "path": "/", "title": "dotfiles - kevinmuka", "description": "Explore Kevin Muka's dotfiles, tools, experiments, and documentation in one place.", "lang": "en", "alternates": []}, content: page0 },
  { ...{"slug": "macbackup", "path": "/macbackup", "title": "macbackup — kevinmuka / dotfiles", "description": "A personal Mac backup tool using rclone, encrypted private areas and explicit history management.", "lang": "en", "alternates": []}, content: page1 },
  { ...{"slug": "macbackup/privacy", "path": "/macbackup/privacy", "title": "macbackup privacy policy — kevinmuka / dotfiles", "description": "Privacy policy for the personal macbackup utility and its Google Drive access.", "lang": "en", "alternates": []}, content: page2 },
  { ...{"slug": "macbackup/docs", "path": "/macbackup/docs", "title": "macbackup documentation — kevinmuka", "description": "macbackup documentation covering file selection, encrypted backups, version history, verification, and recovery on Google Drive.", "lang": "en", "alternates": [{"href": "https://dotfiles.kevinmuka.dev/macbackup/docs", "lang": "en"}, {"href": "https://dotfiles.kevinmuka.dev/macbackup/docs/it", "lang": "it"}, {"href": "https://dotfiles.kevinmuka.dev/macbackup/docs", "lang": "x-default"}]}, content: page3 },
  { ...{"slug": "macbackup/docs/it", "path": "/macbackup/docs/it", "title": "Documentazione macbackup — kevinmuka", "description": "Guida a macbackup: selezione dei file, backup cifrati, storico delle versioni, verifiche e ripristino su Google Drive.", "lang": "it", "alternates": [{"href": "https://dotfiles.kevinmuka.dev/macbackup/docs", "lang": "en"}, {"href": "https://dotfiles.kevinmuka.dev/macbackup/docs/it", "lang": "it"}, {"href": "https://dotfiles.kevinmuka.dev/macbackup/docs", "lang": "x-default"}]}, content: page4 },
  { ...{"slug": "nvim", "path": "/nvim", "title": "Neovim — kevinmuka / dotfiles", "description": "A modular Neovim configuration with lazy.nvim, LSP tools, navigation and a shared theme.", "lang": "en", "alternates": []}, content: page5 },
  { ...{"slug": "nvim/docs", "path": "/nvim/docs", "title": "Neovim configuration guide — kevinmuka", "description": "Explore Kevin Muka's Neovim configuration, from Lua modules and plugins to LSP, navigation, and the shared theme.", "lang": "en", "alternates": [{"href": "https://dotfiles.kevinmuka.dev/nvim/docs", "lang": "en"}, {"href": "https://dotfiles.kevinmuka.dev/nvim/docs/it", "lang": "it"}, {"href": "https://dotfiles.kevinmuka.dev/nvim/docs", "lang": "x-default"}]}, content: page6 },
  { ...{"slug": "nvim/docs/it", "path": "/nvim/docs/it", "title": "Guida alla configurazione Neovim — kevinmuka", "description": "Guida alla configurazione Neovim di Kevin Muka: struttura Lua, plugin, LSP, navigazione e tema condiviso.", "lang": "it", "alternates": [{"href": "https://dotfiles.kevinmuka.dev/nvim/docs", "lang": "en"}, {"href": "https://dotfiles.kevinmuka.dev/nvim/docs/it", "lang": "it"}, {"href": "https://dotfiles.kevinmuka.dev/nvim/docs", "lang": "x-default"}]}, content: page7 },
  { ...{"slug": "symlinks", "path": "/symlinks", "title": "Symlink manager — kevinmuka / dotfiles", "description": "How dot.sh plans, applies and safely manages dotfile symlinks.", "lang": "en", "alternates": []}, content: page8 },
  { ...{"slug": "theme", "path": "/theme", "title": "Theme and terminal — kevinmuka / dotfiles", "description": "Shared color tokens for Zsh, WezTerm and Neovim, plus related Mac workflow modules.", "lang": "en", "alternates": []}, content: page9 },
] as const;
