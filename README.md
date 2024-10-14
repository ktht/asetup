# HOWTOs

Just my personal notes for setting up some software and tools.

## How to run ATLAS software in Docker container on Arch(-like) machine

The following assumes that you're running an Arch(-like) system with an NVidia card and have the following packages installed via your favorite package manager: `docker`, `nvidia-container-toolkit`, `cvmfs` (via AUR).
Even though tutorials like [this](https://twiki.cern.ch/twiki/bin/view/AtlasComputing/Cvmfs21), [this](https://cvmfs.readthedocs.io/en/stable/cpt-quickstart.html#setting-up-the-software), [this](https://www.kaggle.com/code/nikolajuselkana/cern-lhcb-open-data-setup) and [this](https://atlassoftwaredocs.web.cern.ch/athena/containers/ubuntu-setup/) all advocate for installing `autofs`, it's not really needed and may in fact cause problems on Arch as hinted [here](https://aur.archlinux.org/cgit/aur.git/tree/cvmfs.install?h=cvmfs).

Before mounting CVMFS directories, edit `/etc/cvmfs/default.local` such that it has (more-or-less) the following contents (except that `$HOME` is replaced with the actual path):
```
CVMFS_REPOSITORIES=atlas.cern.ch,atlas-condb.cern.ch,grid.cern.ch,atlas-nightlies.cern.ch,sft.cern.ch,sft-nightlies.cern.ch,unpacked.cern.ch
CVMFS_CACHE_BASE=$HOME/cache/cvmfs
CVMFS_QUOTA_LIMIT=50000
CVMFS_HTTP_PROXY=DIRECT
CVMFS_USER=root
CVMFS_DEBUGLOG=$HOME/cache/cvmfs.log
CVMFS_CLIENT_PROFILE=single
```

Quick explanation for some of the variables:

- `CVMFS_USER` is set to `root` (instead of the default `cvmfs`) because if this line is not specified, it'll throw `cannot create workspace directory $HOME/cache/cvmfs/shared` error, which likely comes from the fact that mounting to `/cvmfs` requires root privileges;
- `CVMFS_CLIENT_PROFILE` is set to `single` as recommended [in the official docs](https://cvmfs.readthedocs.io/en/stable/cpt-quickstart.html);
- `CVMFS_QUOTA_LIMIT` is the size of CVMFS cache (`CVMFS_CACHE_BASE`) given in MBs;
- `CVMFS_DEBUGLOG` is the log file. You might want to delete it after you're done every session since it might grow to literal GBs within a few days:

    ```
    rm -fv `cat /etc/cvmfs/default.local | grep CVMFS_DEBUGLOG | tr '=' ' ' | awk '{print $2}'`
    ```

Mounting and unmounting is simple:
```
for d in `cat /etc/cvmfs/default.local | grep CVMFS_REPOSITORIES | tr '=' ' ' | awk '{print $2}' | tr ',' ' '`; do
  sudo mkdir -pv /cvmfs/$d;         # needed only once
  sudo mount -t cvmfs $d /cvmfs/$d; # mount
  sudo umount /cvmfs/$d;            # unmount
done
```

Although untested, one could also populate `/etc/fstab` with appropriate lines so that all CVMFS directories would be mounted automatically upon login:
```
for d in `cat /etc/cvmfs/default.local | grep CVMFS_REPOSITORIES | tr '=' ' ' | awk '{print $2}' | tr ',' ' '`; do
  sudo echo '$d /cvmfs/$d cvmfs noauto,x-systemd.automount,x-systemd.requires=network-online.target,x-systemd.idle-timeout=5min,x-systemd.device-timeout=10,_netdev 0 0' >> /etc/fstab'
done
```

If you get an error along the lines of `libprotobuf-lite.so*: cannot open shared object file` after a system-wide update, then make sure to rebuild `cvmfs` with `yay -S --rebuild cvmfs`.
To verify after mounting that everything's correctly set up, run `cvmfs_config probe` and `cvmfs_config showconfig [domain.cern.ch]` to see if you get any errors. You might also want to consult logs in `CVMFS_DEBUGLOG`.

If everything's fine, then start the Docker daemon with `systemctl start docker` and execute:
```
xhost +local:docker
source setupATLAS.sh
setupATLAS -c find=AnalysisBase,25.2.12 \
 --mount=/path/to/pem/certs:/alrb/.globus:delegated,ro \
 --mount=/path/to/vomses:/etc/vomses:delegated,ro \
 --mount=/host/path/to/athena:$HOME/athena:delegated \
 --afterrun="rmdir athena" \
 --mount=$PWD:$HOME:delegated \
 --pwd=$HOME \
 --swtype=docker \
 --runtimeOpt="docker|--env DISPLAY=$DISPLAY -p 8888:8888 --gpus all" \
 --buildFile=Dockerfile \
 --postsetup="source /srv/setup_session.sh"
source setup_venv.sh -v -i jupyter torch # in the container
```

**TODO**: Try out the following Docker option when running `gdb` inside the contianer: `--cap-add=SYS_PTRACE --security-opt seccomp=unconfined`.

Note that setting up `panda` does not work in this container; for that you need vanilla `el9` container.

Make sure that your `/path/to/pem/certs` contains `userkey.pem` and `usercert.pem` files, and that `/path/to/vomses` includes a file called `atlas-voms-atlas-auth.app.cern.ch` with the following contents:
```
"atlas" "voms-atlas-auth.app.cern.ch" "443" "/DC=ch/DC=cern/OU=computers/CN=atlas-auth.web.cern.ch" "atlas"
```
Up-to-date version of this file can be copied from LXPLUS, or extracted from this [webpage](https://www.gridpp.ac.uk/wiki/GridPP_approved_VOs) or [repository](https://github.com/opensciencegrid/osg-vo-config/).

Side note: `setupATLAS` originates from `/etc/hepix/sh/GROUP/zp/group_rc.sh`, which is maintained [here](https://gitlab.cern.ch/linuxsupport/rpms/hepix/-/blob/master/src/etc/hepix/sh/GROUP/zp/group_rc.sh).

The last line in the above installs Jupyter and PyTorch modules. The modules are placed into `$PWD` of the host machine. The directory name where those modules reside is derived from the ATLAS container name. This setup avoids unnecessarily lengthy builds of the same container by keeping the modules outside of it.

When launching a vanilla `el9` container, you might want to drop the `--buildFile` option.
Note that Docker images are cached in your `$HOME/.alrb/container/docker/`.

The Docker container has the following features:

- ability to install custom software system-wide, which is not possible in, e.g., Apptainer;
- access to CVMFS, which is mounted to `/cvmfs` inside the container implicitly;
- possibility to launch Jupyter notebook by forwarding the ports with the `-p 8888:8888` option (which remember to increment when running multiple containers simultaneously):

    ```
    jupyter notebook --ip 0.0.0.0 --port 8888 --no-browser --allow-root
    ```

- X11 forwarding, which is possible due to the `xhost +local:docker` command and the `--env DISPLAY=$DISPLAY` Docker option;
    - run, e.g., `root -a` to see it yourself;
- access to the NVidia GPU of the host (possible thanks to `--gpus all` Docker option):

    ```python
    import torch
    if torch.cuda.is_available() and torch.cuda.device_count():
        print(torch.cuda.get_device_name(0))
    ```

- access to ATLAS VOMS, rucio and AMI services (thanks to mounting the `/alrb/.globus` and `/etc/vomses` directories):

    ```
    setupATLAS
    lsetup rucio

    voms-proxy-init -voms atlas --cert $HOME/.globus/usercert.pem --key $HOME/.globus/userkey.pem
    voms-proxy-info

    rucio list-account-limits $RUCIO_ACCOUNT

    lsetup pyami
    ami list runs --year 24 --data-periods A B

    voms-proxy-destroy
    ```

After everything's said and done, be sure to stop the Docker daemon with `systemctl stop docker` and unmount the CVMFS directories.
If you get an error to the tune of `Stopping 'docker.service', but its triggering units are still active: docker.socket`, then run `systemctl stop docker.socket`.

It's also worth noting that the Docker images can take out a good chunk of your storage.
Thus, make sure that you have enough space to accommodate the images or clean it up regularly.
The images are stored on `/var/lib/docker` by default, but with a simple `rsync -a` command you can copy the files to a different location and edit `/etc/docker/daemon.json` accordingly:

```json
{
    "data-root": "/new/path/to/docker/images"
}
```

Before moving anything, though, make sure to stop all Docker daemon services.

Launching Docker container via `setupATLAS` with the `--buildFile` option prompts Docker to build a new image, which remains "dangling" after exiting the container.
To remove those dangling images, run `docker rmi $(docker images -f "dangling=true" -q)`, but don't use root privileges to remove images that are being used by stopped container, just leave them be.

## How to install EOS client in a Docker container

The following has to be executed *before* sourcing `/release_setup.sh` (by commenting out the corresponding line from `setup_session.sh` and sourcing it after the EOS client has been set up):

```
# Enable EPEL repository: https://docs.fedoraproject.org/en-US/epel/getting-started/
sudo dnf install -y 'dnf-command(config-manager)'
sudo dnf config-manager --set-enabled crb
sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

wget -O eos.repo https://raw.githubusercontent.com/ktht/asetup/main/eos.repo
sudo mv -v eos.repo /etc/yum.repos.d/eos.repo
sudo yum install -y eos-client
```

Then start using it:

```
export EOS_MGM_URL=root://eosatlas.cern.ch # or eoscms.cern.ch for the CMS folk
kinit -f <CERN username>@CERN.CH # note the capitalization
# all EOS commands should now work, e.g.,
eos ls /eos/...
```

## How to install EOS client on a local Arch(-like) machine

We're  trying to install the latest version of the [EOS](https://github.com/cern-eos/eos/) package, which at the time of writing is `5.2.24`.

1. make sure that the following dependencies are installed via arch package manager

    ```
    pacman -S git gcc cmake readline fuse2 fuse3 leveldb binutils zlib bzip2 attr \
              util-linux-libs xfsprogs sparsehash e2fsprogs libmicrohttpd openssl \
              ncurses protobuf cppunit openldap hiredis zeromq jsoncpp cppzmq curl \
              libevent jemalloc
    ```

2. Although [`xrootd`](https://github.com/xrootd/xrootd) is readily available in [Arch repositories](https://gitlab.archlinux.org/archlinux/packaging/packages/xrootd), it's lagging behind: The latest release is `5.7.0`, while the latest package that's available in the Arch repositories is `5.6.4`. Unfortunately, the latter is incompatible with the EOS package since EOS version (5.2.13). The earliest `xrootd` version that's probably compatible with the new header structure is `5.6.7`. However, there's no reason to switch to some old version; instead we'll try to install the latest `xrootd` onto our system, which currently happens to be `5.7.0`. To achieve this, we'll create the following `PKGBUILD` file:

    ```
    pkgname=xrootd
    pkgver=5.7.0
    pkgrel=1
    pkgdesc="Software framework for fast, low latency, scalable and fault tolerant data access."
    arch=('x86_64')
    url="https://xrootd.slac.stanford.edu/"
    license=('LGPL-3.0-or-later')
    source=("https://github.com/xrootd/xrootd/archive/refs/tags/v5.7.0.tar.gz")
    sha256sums=('7a4e5809edd426e6bde7de4848ccc7bcddd33a950b4b3899837ace377292cac8')

    build() {
      cd "${srcdir}/${pkgname}-${pkgver}"
      mkdir build
      cd build
      cmake .. -DCMAKE_INSTALL_PREFIX=/usr
      make
    }

    package() {
      cd "${srcdir}/${pkgname}-${pkgver}/build"
      make DESTDIR="$pkgdir" install
    }
    ```

The SHA256 checksum is calculated from the tarball with `sha256sum`. Check that the `PKGBUILD` file is configured correctly with `namcap PKGBUILD`. Then proceed to build the package with `makepkg`. If everything succeeded, then install the package with `pacman -U xrootd-5.7.0-1-x86_64.pkg.tar.zst`.

3. Install [isa-l](https://github.com/intel/isa-l) and [isa-l_crypto](https://github.com/intel/isa-l_crypto) packages by following the instruction given in those repositories. Here's how it's done for `isa-l`, for example:

    ```
    git clone https://github.com/intel/isa-l.git
    cd isa-l
    git clone -b v2.31 tags/v2.31 # or some later version
    ./autogen.sh
    ./configure --prefix=$PWD/install --libdir=$PWD/install/lib
    make
    make install
    ```

    The procedure is identical for `isa-l_crypto`, apart from its version which doesn't necessarily match the version of `isa-l`. At the time of writing, the latest version of `isa-l_crypto` is `v2.25.0`.

4. A keen eye reading the [EOS documentation](https://github.com/cern-eos/eos/blob/master/README.md) might spot that EOS has two additional dependencies: `eos-folly` and `eos-rocksdb`. Both correspond to custom builds of [`rocksdb`](https://github.com/facebook/rocksdb) and [`folly`](https://github.com/facebook/folly). The build configurations are detailed in the `*.spec` files of [`eos-rocksdb`](https://gitlab.cern.ch/eos/eos-rocksdb) and [`eos-folly`](https://gitlab.cern.ch/eos/eos-folly) repositories. The `*.patch` files are irrelevant because both packages already include the described changes.

    Although `rocksdb` is also available as [Arch package](https://gitlab.archlinux.org/archlinux/packaging/packages/rocksdb), it does not include the `librocksdb_tools.so` library, which is linked against EOS build.
    Thus, to build `rocksdb`, follow these instructions:

    ```
    git clone https://github.com/facebook/rocksdb.git
    cd rocksdb
    git checkout -b v9.5.2 tags/v9.5.2 # or later
    PREFIX=$PWD/install PORTABLE=1 DISABLE_JEMALLOC=1 OPT='-fPIC -DNDEBUG -O3' make shared_lib tools_lib USE_RTTI=1 DEBUG_LEVEL=0 -j12
    PREFIX=$PWD/install make install-shared
    cp librocksdb_tools.so install/lib/.
    ```

5. Installing `folly` follows a similar patter with just two caveats:

- `CMake/folly-deps.cmake` needs to be patched as detailed [here](https://aur.archlinux.org/cgit/aur.git/tree/fix-cmake-find-glog.patch?h=folly), or otherwise you'll face compilation errors to the tune of `#  error <glog/logging.h> was not included correctly`:
    ```diff
    diff --git a/CMake/folly-deps.cmake b/CMake/folly-deps.cmake
    index d51f11128..f41753ef2 100644
    --- a/CMake/folly-deps.cmake
    +++ b/CMake/folly-deps.cmake
    @@ -64,10 +64,9 @@ if(LIBGFLAGS_FOUND)
      set(FOLLY_LIBGFLAGS_INCLUDE ${LIBGFLAGS_INCLUDE_DIR})
    endif()

    -find_package(Glog MODULE)
    -set(FOLLY_HAVE_LIBGLOG ${GLOG_FOUND})
    -list(APPEND FOLLY_LINK_LIBRARIES ${GLOG_LIBRARY})
    -list(APPEND FOLLY_INCLUDE_DIRECTORIES ${GLOG_INCLUDE_DIR})
    +find_package(Glog CONFIG REQUIRED)
    +set(FOLLY_HAVE_LIBGLOG True)
    +list(APPEND FOLLY_LINK_LIBRARIES glog::glog)

    find_package(LibEvent MODULE REQUIRED)
    list(APPEND FOLLY_LINK_LIBRARIES ${LIBEVENT_LIB})
    ```
- the C++ compilation flags used in building `folly` need to match the compilation flags when building EOS, or otherwise you'd get a cryptic `Undefined symbols for architecture x86_64:
"folly::f14::detail::F14LinkCheck<(folly::f14::detail::F14IntrinsicsMode)1>::check()"` error as explained in [this GitHub comment](https://github.com/facebook/folly/issues/1939#issuecomment-1442414882) as well as [in the source code itself](https://github.com/facebook/folly/blob/v2024.08.26.00/folly/container/detail/F14Table.h#L129-L138).

    Here are complete instructions for building `folly`:

    ```
    git clone https://github.com/facebook/folly.git
    cd folly
    git checkout -b v2024.08.26.00 tags/v2024.08.26.00
    curl https://github.com/facebook/folly/compare/v2024.08.26.00...ktht:folly:v2024.08.26.00-arch-patch.diff | git apply
    mkdir bin && cd $_
    export CXXFLAGS="-g3 -fPIC -Wno-nonnull -march=native"
    cmake -DCMAKE_INSTALL_PREFIX:PATH=$PWD/../install -DBUILD_SHARED_LIBS=ON ..
    make
    make install
    ```

6. It's finally time to build EOS. However, there are multiple issues with the code that need to be patched:

- `CMAKE_INSTALL_SYSCONFDIR` is hardcoded to `/etc` and it's not possible to overwrite it when trying to install the build to some local directory without root privileges. Here's the patch:
    ```diff
    diff --git a/CMakeLists.txt b/CMakeLists.txt
    index 853949c31..b2e809eef 100644
    --- a/CMakeLists.txt
    +++ b/CMakeLists.txt
    @@ -103,7 +103,7 @@ if (NOT PACKAGEONLY)
      include(EosCompileFlags)
    endif()

    -set(CMAKE_INSTALL_SYSCONFDIR /etc)
    +set(CMAKE_INSTALL_SYSCONFDIR "/etc" CACHE PATH "")
    include(EosFindLibs)

    #-------------------------------------------------------------------------------
    ```
- the same goes for `PYTHONSITEPKG_PATH`, which defaults to `/usr/lib/python...`. The patch is:
    ```diff
    diff --git a/archive/CMakeLists.txt b/archive/CMakeLists.txt
    index 7987d8f29..479fe5e19 100644
    --- a/archive/CMakeLists.txt
    +++ b/archive/CMakeLists.txt
    @@ -30,13 +30,13 @@ if(PYTHONSITEPKG_FOUND)
                          WORLD_READ WORLD_EXECUTE)

      install(DIRECTORY eosarch
    -         DESTINATION ${PYTHONSITEPKG_PATH}
    +         DESTINATION ${CMAKE_INSTALL_FULL_LIBDIR}/python${PYTHON_VERSION}/site-packages
              PATTERN "tests" EXCLUDE
              PATTERN "*~" EXCLUDE
              PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ)

      install(FILES opt-eos-xrootd.pth
    -         DESTINATION ${PYTHONSITEPKG_PATH}
    +         DESTINATION ${CMAKE_INSTALL_FULL_LIBDIR}/python${PYTHON_VERSION}/site-packages
              PERMISSIONS OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ)

      install(FILES eosarchived.conf
    diff --git a/cmake/FindPythonSitePkg.cmake b/cmake/FindPythonSitePkg.cmake
    index f3c66de2b..c4039030a 100644
    --- a/cmake/FindPythonSitePkg.cmake
    +++ b/cmake/FindPythonSitePkg.cmake
    @@ -11,6 +11,7 @@ if(NOT Python3_Interpreter_FOUND)
      return()
    else()
      set(PYTHONSITEPKG_FOUND TRUE)
    +  set(PYTHON_VERSION "${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}")
    endif()

    if(Python3_SITELIB)
    ```
- `boost_context` library is not properly linked in the build. Applying this patch gets around the problem:
    ```diff
    diff --git a/cmake/Findeosfolly.cmake b/cmake/Findeosfolly.cmake
    index 13bc42309..c9af44d0c 100644
    --- a/cmake/Findeosfolly.cmake
    +++ b/cmake/Findeosfolly.cmake
    @@ -41,7 +41,7 @@ endif()

    # This is done to preserve compatibility with qclient
    set(FOLLY_INCLUDE_DIRS ${EOSFOLLY_INCLUDE_DIR})
    -set(FOLLY_LIBRARIES    ${EOSFOLLY_LIBRARY} glog gflags)
    +set(FOLLY_LIBRARIES    ${EOSFOLLY_LIBRARY} glog gflags boost_context)
    set(FOLLY_FOUND TRUE)
    unset(EOSFOLLY_LIBRARY)
    unset(EOSFOLLY_INCLUDE_DIR)
    ```
- since [`26.0-rc2`](https://github.com/protocolbuffers/protobuf/releases/tag/v26.0-rc2) of `protobuf`, the `always_print_primitive_fields` field is deprecated in favor of `always_print_fields_with_no_presence`. The latest `protobuf` package that's available on Arch machines is already at version `27.3`. The easiest way to fix the issue is to run the following:
  ```bash
  sed -i 's/always_print_primitive_fields/always_print_fields_with_no_presence/g' $(grep -rl 'always_print_primitive_fields' .)
  ```

    With that in mind, here are the instructions for building EOS:

    ```
    git clone https://github.com/cern-eos/eos.git
    cd eos
    git checkout -b 5.2.24 tags/5.2.24
    curl https://github.com/cern-eos/eos/compare/5.2.24...ktht:eos:5.2.24-sysconfdir-patch.diff | git apply
    curl https://github.com/cern-eos/eos/compare/5.2.24...ktht:eos:5.2.24-pythonsite-patch.diff | git apply
    curl https://github.com/cern-eos/eos/compare/5.2.24...ktht:eos:5.2.24-boost_context-patch.diff | git apply
    curl https://github.com/cern-eos/eos/compare/5.2.24...ktht:eos:5.2.24-protobuf-patch.diff | git apply # or the sed command
    mkdir build-ninja && cd $_
    # /path/to = where you installed the libraries in previous steps
    cmake \
      -DROCKSDB_TOOLS_LIBRARY=/path/to/rocksdb/install/lib/librocksdb_tools.so \
      -DROCKSDB_LIBRARY=/path/to/rocksdb/install/lib/librocksdb.so \
      -DROCKSDB_INCLUDE_DIR=/path/to/rocksdb/install/include \
      -DISAL_ROOT=/path/to/isa-l/install \
      -DISAL_CRYPTO_ROOT=/path/to/isa-l_crypto/install \
      -DEOSFOLLY_LIBRARY=/path/to/folly/install/lib/libfolly.so \
      -DEOSFOLLY_INCLUDE_DIR=/path/to/folly/install/include \
      -DCMAKE_INSTALL_PREFIX:PATH=$PWD/../install \
      -DCMAKE_INSTALL_SYSCONFDIR=$PWD/../install/etc \
      -GNinja \
      -Wno-dev \
      -DCMAKE_CXX_FLAGS="-DGLOG_USE_GLOG_EXPORT -march=native" \
      ..
    ninja -j12 |& tee out.log
    ninja install
    ```

7. To run any EOS commands, you need to set up some environment variables and authenticate yourself with Kerberos:

    ```
    export PATH=$PWD/../install/bin:$PWD/../install/sbin:$PATH
    export LD_LIBRARY_PATH=$PWD/../install/lib:$LD_LIBRARY_PATH
    export PYTHONPATH=$PWD/../install/lib/python3.12/site-packages:$PYTHONPATH
    # <experiment> = atlas, cms, lhcb, theory, ... if you want to access /eos/<experiment>
    export EOS_MGM_URL=root://eos<experiment>.cern.ch
    kinit -f <CERN username>@CERN.CH
    ```

    The following commands should now work:

    ```
    eos ls -lh /eos/...
    eos attr ls /eos/...
    eos cp /eos/... /local/path
    xrdcp $EOS_MGM_URL//eos/... /local/path # equivalent to the previous line
    ```

    Interactive `eos` also works.

    The instructions for mounting `/eos` to local host are detailed [here](https://gitlab.cern.ch/dss/eos/-/blob/master/fusex/README.md#configuration-default-values-and-avoiding-configuration-files).
    To summarize:

    ```
    mkdir -p $HOME/eos
    eosxd3 -ofsname=<CERN username>@eos<experiment>.cern.ch:/eos/... $HOME/eos
    ```

    Mounting to `/eos/user` and `/eos/project` is complicated by the fact that `/eos/{user,project}/[a-z]` is a symlink to `/eos/{home,project}-[a-z]`, e.g., `/eos/user/t/testuser` resolves to `/eos/home-t/testuser` remotely.
    However, those symlink targets are not accessible from the `eosuser` host.
    In order to get around this problem, you need to mount `/eos/{home,project}-[a-z]` directory explicitly using `eos{home,project}-[a-z].cern.ch` as the hostname, e.g., `eoshome-t.cern.ch:/eos`, which gives access to `user/t` subdirectory from the mount point of your local machine.
    Thus, to mount multiple user directories, it's better to mount at the subdirectory level as follows: `eos{home,project}-[a-z].cern.ch:/eos/{user,project}/[a-z] ~/eos/{user,project}/[a-z]`.

    EOS directories are mounted through FUSE, which gives access to those directories via POSIX interface.
    In other words, you can use the same `ls`, `cd`, `find`, etc commands in EOS directories as if they were on local filesystem.
    When copying large files from EOS to local filesystem, it may be convenient to track progress with `rsync -ah --progress`.

    To unmount, simply run `fusermount3 -uz $HOME/eos`.

    In order to mount `/eos` to a Docker container (via, e.g., `--mount=$HOME/eos/:/eos:delegated,ro` option that's passed to `setupATLAS`, see above), you first need to make sure that `user_allow_other` is uncommented in `/etc/fuse.conf` (which is completely fine in single-user environment) before running:

    ```
    eosxd3 -oallow_other,fsname=<CERN username>@eos<experiment>.cern.ch:/eos/... $HOME/eos
    ```

    Note that editing `/etc/fuse.conf` would be needed even when running the above command as `root`.

    More fine-granular control over the mounting options can be assumed with JSON configuration file `$HOME/.eos/fuse.<name>.conf`, which you can write based on [`./fusex/fuse.conf.example`](https://gitlab.cern.ch/dss/eos/-/blob/master/fusex/fuse.conf.example).
    Not all options need to be defined, as other options not defined in the configuration file will simply resort to their default values.
    To mount EOS filesystem with the options defined in the JSON configuration file, just run `eosxd3 -ofsname=<name>`.
    It's worth noting that it's not possible to propagate `allow_other` option from the JSON configuration file to the mount options.

    Of course, all these steps can be bypassed by mouting with `sshfs`, e.g., `sshfs lxplus.cern.ch:/some/remote/directory /some/local/directory`, where `/some/remote/directory` can be any AFS or EOS path.
    Since `sshfs` relies on FUSE libraries it provides the same POSIX interface as in EOS mounts.
    Unmounting is also the same.

## Docker and VSCode

This section describes how to run VSCode together with Docker.
The main advantage of this method over running VSCode via SSH is mainly latency, as there's no lag induced by the network (except for CVMFS caching) nor the filsystem, which can be notoriously bad on LXPLUS.
Furthermore, if an LXPLUS node goes down then access to the code is also lost.

### Docker started from VSCode

For whatever reason Docker in Athena is configured to use past-EOL CC7 with an outdated mirror to EPEL repository and old `pip` version.
Here's a patch that resolves both problems:

```diff
diff --git a/.devcontainer/Dockerfile b/.devcontainer/Dockerfile
index 6501acef459..c94e5d929fb 100644
--- a/.devcontainer/Dockerfile
+++ b/.devcontainer/Dockerfile
@@ -7,6 +7,21 @@ FROM cern/cc7-base:latest
 USER root
 WORKDIR /root

+# Patch the EPEL repository file
+RUN echo -e '[epel]\n\
+name=Extra Packages for Enterprise Linux 7 - $basearch\n\
+baseurl=https://archives.fedoraproject.org/pub/archive/epel/7/$basearch\n\
+enabled=1\n\
+gpgcheck=0\n\
+gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-7\n\
+\n\
+[epel-debuginfo]\n\
+name=Extra Packages for Enterprise Linux 7 - $basearch - Debug\n\
+baseurl=https://archives.fedoraproject.org/pub/archive/epel/7/$basearch/debug\n\
+enabled=0\n\
+gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-7\n\
+gpgcheck=0\n' > /etc/yum.repos.d/epel.repo
+
 # Install some additional packages.
 RUN yum -y install which sclo-git212 wget tar atlas-devel libuuid-devel texinfo \
            python2-pip redhat-lsb-core libX11-devel libXpm-devel libXft-devel  \
@@ -25,7 +40,7 @@ COPY atlas_prompt.sh setup_atlas.sh enable_sclo_git212.sh /etc/profile.d/
 COPY motd /etc/

 # Install flake8 python linter
-RUN pip install flake8 six
+RUN pip install flake8 six --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org
 RUN scl enable sclo-git212 'pip install git+https://:@gitlab.cern.ch:8443/atlas/atlasexternals.git#subdirectory=External/flake8_atlas'

 # Switch to the ATLAS account.
```

As described in the [original docs](https://atlassoftwaredocs.web.cern.ch/athena/ide/docker/), before VSCode's IntelliSense regonizes any source code it is imperative to first build something in the Athena project. To do this you have to create a `build` directory outside of the Athena project (here we create it next to the Athena directory), set up your working area and run `cmake` in it:

```
mkdir build && cd $_
asetup AthAnalysis,24.2.41
source x86_64-el9-gcc13-opt/setup.sh
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=TRUE \
      -DATLAS_ENABLE_IDE_HELPERS=TRUE \
      -DATLAS_PACKAGE_FILTER_FILE=../athena/Projects/WorkDir/package_filters_example.txt \
      ../athena/Projects/WorkDir
```

Note that `asetup` is not available in Athena containers.

The `ATLAS_ENABLE_IDE_HELPERS` flag is responsible for creating symlinks `ide_compiler` and `ide_python`, which point to particular versions of GCC and Python compilers on CVFMS depending on the Athena release.

### Attaching VSCode to a running Docker container

Alternatively, instead of launching the Docker from wihtin VSCode (`Dev Containers: Open Folder in Container...`) one could also launch it in a separate terminal and then connect to it from VSCode (`Dev Containers: Attach to Running Container...`).
This might be more convenient as it wouldn't entail editing the `Dockerfile` that's part of the athena repository.

Unfortunately, VSCode's IntelliSense doesn't seem to work properly when run in Docker.
The main issue is that when launching a Docker session within VSCode or when attaching to an already running container, it's unable to autodetect the include paths that are necessary for IntelliSense to work.
It's the responsibility of the user to set up the environment properly.
Ideally, these environment variables would be propagated from [standard shell scripts](https://code.visualstudio.com/docs/supporting/faq#_resolving-shell-environment-fails) to IntelliSense, but as other have [noted](https://github.com/microsoft/vscode-cpptools/issues/11186) it's not really the case.
Furthermore, while propagating environment variables from a container is theoretically [possible](https://code.visualstudio.com/docs/devcontainers/attach-container#_variables-in-attached-container-configuration-files), it's probably too difficult to propagate anything from a *shell session* that's already running in the container to IntelliSense.
That's also probably why VSCode is unable to detect the compiler when attaching to a Docker container where the environment was set up manually.
Ideally, these paths could be passed to IntelliSense the same way as paths to Python modules (i.e., by dumping them to a text file like `env.txt` as shown [here](https://gitlab.cern.ch/atlas/athena/-/blob/main/.vscode/IDEHelperScripts/Setup.cmake) and then passing the text file to [`"python.envFile"` setting](https://code.visualstudio.com/docs/python/environments#_environment-variable-definitions-file), but C/C++ IntelliSense configuration doesn't support this feature yet.

The solution to this conundrum isn't elegant but it's guaranteed to work.
First, you need to patch the `c_cpp_properties.json` file as follows:

```diff
diff --git a/.vscode/c_cpp_properties.json b/.vscode/c_cpp_properties.json
index 7430a59e918..a2635a59c6f 100644
--- a/.vscode/c_cpp_properties.json
+++ b/.vscode/c_cpp_properties.json
@@ -3,7 +3,8 @@
         {
             "name": "Linux",
             "includePath": [
-                "${workspaceFolder}/**"
+                "${workspaceFolder}/**",
+                "${workspaceFolder}/../include"
             ],
             "defines": [],
             "compilerPath": "${workspaceFolder}/../build/ide_compiler",
```

Then call `vscode_setup` in the Docker session and wait until it creates the symlinks for every single header file or directory that's stored in the directories given by `$ROOT_INCLUDE_PATH`.
The function also sets up container-specific hidden directory for hosting VSCode server files.
The symlinks are created inside `include` directory, which is adjacent to the `build` and `athena` directories.
The `include` directory itself is a symlink to the actual directory hosting the symlinks.
The actual directory is given a unique name based on container name and `asetup` arguments to distinguish it from other `include` directories created in different conditions.
When a new build directory is created with a different setup, then the existing `include` symlink is pointed to the new directory containing the symlinks.
To illustrate the point, here's how the directory structure might look after multiple builds:

```
athena/
include -> build/../include-atlas-grid-almalinux9-AthAnalysis-24.2.41/
include-atlas-grid-almalinux9-AthAnalysis-24.2.41/
include-atlas-grid-almalinux9-AnalysisBase-25.2.12/
build/
```

### VSCode with custom CMake projects

If you want to enjoy IntelliSense in your custom CMake project, make sure to copy [the `.vscode` directory from Athena](https://gitlab.cern.ch/atlas/athena/-/tree/main/.vscode) to your project's root directory with the aforementioned patch to `c_cpp_properties.json` and include the following lines to your `CMakeLists.txt` (before `atlas_cpack_setup`?) that you want to build from:

```cmake
# Setup IDE integration:
set( ATLAS_ENABLE_IDE_HELPERS OFF CACHE BOOL "Enable IDE helpers" )
if( ATLAS_ENABLE_IDE_HELPERS )
   set( ATLAS_IDEHELPERSCRIPTS_SETUP
      "${CMAKE_SOURCE_DIR}/.vscode/IDEHelperScripts/Setup.cmake"
      CACHE FILEPATH "Setup file for the IDE / VS Code helpers" )
   include( "${ATLAS_IDEHELPERSCRIPTS_SETUP}" )
endif()
```

Note that if the `CMakeLists.txt` file you want to build from is in a subdirectory relative to your project's root directory (`${CMAKE_SOURCE_DIR}`) you have to modify `${ATLAS_IDEHELPERSCRIPTS_SETUP}` accordingly.
