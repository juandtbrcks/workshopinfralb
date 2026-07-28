# Databricks notebook source
# MAGIC %md
# MAGIC # ⚙️ Configuración central del Workshop
# MAGIC
# MAGIC **Único lugar** donde se definen los parámetros del lab. Todos los demás notebooks lo
# MAGIC cargan con `%run ./config` (directamente o a través de `00_setup_conexion`), así no hay
# MAGIC variables hardcodeadas repartidas.
# MAGIC
# MAGIC Para reapuntar el workshop a otro proyecto, catálogo o modelos, **edita solo este archivo**.

# COMMAND ----------

# ─────────────────────────── Lakebase ───────────────────────────
# Proyecto Lakebase (autoscaling), branch, endpoint y base de datos.
LAKEBASE_PROJECT  = "grupo-infra-ws"
LAKEBASE_BRANCH   = "production"
LAKEBASE_ENDPOINT = "primary"
LAKEBASE_DATABASE = "infra_ws"

# ──────────────────── Unity Catalog (datos sintéticos) ────────────────────
# Esquema donde viven las tablas Delta que alimentan el lab y la app.
UC_CATALOG = "jgworkspaceclassic_catalog"
UC_SCHEMA  = "infra_lakebase_ws"

# ─────────────────────── Foundation Models ───────────────────────
# Embeddings multilingüe (español) + LLM para RAG.
EMBED_ENDPOINT = "databricks-qwen3-embedding-0-6b"
EMBED_DIM      = 1024
CHAT_ENDPOINT  = "databricks-claude-opus-4-8"

# ─────────────────────────── Fase 4 ───────────────────────────
# Nombre del branch efímero para el experimento de branching.
# Si varios participantes corren la fase a la vez, dale un sufijo único
# (p.ej. f"experimento-{tus_iniciales}") para evitar colisiones.
BRANCH_EXPERIMENTO = "experimento-precios"

# COMMAND ----------

print("⚙️  Configuración cargada:")
print(f"  Lakebase : projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}/endpoints/{LAKEBASE_ENDPOINT}  ·  db={LAKEBASE_DATABASE}")
print(f"  UC       : {UC_CATALOG}.{UC_SCHEMA}")
print(f"  Modelos  : embed={EMBED_ENDPOINT} (dim {EMBED_DIM})  ·  chat={CHAT_ENDPOINT}")
print(f"  Fase 4   : branch experimento = {BRANCH_EXPERIMENTO}")
