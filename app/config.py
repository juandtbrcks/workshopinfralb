"""Configuración y autenticación dual-mode (local vs Databricks App)."""
import os
from functools import lru_cache
from databricks.sdk import WorkspaceClient

# Detecta si corre dentro de una Databricks App
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# Parámetros del proyecto Lakebase (overridables por env)
PROJECT_ID = os.environ.get("LAKEBASE_PROJECT", "grupo-infra-ws")
BRANCH     = os.environ.get("LAKEBASE_BRANCH", "production")
ENDPOINT   = os.environ.get("LAKEBASE_ENDPOINT", "primary")
DATABASE   = os.environ.get("LAKEBASE_DB", "infra_ws")

EMBED_ENDPOINT = os.environ.get("EMBED_ENDPOINT", "databricks-qwen3-embedding-0-6b")
CHAT_ENDPOINT  = os.environ.get("CHAT_ENDPOINT", "databricks-claude-opus-4-8")


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP:
        # Remoto: usa el service principal auto-inyectado
        return WorkspaceClient()
    # Local: usa el perfil de la CLI
    profile = os.environ.get("DATABRICKS_PROFILE", "fe-vm-jgworkspaceclassic")
    return WorkspaceClient(profile=profile)
