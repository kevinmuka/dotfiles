# Loaded before compinit by ~/.zshrc; safe to source again in an existing shell.
() {
  local completion_dir="$HOME/.zsh/completions"
  [[ -r "$completion_dir/_localbackup" ]] || return 0
  if (( ${fpath[(Ie)$completion_dir]} == 0 )); then
    fpath=("$completion_dir" "${fpath[@]}")
  fi
  zmodload zsh/complist 2>/dev/null
  zstyle ':completion:*:*:localbackup:*' menu select
  zstyle ':completion:*:*:localbackup:*' last-prompt true
  if [[ -t 1 && "$TERM" != dumb && -z "$NO_COLOR" ]]; then
    zstyle ':completion:*:*:localbackup:*' list-colors '=(#b)([a-z-]#)(*)=0=1;34=2'
  fi
  autoload -Uz _localbackup
  if (( $+functions[compdef] )); then
    compdef _localbackup localbackup
  fi
}
