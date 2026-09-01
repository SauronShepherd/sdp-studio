"""Shared plugin manifest and compatibility checks."""

from __future__ import annotations

import re
import warnings
from typing import Any

SDK_VERSION = "0.1.0"


def validate_plugin_manifest(plugin: dict[str, Any], *, identifier: str) -> bool:
    """Validate the required, provider-neutral plugin metadata contract."""
    api_version = plugin.get("api_version")
    plugin_version = plugin.get("plugin_version")
    capabilities = plugin.get("capabilities")
    license_name = plugin.get("license")
    minimum = plugin.get("min_sdpstudio_version", "0.0.0")
    if not isinstance(api_version, str) or not api_version:
        warnings.warn(
            f"Ignoring plugin {identifier}: missing api_version", RuntimeWarning, stacklevel=2
        )
        return False
    if not isinstance(license_name, str) or not license_name:
        warnings.warn(
            f"Ignoring plugin {identifier}: missing license", RuntimeWarning, stacklevel=2
        )
        return False
    if not isinstance(plugin_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", plugin_version):
        warnings.warn(
            f"Ignoring plugin {identifier}: invalid plugin_version",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
    if not isinstance(capabilities, list) or not all(
        isinstance(capability, str) and capability.strip() for capability in capabilities
    ):
        warnings.warn(
            f"Ignoring plugin {identifier}: capabilities must be a list of names",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
    if not isinstance(minimum, str) or not re.fullmatch(r"\d+\.\d+\.\d+", minimum):
        warnings.warn(
            f"Ignoring plugin {identifier}: invalid min_sdpstudio_version",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
    if api_version != "v1" or tuple(map(int, minimum.split("."))) > tuple(
        map(int, SDK_VERSION.split("."))
    ):
        warnings.warn(f"Ignoring incompatible plugin {identifier}", RuntimeWarning, stacklevel=2)
        return False
    return True
