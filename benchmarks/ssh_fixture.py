"""Open a disposable local SSH session using a runtime-only keypair."""

import subprocess

import paramiko


def open_ephemeral_ssh(container_name):
    """Install a generated public key, then connect through Docker stdio SSH."""
    key = paramiko.RSAKey.generate(2048)
    public_key = f"{key.get_name()} {key.get_base64()} local-benchmark\n"
    install_command = (
        "install -d -m 700 -o benchmark -g benchmark /home/benchmark/.ssh "
        "&& cat > /home/benchmark/.ssh/authorized_keys "
        "&& chown benchmark:benchmark /home/benchmark/.ssh/authorized_keys "
        "&& chmod 600 /home/benchmark/.ssh/authorized_keys"
    )
    subprocess.run(
        ["docker", "exec", "-i", container_name, "sh", "-c", install_command],
        input=public_key, text=True, check=True,
    )

    proxy = paramiko.ProxyCommand(
        f"docker exec -i {container_name} /usr/sbin/sshd -i"
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            container_name, username="benchmark", pkey=key, sock=proxy,
            look_for_keys=False, allow_agent=False, timeout=10,
        )
    except Exception:
        proxy.close()
        raise
    return client


def remove_ephemeral_ssh_key(container_name):
    """Remove the temporary public key after the SSH client has closed."""
    subprocess.run(
        ["docker", "exec", container_name, "rm", "-f",
         "/home/benchmark/.ssh/authorized_keys"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
