FROM debian:12

ENV DEBIAN_FRONTEND="noninteractive"

# Dependencies
RUN apt-get -y update ; \
    apt-get -y install apt-utils ; \
    apt-get -y install dumb-init openssh-server sudo iproute2 ; \
    apt-get -y install qemu-system qemu-kvm ; \
    apt-get -y install python3-pip python3-venv ; \
    apt-get -y install build-essential curl git vim htop ; \
    apt-get -y install libncurses-dev gawk flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf llvm-16 clang-16 bc lld lld-16 ; \
    apt-get -y install libglib2.0-dev libfdt-dev libpixman-1-dev zlib1g-dev ninja-build ; \
    apt-get clean && apt-get autoclean

# Default user
# RUN groupadd ssh
RUN useradd -rm -d /home/user -s /bin/bash -g root -G sudo -u 1000 user ; \
    passwd -d user ; \
    mkdir -p /run/sshd ;

ARG BUILDTIME=unknown

# Repositories
# -b artifact-eval
RUN su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-bench.git /home/user/hyperalloc-bench" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-linux.git /home/user/hyperalloc-linux" && \
    su user -c "cd /home/user/hyperalloc-linux && sed -i 's/git@github.com:luhsra\\/llfree-c.git/https:\\/\\/github.com\\/luhsra\\/llfree-c.git/g' .gitmodules && git submodule update --init" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-qemu.git /home/user/hyperalloc-qemu" && \
    su user -c "cd /home/user/hyperalloc-qemu && sed -i 's/git@github.com:luhsra\\/llfree-c.git/https:\\/\\/github.com\\/luhsra\\/llfree-c.git/g' .gitmodules && git submodule update --init subprojects/llfree-c/llc" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-stream.git /home/user/hyperalloc-stream" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-ftq.git /home/user/hyperalloc-ftq" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/linux-alloc-bench.git /home/user/linux-alloc-bench" && \
    echo 1

# Python dependencies
RUN su user -c "cd /home/user/hyperalloc-bench && python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt"

COPY files/halt /bin/
COPY files/sshd_config /etc/ssh/
COPY files/init.sh /

# Prebuild artifacts

## QEMU
RUN -su user -c "mkdir /home/user/hyperalloc-qemu/build-virt && cd /home/user/hyperalloc-qemu/build-virt && CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp"
COPY --chown=user:root bin/virtio-qemu-system /home/user/hyperalloc-qemu/build-virt/qemu-system-x86_64
RUN -su user -c "mkdir /home/user/hyperalloc-qemu/build-huge && cd /home/user/hyperalloc-qemu/build-huge && CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-virtio-balloon-huge"
COPY --chown=user:root bin/virtio-huge-qemu-system /home/user/hyperalloc-qemu/build-huge/qemu-system-x86_64
RUN -su user -c "mkdir /home/user/hyperalloc-qemu/build && cd /home/user/hyperalloc-qemu/build && CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-llfree"
COPY --chown=user:root bin/llfree-qemu-system /home/user/hyperalloc-qemu/build/qemu-system-x86_64

## Linux
COPY --chown=user:root bin/buddy-bzImage /home/user/hyperalloc-linux/build-buddy-vm/arch/x86/boot/bzImage
COPY --chown=user:root bin/buddy-huge-bzImage /home/user/hyperalloc-linux/build-buddy-huge/arch/x86/boot/bzImage
COPY --chown=user:root bin/llfree-bzImage /home/user/hyperalloc-linux/build-llfree-vm/arch/x86/boot/bzImage

## Kernel Module
COPY --chown=user:root bin/buddy-alloc.ko /home/user/linux-alloc-bench/build-buddy-vm/alloc.ko
COPY --chown=user:root bin/buddy-huge-alloc.ko /home/user/linux-alloc-bench/build-buddy-huge/alloc.ko
COPY --chown=user:root bin/llfree-alloc.ko /home/user/linux-alloc-bench/build-llfree-vm/alloc.ko

## Disk Image
COPY --chown=user:root bin/debian.qcow2 /home/user/hyperalloc-bench/resources/debian.qcow2

EXPOSE 2222

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/init.sh"]
