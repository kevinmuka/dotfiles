# Loaded before compinit by ~/.zshrc; also safe to source in an existing shell.
() {
  local completion_dir="$HOME/.zsh/completions"
  [[ -r "$completion_dir/_macbackup" ]] || return 0

  if (( ${fpath[(Ie)$completion_dir]} == 0 )); then
    fpath=("$completion_dir" "${fpath[@]}")
  fi
  # Keep repeated TAB presses inside one selectable menu for macbackup.
  zmodload zsh/complist 2>/dev/null
  zstyle ':completion:*:*:macbackup:*' menu select
  zstyle ':completion:*:*:macbackup:*' last-prompt true
  if [[ -t 1 && "$TERM" != dumb && -z "$NO_COLOR" ]]; then
    zstyle ':completion:*:*:macbackup:*' list-colors '=(#b)([a-z-]#)(*)=0=1;34=2'
  fi
  local completion_function=_macbackup
  [[ ${MACBACKUP_LANG:l} == it ]] && completion_function=_macbackup_it
  autoload -Uz "$completion_function"
  if (( $+functions[compdef] )); then
    compdef "$completion_function" macbackup
  fi
}
