"""Optional Databricks adapter boundary.

This package deliberately contains no Databricks SDK import. Applications may
inject a compatible client, keeping the core installation vendor-neutral.
"""

from .adapter import DatabricksAdapter, DatabricksClient, DatabricksConfig, DatabricksRestClient

__all__ = ["DatabricksAdapter", "DatabricksConfig", "DatabricksClient", "DatabricksRestClient"]
