# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "1"
# ///
# MAGIC %md
# MAGIC # 📥 Ingesta de datos — Parquet → Tablas Delta (Unity Catalog)
# MAGIC
# MAGIC Este notebook crea las tablas Delta del workshop a partir de los **archivos Parquet que
# MAGIC vienen en el repo** (`data/parquet/`). Es el **primer paso** al clonar el repositorio: deja
# MAGIC listas las tablas en Unity Catalog para que todas las fases del lab tengan datos.
# MAGIC
# MAGIC | Parquet (repo) | → Tabla Delta | Filas |
# MAGIC |----------------|---------------|-------|
# MAGIC | `kb_documentos.parquet` | `kb_documentos` | 32 |
# MAGIC | `plantas.parquet` | `plantas` | 5 |
# MAGIC | `clientes_geo.parquet` | `clientes_geo` | 20 |
# MAGIC | `unidades.parquet` | `unidades` | 6 |
# MAGIC | `productos.parquet` | `productos` | 12 |
# MAGIC | `pedidos.parquet` | `pedidos` | 200 |
# MAGIC
# MAGIC > **Patrón didáctico:** archivos crudos → capa gobernada en Delta/Unity Catalog. Es la
# MAGIC > entrada del medallón. Desde aquí, `00_poblar_lakebase` sirve estos datos a Lakebase.

# COMMAND ----------

# MAGIC %run ./config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Localizar los archivos Parquet del repo
# MAGIC
# MAGIC Cuando el repo se clona en **Databricks Git Folders**, los archivos quedan junto al
# MAGIC notebook. Resolvemos la ruta absoluta al directorio `data/parquet/` del repo.

# COMMAND ----------

import os

# Ruta del notebook actual dentro del workspace → subimos a la raíz del repo → data/parquet
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_repo_root = os.path.dirname(os.path.dirname(_nb_path))          # .../notebooks/00_ingesta -> raíz repo
PARQUET_DIR = f"/Workspace{_repo_root}/data/parquet"

print(f"Notebook   : {_nb_path}")
print(f"Raíz repo  : {_repo_root}")
print(f"Parquet en : {PARQUET_DIR}")

# Verificación: listar los archivos encontrados
archivos = [f for f in os.listdir(PARQUET_DIR) if f.endswith(".parquet")]
print(f"\nArchivos Parquet encontrados ({len(archivos)}):")
for f in sorted(archivos):
    print(f"  · {f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Crear el catálogo/esquema destino
# MAGIC
# MAGIC Usa `UC_CATALOG` y `UC_SCHEMA` de `config`. Edita ahí para reapuntar a tu propio entorno.

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{UC_SCHEMA} "
          f"COMMENT 'Datos del Workshop Lakebase - Asistente de Operaciones INFRA'")
print(f"✔ Esquema listo: {UC_CATALOG}.{UC_SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Ingerir cada Parquet como tabla Delta
# MAGIC
# MAGIC Leemos cada Parquet con **pandas en el driver** y lo convertimos a DataFrame de Spark para
# MAGIC escribirlo como tabla Delta gestionada.
# MAGIC
# MAGIC > **¿Por qué pandas y no `spark.read.parquet`?** En cómputo **serverless**, los executors de
# MAGIC > Spark no pueden leer archivos del workspace/Git Folder (`file:/Workspace/...`). Leer con
# MAGIC > pandas en el driver sí funciona y, como estos datasets son pequeños (máx. 200 filas), es
# MAGIC > el enfoque más portable. `mode("overwrite")` lo hace idempotente: re-ejecuta sin duplicar.

# COMMAND ----------

import pandas as pd

TABLAS = ["kb_documentos", "plantas", "clientes_geo", "unidades", "productos", "pedidos"]

for tabla in TABLAS:
    # pandas lee del workspace (driver). Normalizamos los dtypes "nullable" de pandas
    # (StringDtype/Int64) a tipos que Spark infiere sin ambigüedad.
    pdf = pd.read_parquet(f"{PARQUET_DIR}/{tabla}.parquet")
    for col in pdf.columns:
        dt = pdf[col].dtype
        if isinstance(dt, pd.StringDtype):
            pdf[col] = pdf[col].astype(object)
        elif isinstance(dt, pd.Int64Dtype):
            pdf[col] = pdf[col].astype("int64")
    sdf = spark.createDataFrame(pdf)                          # → DataFrame de Spark
    destino = f"{UC_CATALOG}.{UC_SCHEMA}.{tabla}"
    sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(destino)
    print(f"✔ {destino:60s} ← {len(pdf):>3} filas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verificación

# COMMAND ----------

print("Resumen de tablas creadas:\n")
for tabla in TABLAS:
    n = spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.{tabla}").count()
    print(f"  {tabla:16s} {n:>4} filas")

# Muestra de contenido
print("\nEjemplo — catálogo de productos:")
display(spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.productos").select("nombre", "categoria", "precio_mxn"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Ingesta completa
# MAGIC
# MAGIC Las 6 tablas Delta están en Unity Catalog. Siguientes pasos:
# MAGIC 1. **`00_poblar_lakebase`** — sirve estos datos a Lakebase (embeddings + geometrías).
# MAGIC 2. **`01`–`04`** — las fases del workshop, que leen de estas tablas.
