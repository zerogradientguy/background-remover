"""
Compatibility shims that must be imported before the offending packages.

basicsr (used by Real-ESRGAN + GFPGAN) imports
`torchvision.transforms.functional_tensor`, which was removed in torchvision>=0.17.
We recreate it as an alias so the old import keeps working without editing site-packages.
"""
from __future__ import annotations

import sys
import types


def install_torchvision_functional_tensor_shim() -> None:
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    import torchvision.transforms.functional as _tv_functional

    shim = types.ModuleType("torchvision.transforms.functional_tensor")
    shim.rgb_to_grayscale = _tv_functional.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = shim
