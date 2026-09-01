# Plugin development

Plugins are discovered through the declared entry-point groups. Operators provide deterministic metadata, validation, and code-generation support; runtime adapters provide probe and execution behavior. Every manifest must declare `api_version: "v1"`, a semantic `plugin_version` (`MAJOR.MINOR.PATCH`), a non-empty `capabilities` list, a license, and (when needed) `min_sdpstudio_version`. Manifests with an incompatible API or minimum version are isolated and never loaded.

The machine-readable SDK reference is [plugin-sdk.json](../reference/plugin-sdk.json). Regenerate it after changing the plugin groups or manifest contract with `python scripts/plugin_reference.py`; release checks should verify the generated file is committed and deterministic.

Core code generation must remain network-free. Provider-specific behavior belongs in an adapter or plugin, never in `sdpstudio_core`. Add contract tests for every operator's validation and generated source before publishing a plugin.
