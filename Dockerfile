ARG name
RUN usermod -aG wheel $name && \
    usermod -u 9999 atlas && usermod -u 1000 $name && usermod -u 1001 atlas && \
    groupmod -g 9999 atlas && groupmod -g 1000 $name && groupmod -g 1001 atlas
