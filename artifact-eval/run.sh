#!/bin/bash
docker run --network=host --device=/dev/kvm --rm ghcr.io/luhsra/hyperalloc_ae $@
