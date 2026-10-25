FROM postgres:17.11
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends openssh-server \
    && mkdir -p /run/sshd \
    && useradd -m -s /bin/bash benchmark \
    && printf '\nPasswordAuthentication no\nPubkeyAuthentication yes\nPermitRootLogin no\nAllowUsers benchmark\n' >> /etc/ssh/sshd_config \
    && ssh-keygen -A \
    && rm -rf /var/lib/apt/lists/*
