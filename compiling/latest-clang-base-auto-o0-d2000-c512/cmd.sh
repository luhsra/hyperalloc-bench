/opt/ballooning/virtio-qemu-system -smp 12 -hda /opt/ballooning/debian.img -serial mon:stdio -nographic -kernel /opt/ballooning/buddy-bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5222-:22 -no-reboot --cpu host -m 16G -device '{"driver": "virtio-balloon", "free-page-reporting": true}' -append 'root=/dev/sda3 console=ttyS0 nokaslr page_reporting.page_reporting_delay=2000 page_reporting.page_reporting_capacity=512 page_reporting.page_reporting_order=0' -enable-kvm