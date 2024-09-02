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

source /release_setup.sh
