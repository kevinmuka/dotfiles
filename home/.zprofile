if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

export PATH="/usr/local/texlive/2025/bin/universal-darwin:$PATH"
export PATH="$HOME/.local/bin:$PATH"
export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"

export PATH="$PATH:/$HOME/.config/scripts"

# Added by Antigravity CLI installer
export PATH="/Users/kevinmuka/.local/bin:$PATH"

# Use the locally cached Go toolchain when available.
go_toolchain_bin="$HOME/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.25.9.darwin-arm64/bin"
if [[ -x "$go_toolchain_bin/go" ]]; then
  export PATH="$go_toolchain_bin:$PATH"
fi
unset go_toolchain_bin
