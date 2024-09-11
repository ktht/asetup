#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: source $0 /path/to/local/eos/install [experiment]"
  return 1
fi
EOS_DIR=$1

if [ ! -d $EOS_DIR ]; then
  echo "No such directory: $EOS_DIR"
  return 1
fi

EXPERIMENT=atlas
if [ ! -z "$2" ]; then
  EXPERIMENT=$2
fi

export PATH=$EOS_DIR/bin:$EOS_DIR/sbin:$PATH
export LD_LIBRARY_PATH=$EOS_DIR/lib:$LD_LIBRARY_PATH
export PYTHONPATH=$EOS_DIR/lib/python$(python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')")/site-packages:$PYTHONPATH
export EOS_MGM_URL=root://eos$EXPERIMENT.cern.ch
