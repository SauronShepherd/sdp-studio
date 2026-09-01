# Kubernetes runtime

Create a Kubernetes runtime profile with an explicit API/master endpoint,
namespace, image, and service account. Namespace and pod-prefix allowlists can
be supplied by the administrator through the profile configuration. Profiles
are validated before submission and commands are executed as argument arrays;
shell interpolation is not used.

The Kubernetes adapter exposes probe, driver status, bounded logs, events, and
cancel endpoints. It does not claim local row preview unless the configured
runtime supports it. Run the contract suite with:

```bash
python -m pytest -q tests/test_runtime_profiles.py tests/test_adapters.py
python scripts/qualify.py --kubernetes
```
