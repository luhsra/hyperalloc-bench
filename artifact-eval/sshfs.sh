#!/bin/bash
if [ -z "$KEY" ]; then
    echo "Please provide a path to your private ssh key in the KEY environment variable."
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

mkdir -p hyperalloc_ae
sshfs -o IdentityFile=$KEY -o NoHostAuthenticationForLocalhost=yes -p 2222 user@localhost:/home/user hyperalloc_ae
