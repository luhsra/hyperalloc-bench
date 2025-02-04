#!/bin/bash
set -e

mkdir -p bin

cp -r ../../hyperalloc-qemu/build-virt/qemu-system-x86_64 bin/virtio-qemu-system
cp -r ../../hyperalloc-qemu/build-huge/qemu-system-x86_64 bin/virtio-huge-qemu-system
cp -r ../../hyperalloc-qemu/build/qemu-system-x86_64 bin/llfree-qemu-system

cp -r ../../hyperalloc-linux/build-buddy-vm/arch/x86/boot/bzImage bin/buddy-bzImage
cp -r ../../hyperalloc-linux/build-buddy-huge/arch/x86/boot/bzImage bin/buddy-huge-bzImage
cp -r ../../hyperalloc-linux/build-llfree-vm/arch/x86/boot/bzImage bin/llfree-bzImage

cp -r ../../linux-alloc-bench/build-buddy-vm/alloc.ko bin/build-buddy-alloc.ko
cp -r ../../linux-alloc-bench/build-buddy-huge/alloc.ko bin/build-huge-alloc.ko
cp -r ../../linux-alloc-bench/build-llfree-vm/alloc.ko bin/build-llfree-alloc.ko

# cp -r ../../llfree-rs/target/release/write bin/write
cp ../resources/debian.qcow2 bin

docker build --network=host --build-arg BUILDTIME=$(date +%Y%m%d-%H%M%S) -t ghcr.io/luhsra/hyperalloc_ae . $@

rm -r bin
