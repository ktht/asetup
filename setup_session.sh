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

vscode_inc () {
  get_alrb || return 1

  if [ -z "$ROOT_INCLUDE_PATH" ] || [ -z "$TestArea" ]; then
    echo "Make sure to run cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=TRUE -DATLAS_ENABLE_IDE_HELPERS=TRUE -DATLAS_PACKAGE_FILTER_FILE=..."
    return 1
  fi

  dir=$TestArea/..
  if [ ! -d $dir/athena ]; then
    echo "The build directory ($TestArea) must be adjacent to athena"
    return 1
  fi

  inc_dir=$dir/include-$alrb_name
  ret_value=0
  if [ ! -d $inc_dir ]; then
    mkdir -v $inc_dir
    for dirn in `echo $ROOT_INCLUDE_PATH | tr ':' '\n' `; do
      if [ ! -d $dirn ]; then
        echo "No such directory: $dirn -> moving on"
        continue
      fi
      for fn in $dirn/*; do
        fn_link=$inc_dir/$(basename $fn)
        if [ ! -e $fn_link ]; then
          ln -sv $fn $fn_link
        else
          echo "ERROR: trying to create symlink for $fn but its target already exist at $(readlink -f $fn_link)"
          ret_value=1
          continue
        fi
      done
    done
  fi

  inc_dir_link=$dir/include
  ln -sfv $inc_dir $inc_dir_link

  return $ret_value
}
