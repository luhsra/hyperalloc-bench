FROM debian:12

# Dependencies
RUN apt-get -y update ; \
    apt-get -y install dumb-init openssh-server sudo ; \
    apt-get -y install qemu qemu-kvm ; \
    apt-get -y install python3-pip python3-venv python3-psutil python3-seaborn python3-pandas ; \
    apt-get -y install build-essential curl git vim htop ; \
    apt-get -y install libncurses-dev gawk flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf llvm-16 clang-16 bc lld lld-16 ; \
    apt-get clean && apt-get autoclean

# Default user
RUN useradd -rm -d /home/user -s /bin/bash -g root -G sudo,ssh -u 1000 user ; \
    passwd -d user ; \
    mkdir -p /run/sshd ;

# Repositories
RUN su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-bench.git -b artifact-eval /home/user/hyperalloc-bench" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-linux.git -b artifact-eval /home/user/hyperalloc-linux" && \
    su user -c "cd /home/user/hyperalloc-linux && git submodule update --init" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-qemu.git -b artifact-eval /home/user/hyperalloc-qemu" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-stream.git -b artifact-eval /home/user/hyperalloc-stream" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/hyperalloc-ftq.git -b artifact-eval /home/user/hyperalloc-ftq" && \
    su user -c "git clone --depth 1 https://github.com/luhsra/linux-alloc-bench.git -b artifact-eval /home/user/linux-alloc-bench" && echo 1

COPY files/halt /bin/
COPY files/sshd_config /etc/ssh/
COPY files/init.sh /

# Prebuild artifacts
COPY --chown=user:root bin/virtio-qemu-system /home/user/hyperalloc-qemu/build-virtio/qemu-system-x86_64
COPY --chown=user:root bin/virtio-huge-qemu-system /home/user/hyperalloc-qemu/build-huge/qemu-system-x86_64
COPY --chown=user:root bin/llfree-qemu-system /home/user/hyperalloc-qemu/build/qemu-system-x86_64

COPY --chown=user:root bin/buddy-bzImage /home/user/hyperalloc-linux/build-buddy-vm/arch/x86/boot/bzImage
COPY --chown=user:root bin/buddy-huge-bzImage /home/user/hyperalloc-linux/build-buddy-huge/arch/x86/boot/bzImage
COPY --chown=user:root bin/llfree-bzImage /home/user/hyperalloc-linux/build-llfree-vm/arch/x86/boot/bzImage

COPY --chown=user:root bin/buddy-alloc.ko /home/user/linux-alloc-bench/build-buddy-vm/alloc.ko
COPY --chown=user:root bin/buddy-huge-alloc.ko /home/user/linux-alloc-bench/build-buddy-huge/alloc.ko
COPY --chown=user:root bin/llfree-alloc.ko /home/user/linux-alloc-bench/build-llfree-vm/alloc.ko

COPY --chown=user:root bin/debian.qcow2 /home/user/hyperalloc-bench/resources/debian.qcow2

EXPOSE 22

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/init.sh"]
