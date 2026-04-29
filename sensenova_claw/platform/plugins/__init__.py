"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry

__all__ = [
    "ManifestValidationError",
    "PluginManifest",
    "PluginPermissions",
    "RegistryEntry",
    "load_manifest_from_yaml",
]
