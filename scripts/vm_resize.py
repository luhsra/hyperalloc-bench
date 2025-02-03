import math
from qemu.qmp import QMPClient
from .utils import fmt_bytes


HUGEPAGE_SIZE = 2**21
"""Size of a huge page in bytes"""

class VMResize:
    def __init__(self, qmp: QMPClient, mode: str, max: int, min: int, init: int, auto_fraction: int | None = None) -> None:
        """min and max are the VM memory limits in bytes"""
        self.qmp = qmp
        self.mode = mode
        self.min = round(min)
        self.max = round(max)
        self.size = init if init is not None else min
        self.auto_fraction = auto_fraction

    async def set(self, target_size: int | float):
        """Resize the VM to the target_size (bytes)"""
        new_size = round(target_size)

        # align up to hugepage size
        new_size = ((new_size + HUGEPAGE_SIZE - 1) // HUGEPAGE_SIZE) * HUGEPAGE_SIZE
        new_size = max(self.min, min(self.max, new_size))

        if new_size == self.size: return

        self.size = new_size
        print("resize", fmt_bytes(self.size))

        match self.mode:
            case "base-manual" | "huge-manual":
                await self.qmp.execute("balloon", {"value": self.size})
            case "llfree-manual" | "llfree-manual-map":
                await self.qmp.execute("llfree-balloon", {"value" : self.size})
            case "virtio-mem":
                await self.qmp.execute("qom-set", {
                    "path": "vm0",
                    "property": "requested-size",
                    "value" : self.size - self.min
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
            case "virtio-mem":
                res = await self.qmp.execute("qom-get", {"path": "vm0", "property": "size"})
                return self.min + res
            case _: assert False, "Invalid Mode"

    async def auto_resize(self, small: float, huge: float):
        assert self.auto_fraction is not None
        if math.isnan(small) or math.isnan(huge):
            return
        # Follow free huge pages
        free = int(huge * 2 ** (12 + 9) * 0.9)  # 10% above huge pages
        # free = small * 2**12 * 0.9 # 10% above small pages
        # Step size, amount of mem that is plugged/unplugged
        step = round(self.max * self.auto_fraction)
        if free < step / 2:  # grow faster
            await self.set(self.size + 2 * step)
        elif free < step:
            await self.set(self.size + step)
        elif free > 2 * step:
            await self.set(self.size - step)
