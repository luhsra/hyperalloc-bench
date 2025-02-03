#!/bin/bash
mkdir -p hyperalloc_ae
sshfs -o NoHostAuthenticationForLocalhost=yes -p 2222 user@localhost:/home/user hyperalloc_ae
