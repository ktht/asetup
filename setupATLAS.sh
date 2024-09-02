#!/bin/bash

function setupATLAS
{
    if [ -d  /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase ]; then

        export ALRB_localConfigDir="/etc/hepix/sh/GROUP/zp/alrb"

        export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase
        source $ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh
        return $?
    else
        \echo "Error: cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase is unavailable" >&2
        return 64
    fi
}
