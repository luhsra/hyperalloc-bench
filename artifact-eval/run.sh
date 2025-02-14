#!/bin/bash
if [ -z "$KEY" ]; then
    echo "Please provide a path to your private ssh key in the KEY environment variable."
    echo "If you don't have a key pair, you can generate one with ssh-keygen."
    exit 1
fi
if [ ! -f "$KEY" ]; then
    echo "The specified private key file '$KEY' does not exist."
    exit 1
fi
if [ ! -f "$KEY.pub" ]; then
    echo "The public key file '$KEY.pub' does not exist."
    exit 1
fi

AUTHORIZED_KEYS=$(cat "$KEY.pub")

echo "You can connect to the container with the following command:"
echo "  ssh -p2222 -i $KEY user@localhost"
echo ""

docker run -p 127.0.0.1:2222:2222 --device=/dev/kvm -e AUTHORIZED_KEYS="$AUTHORIZED_KEYS" $@ --rm ghcr.io/luhsra/hyperalloc_ae
