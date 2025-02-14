#!/bin/bash

if [ -z "$AUTHORIZED_KEYS" ]; then
  echo "Please provide the public key in the AUTHORIZED_KEYS environment variable."
  echo "Example: docker run -e AUTHORIZED_KEYS=\"$(cat ~/.ssh/id_rsa.pub)\" ..."
  exit 1
fi

# save the authorized keys
echo "Saving authorized keys..."
mkdir -p /home/user/.ssh
echo "$AUTHORIZED_KEYS" > /home/user/.ssh/authorized_keys

echo 'Starting SSH server...'
exec /usr/sbin/sshd -D
