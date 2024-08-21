from qemu.qmp import QMPClient


HUGEPAGE_SIZE = 2**21
"""Size of a huge page in bytes"""

class VMResize:
    def __init__(self, qmp: QMPClient, mode: str, max: int, min: int) -> None:
        """min and max are the VM memory limits in bytes"""
        self.qmp = qmp
        self.mode = mode
        self.min = round(min)
        self.max = round(max)
        self.size = min

    async def set(self, target_size: int | float):
        """Resize the VM to the target_size (bytes)"""
        if target_size >= self.max and self.size == self.max: return
        if target_size <= self.min and self.size == self.min: return

        new_size = round(target_size)
        # align up to hugepage size
        new_size = (((new_size - self.min) + HUGEPAGE_SIZE - 1) // HUGEPAGE_SIZE) * HUGEPAGE_SIZE
        new_size = max(self.min, min(self.max, round(new_size)))

        if new_size != self.size: return

        self.size = new_size
        print("resize", self.size)

        match self.mode:
            case "base-manual" | "huge-manual":
                await self.qmp.execute("balloon", {"value" : self.size})
            case "llfree-manual" | "llfree-manual-map":
                await self.qmp.execute("llfree-balloon", {"value" : self.size})
            case "virtio-mem-kernel" | "virtio-mem-movable":
                await self.qmp.execute("qom-set", {
                    "path": "vm0",
                    "property": "requested-size",
                    "value" : self.size
                })
            case _: assert False, "Invalid Mode"

    async def query(self) -> int:
        match self.mode:
            case "base-manual" | "huge-manual":
                res = await self.qmp.execute("query-balloon")
                return res["actual"]
            case "llfree-manual" | "llfree-manual-map":
                res = await self.qmp.execute("query-llfree-balloon")
                return res["actual"]
            case "virtio-mem-kernel" | "virtio-mem-movable":
                res = await self.qmp.execute("qom-get", {"path": "vm0", "property": "size"})
                return self.min + res
            case _: assert False, "Invalid Mode"
