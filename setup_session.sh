#!/bin/bash

if command -v bindkey &>/dev/null; then
  bindkey '\e[1;5C' forward-word
  bindkey '\e[1;5D' backward-word
  bindkey "\033[H" beginning-of-line
  bindkey "\033[F" end-of-line
fi
alias ls='ls --color=auto'
alias l='ls -F'
alias ll='l -l'
alias grep='grep --color=auto'
export LESS=-FR

export HISTFILE=/home/$USER/.bash_history
touch $HISTFILE
export HISTSIZE=10000
export SAVEHIST=10000

export PATH=$PATH:/home/$USER

if [ "$SHELL" = "/bin/bash" ]; then
  shopt -s histappend
else
  # we're in zsh
  setopt SHARE_HISTORY
  export PROMPT="%B%F{red}[%f%b%B%F{red}%n %f%b%B%F{red}@ %f%b%B%F{red}$ALRB_CONT_SETUPATLASOPT%f%b%F{red}]%f%B%F{blue}: %f%b%B%F{blue}%~%f%b%B%F{blue} > %f%b"
fi

if [ -f /release_setup.sh ]; then
  source /release_setup.sh
fi

get_alrb () {
  if [ -z $AtlasProject ]; then
    echo "Set up ATLAS project first!"
    return 1
  fi
  alrb_name=$(echo $ALRB_CONT_IMAGE | awk -F'/' '{print $NF}' | sed 's/:/-/g; s/=/-/g')
  project_name=${AtlasProject}-$(eval echo \$$AtlasProject\_VERSION)
  if [ "$(echo $project_name | tr '[:upper:]' '[:lower:]')" != "$alrb_name" ]; then
    alrb_name=${alrb_name}-${project_name}
  fi
  export alrb_name
}

vscode_setup () {
  get_alrb || return 1

  vscode_server_default=/home/$USER/.vscode-server-$alrb_name
  vscode_server_target=$ALRB_CONT_DUMMYHOME/.vscode-server

  mkdir -pv $vscode_server_default
  ln -sfv $vscode_server_default $vscode_server_target
}
