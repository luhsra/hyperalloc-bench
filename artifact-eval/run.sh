#!/bin/bash
docker run -p 127.0.0.1:2222:2222 --device=/dev/kvm $@ --rm ghcr.io/luhsra/hyperalloc_ae
