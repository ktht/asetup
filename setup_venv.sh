#!/bin/bash

print_help() {
  echo "Usage: $0 [-i|--install <jupyter|torch>] -v|--venv [<directory>] [-r|--requirements <requirements>] [-h|--help]"
  echo ""
  echo "Options:"
  echo "  -v, --venv [<directory>]          Specify a virtual environment directory"
  echo "  -i, --install <jupyter|torch>     Install specified packages"
  echo "  -r, --requirements <requirements> Installation requirements (e.g., requests<=2.31.0)"
  echo "  -h, --help                        Show this help message"
}

if [ ! -z $VIRTUAL_ENV ]; then
  echo "venv already set to: $VIRTUAL_ENV";
  echo "Run 'deactivate' and try again";
  return 1;
fi

install_jupyter=0
install_torch=0
venv_dir=""
venv_provided=0
requirements=""

while [[ $# -gt 0 ]]; do
  case $1 in
    -i|--install)
      shift
      while [[ $# -gt 0 && $1 != -* ]]; do
        case $1 in
          jupyter)
            install_jupyter=1
            ;;
          torch)
            install_torch=1
            ;;
          *)
            echo "Invalid argument for -i|--install: $1"
            print_help
            return 1
            ;;
        esac
        shift
      done
      ;;
    -v|--venv)
      venv_provided=1
      if [[ -n "$2" && "$2" != -* ]]; then
        venv_dir="$2"
        shift 2
      else
        venv_dir=""
        shift
      fi
      ;;
    -r|--requirements)
      shift
      while [[ $# -gt 0 && $1 != -* ]]; do
        requirements="$requirements $1"
        shift
      done
      if [[ -z "$requirements" ]]; then
        echo "No arguments provided for -r|--requirements: $requirements"
        print_help
        return 1
      fi
      ;;
    -h|--help)
      print_help
      return 0
      ;;
    *)
      echo "Invalid option: $1" >&2
      print_help
      return 1
      ;;
  esac
done

if [ $venv_provided -eq 0 ]; then
  echo "Error: -v/--venv option is required."
  echo "venv_provided = $venv_provided"
  print_help
  return 1
fi

if [ -z $AtlasProject ]; then
  echo "Set up ATLAS project first!"
  return 1
fi

venv_default=$(echo $ALRB_CONT_IMAGE | awk -F'/' '{print $NF}' | sed 's/:/-/g; s/=/-/g')
project_name=${AtlasProject}-$(eval echo \$$AtlasProject\_VERSION)
if [ "$(echo $project_name | tr '[:upper:]' '[:lower:]')" != "$venv_default" ]; then
  venv_default=${venv_default}-${project_name}
fi
venv_default=venv-${venv_default}

if [ -z "$venv_dir" ]; then
  venv_dir=$venv_default
  echo "No venv provided, defaulting to: $venv_dir"
fi

if [ -f $venv_dir/pyvenv.cfg ]; then
  pip_home=$(grep home $venv_dir/pyvenv.cfg | awk '{print $3}')
  if ! echo $PATH | grep $pip_home &>/dev/null; then
    echo "Incompatible venv directory: $venv_dir"
    echo "Expected the following path to pip: $pip_home"
    echo "Try creating a new venv with, e.g., --venv $venv_default"
    return 1
  fi
else
  echo "Not a venv directory: $venv_dir"
  echo "Creating one ..."
  mkdir $venv_dir && python -m venv $venv_dir
fi

source $venv_dir/bin/activate

if [ $install_jupyter -eq 1 ]; then
  if ! pip show jupyter &> /dev/null; then
    echo "Installing Jupyter ..."
    pip install jupyter $requirements
  else
    echo "Jupyter already installed"
  fi

  export LESSOPEN="| pygmentize -O bg=light %s 2> >(grep -v \"Error: no lexer for filename\" >&2)"

  container_port=$(echo $ALRB_CONT_CMDOPTS | sed -n 's/.*-p [0-9]*:\([0-9]*\).*/\1/p')
  if [ -z $container_port ]; then
    echo "Could not find the container port. Did you launch the docker container with: -p <host port>:<container port>?"
    return 1
  else
    echo "Run the following to launch a jupyter notebook:"
    echo ""
    echo "    jupyter notebook --ip 0.0.0.0 --port $container_port --no-browser --allow-root"
    echo ""
  fi
fi

if [ $install_torch -eq 1 ]; then
  if ! pip show torch &> /dev/null; then
    echo "Installing PyTorch ..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  else
    echo "PyTorch already installed"
  fi

  if ! echo $ALRB_CONT_CMDOPTS | grep "\-\-gpus all" &>/dev/null; then
    echo "Did you launch the docker container with: --gpus all?"
    return 1
  fi
fi
