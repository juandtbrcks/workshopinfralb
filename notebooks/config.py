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

# ═══════════════════════════════════════════════════════════════════
#  👤 EDITA SOLO ESTA LÍNEA
# ═══════════════════════════════════════════════════════════════════
# Pon tus iniciales o nombre corto (solo minúsculas/números, sin espacios).
# Cada participante crea y usa SU PROPIA infraestructura, totalmente independiente:
# de este valor se derivan tu proyecto Lakebase, tu esquema y tu branch.
PARTICIPANTE = "jgordon"     # ← CÁMBIALO, p.ej. "amlopez", "equipo1", etc.

# ─────────────────────────── Lakebase ───────────────────────────
# Tu propio proyecto Lakebase (lo creas tú en el Paso de setup). El nombre debe ser
# DNS-compliant: minúsculas, números y guiones.
LAKEBASE_PROJECT  = f"infra-ws-{PARTICIPANTE}"
LAKEBASE_BRANCH   = "production"      # branch raíz que se crea con el proyecto
LAKEBASE_ENDPOINT = "primary"         # endpoint que se crea con el proyecto
LAKEBASE_DATABASE = "infra_ws"        # base dentro de TU proyecto

# ──────────────────── Unity Catalog (datos sintéticos) ────────────────────
# Catálogo COMPARTIDO (ya existe en el workspace); cada quien su propio ESQUEMA.
UC_CATALOG = "jgworkspaceclassic_catalog"         # ajusta al catálogo del workspace
UC_SCHEMA  = f"infra_lakebase_ws_{PARTICIPANTE}"  # tu propio esquema

# ─────────────────────── Foundation Models ───────────────────────
# Endpoints del workspace (compartidos). Embeddings multilingüe + LLM para RAG.
EMBED_ENDPOINT = "databricks-qwen3-embedding-0-6b"
EMBED_DIM      = 1024
CHAT_ENDPOINT  = "databricks-claude-opus-4-8"

# ─────────────────────────── Fase 4 ───────────────────────────
# Branch efímero para el experimento de branching (dentro de tu propio proyecto).
BRANCH_EXPERIMENTO = "experimento-precios"

# COMMAND ----------

print("⚙️  Configuración cargada:")
print(f"  Participante : {PARTICIPANTE}")
print(f"  Lakebase     : projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}  ·  db={LAKEBASE_DATABASE}")
print(f"  UC           : {UC_CATALOG}.{UC_SCHEMA}")
print(f"  Modelos      : embed={EMBED_ENDPOINT} (dim {EMBED_DIM})  ·  chat={CHAT_ENDPOINT}")
print(f"  Fase 4       : branch experimento = {BRANCH_EXPERIMENTO}")

import re as _re
assert _re.fullmatch(r"[a-z0-9]+", PARTICIPANTE), \
    ("PARTICIPANTE debe ser solo minúsculas ASCII y números, sin espacios, guiones ni acentos "
     "(el nombre del proyecto Lakebase debe ser DNS-compliant). Ej.: 'jgordon', 'equipo1'.")
