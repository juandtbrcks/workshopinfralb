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
#  👤 CADA PARTICIPANTE EDITA SOLO ESTA LÍNEA
# ═══════════════════════════════════════════════════════════════════
# Pon tus iniciales o nombre corto (solo minúsculas/números, sin espacios).
# Con esto tu base de datos y tu branch quedan aislados de los demás.
PARTICIPANTE = "jgordon"     # ← CÁMBIALO, p.ej. "amlopez", "equipo1", etc.

# ─────────────────────────── Lakebase ───────────────────────────
# El PROYECTO es COMPARTIDO por todo el taller (lo crea el instructor una vez).
# La BASE DE DATOS es propia de cada participante (deriva de PARTICIPANTE).
LAKEBASE_PROJECT  = "grupo-infra-ws"          # compartido — no cambiar
LAKEBASE_BRANCH   = "production"              # compartido — no cambiar
LAKEBASE_ENDPOINT = "primary"                 # compartido — no cambiar
LAKEBASE_DATABASE = f"infra_ws_{PARTICIPANTE}"  # propia de cada quien

# ──────────────────── Unity Catalog (datos sintéticos) ────────────────────
# COMPARTIDO por todo el taller: las tablas Delta son de SOLO LECTURA (los notebooks
# leen de aquí y escriben a Lakebase). El instructor corre la ingesta una sola vez.
UC_CATALOG = "jgworkspaceclassic_catalog"     # compartido — ajusta al catálogo del taller
UC_SCHEMA  = "infra_lakebase_ws"              # compartido

# ─────────────────────── Foundation Models ───────────────────────
# Compartidos (son endpoints del workspace). Embeddings multilingüe + LLM para RAG.
EMBED_ENDPOINT = "databricks-qwen3-embedding-0-6b"
EMBED_DIM      = 1024
CHAT_ENDPOINT  = "databricks-claude-opus-4-8"

# ─────────────────────────── Fase 4 ───────────────────────────
# Branch efímero para el experimento de branching — único por participante
# (el proyecto es compartido, así que dos branches no pueden llamarse igual).
BRANCH_EXPERIMENTO = f"experimento-{PARTICIPANTE}"

# COMMAND ----------

print("⚙️  Configuración cargada:")
print(f"  Participante : {PARTICIPANTE}")
print(f"  Lakebase     : projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}  ·  db={LAKEBASE_DATABASE}")
print(f"  UC           : {UC_CATALOG}.{UC_SCHEMA}")
print(f"  Modelos      : embed={EMBED_ENDPOINT} (dim {EMBED_DIM})  ·  chat={CHAT_ENDPOINT}")
print(f"  Fase 4       : branch experimento = {BRANCH_EXPERIMENTO}")

assert PARTICIPANTE and PARTICIPANTE.replace("_", "").isalnum(), \
    "PARTICIPANTE debe ser solo letras/números (sin espacios ni acentos)."
