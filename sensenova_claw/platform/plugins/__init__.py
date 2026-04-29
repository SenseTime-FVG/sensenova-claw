"""sensenova_claw plugin 基础设施（P1：Loader + Registry 抽象）。"""
from sensenova_claw.platform.plugins.loader import (
    InstallFailure,
    InstallReport,
    PluginLoader,
)
from sensenova_claw.platform.plugins.manifest import (
    ManifestValidationError,
    PluginManifest,
    PluginPermissions,
    load_manifest_from_yaml,
)
from sensenova_claw.platform.plugins.registry_entry import RegistryEntry
from sensenova_claw.platform.plugins.sources import (
    BuiltinPluginSource,
    PluginSource,
    SourceError,
    UserPluginSource,
)

__all__ = [
    "BuiltinPluginSource",
    "InstallFailure",
    "InstallReport",
    "ManifestValidationError",
    "PluginLoader",
    "PluginManifest",
    "PluginPermissions",
    "PluginSource",
    "RegistryEntry",
    "SourceError",
    "UserPluginSource",
    "load_manifest_from_yaml",
]
