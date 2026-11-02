# Loaded before compinit by ~/.zshrc; also safe to source in an existing shell.
() {
  local completion_dir="$HOME/.zsh/completions"
  [[ -r "$completion_dir/_macbackup" ]] || return 0

  if (( ${fpath[(Ie)$completion_dir]} == 0 )); then
    fpath=("$completion_dir" "${fpath[@]}")
  fi
  autoload -Uz _macbackup
  if (( $+functions[compdef] )); then
    compdef _macbackup macbackup
  fi
}
