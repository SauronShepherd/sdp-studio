import os

import pytest
from sdpstudio_adapters_databricks import DatabricksConfig, DatabricksRestClient


@pytest.mark.databricks_live
def test_databricks_live_probe_when_credentials_are_configured():
    workspace = os.environ.get("SDPSTUDIO_DATABRICKS_WORKSPACE_URL")
    token = os.environ.get("SDPSTUDIO_DATABRICKS_TOKEN")
    if not workspace or not token:
        pytest.skip("Databricks live qualification credentials are not configured")
    result = DatabricksRestClient(DatabricksConfig(workspace), token=token).probe()
    assert result["available"] is True
    assert result["sdp"] is True
