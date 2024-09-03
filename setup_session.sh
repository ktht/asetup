#!/bin/bash

if command -v bindkey &>/dev/null; then
  bindkey '\e[1;5C' forward-word
  bindkey '\e[1;5D' backward-word
  bindkey "\033[H" beginning-of-line
  bindkey "\033[F" end-of-line
fi
alias ls='ls --color=auto'
alias l='ls -F'
alias grep='grep --color=auto'
export LESS=-FR

export HISTFILE=/home/$USER/.bash_history
touch $HISTFILE
export HISTSIZE=10000
export SAVEHIST=10000

if [ "$SHELL" = "/bin/bash" ]; then
  shopt -s histappend
else
  setopt SHARE_HISTORY
fi

if [ -f /release_setup.sh ]; then
  source /release_setup.sh
fi
