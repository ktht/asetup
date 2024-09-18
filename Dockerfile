ARG name
RUN usermod -aG wheel $name && \
    usermod -u 9999 atlas && usermod -u 1000 $name && usermod -u 1001 atlas && \
    groupmod -g 9999 atlas && groupmod -g 1000 $name && groupmod -g 1001 atlas
RUN sudo dnf install --disablerepo='*' --enablerepo='baseos' -y time # https://linuxsoft.cern.ch/cern/alma/9/BaseOS/x86_64/os/Packages/time-*.el9.x86_64.rpm
