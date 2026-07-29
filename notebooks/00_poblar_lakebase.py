# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 🌱 Bootstrap de datos — de Unity Catalog a Lakebase
# MAGIC
# MAGIC Este notebook siembra Lakebase con los **datos sintéticos de Grupo Infra** que viven en
# MAGIC Unity Catalog (`jgworkspaceclassic_catalog.infra_lakebase_ws`). Deja el entorno listo para:
# MAGIC - el **workshop** (los participantes ya encuentran datos con sentido de negocio), y
# MAGIC - la **Databricks App** "Asistente de Operaciones INFRA".
# MAGIC
# MAGIC | Tabla UC | → Tabla Lakebase | Transformación |
# MAGIC |----------|------------------|----------------|
# MAGIC | `kb_documentos` | `knowledge_base` | genera embeddings (`pgvector`) |
# MAGIC | `plantas` | `plantas` | lat/lon → `geography` (PostGIS) |
# MAGIC | `clientes_geo` | `clientes_geo` | lat/lon → `geography` |
# MAGIC | `unidades` | `unidades` | lat/lon → `geography` |
# MAGIC | `productos` | `productos` | copia directa |
# MAGIC | `pedidos` | `pedidos` | copia directa |
# MAGIC
# MAGIC > **Patrón didáctico:** en producción esto sería un job de "reverse ETL" (Delta → Lakebase),
# MAGIC > o tablas *synced* de Unity Catalog. Aquí lo hacemos explícito para que se vea el flujo.

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary pgvector databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# UC_CATALOG, UC_SCHEMA, EMBED_ENDPOINT y EMBED_DIM vienen de `config`
# (vía %run ./00_setup_conexion)

def uc(table):
    return spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.{table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Knowledge base + embeddings (Fase 2)

# COMMAND ----------

# MAGIC %md
# MAGIC Generamos los embeddings usando el modelo establecido en archivo config

# COMMAND ----------

from pgvector.psycopg2 import register_vector

def embed(texts):
    if isinstance(texts, str):
        texts = [texts]
    resp = _w.serving_endpoints.query(name=EMBED_ENDPOINT, input=texts)
    return [d["embedding"] if isinstance(d, dict) else d.embedding for d in resp.data]

docs = uc("kb_documentos").select("doc_id", "categoria", "titulo", "contenido").collect()

conn = get_connection()
register_vector(conn)
cur = conn.cursor()

cur.execute(f"""
CREATE TABLE IF NOT EXISTS knowledge_base (
    doc_id     TEXT PRIMARY KEY,
    categoria  TEXT,
    titulo     TEXT,
    contenido  TEXT NOT NULL,
    embedding  vector({EMBED_DIM})
);
CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON knowledge_base USING hnsw (embedding vector_cosine_ops);
""")

# indexamos como "categoria: contenido" (mejora relevancia)
textos = [f"{d['categoria']}: {d['contenido']}" for d in docs]
vectores = embed(textos)

for d, vec in zip(docs, vectores):
    cur.execute(
        """INSERT INTO knowledge_base (doc_id, categoria, titulo, contenido, embedding)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (doc_id) DO UPDATE SET
             categoria=EXCLUDED.categoria, titulo=EXCLUDED.titulo,
             contenido=EXCLUDED.contenido, embedding=EXCLUDED.embedding""",
        (d["doc_id"], d["categoria"], d["titulo"], d["contenido"], vec),
    )
cur.execute("SELECT count(*) FROM knowledge_base;")
print(f"✔ knowledge_base: {cur.fetchone()[0]} documentos con embeddings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Datos geoespaciales (Fase 3)

# COMMAND ----------

cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
cur.execute("""
CREATE TABLE IF NOT EXISTS plantas (
    planta_id TEXT PRIMARY KEY, nombre TEXT,
    capacidad_cilindros_dia INT, ubicacion geography(Point,4326));
CREATE TABLE IF NOT EXISTS clientes_geo (
    cliente_id TEXT PRIMARY KEY, nombre TEXT, tipo TEXT, segmento TEXT,
    tiene_credito BOOLEAN, ubicacion geography(Point,4326));
CREATE TABLE IF NOT EXISTS unidades (
    unidad_id TEXT PRIMARY KEY, placa TEXT, tipo_unidad TEXT,
    capacidad_cilindros INT, ubicacion geography(Point,4326));
CREATE INDEX IF NOT EXISTS idx_clientes_geo ON clientes_geo USING gist (ubicacion);
CREATE INDEX IF NOT EXISTS idx_plantas_geo  ON plantas      USING gist (ubicacion);
""")

for r in uc("plantas").collect():
    cur.execute("""INSERT INTO plantas (planta_id,nombre,capacidad_cilindros_dia,ubicacion)
        VALUES (%s,%s,%s, ST_MakePoint(%s,%s)::geography)
        ON CONFLICT (planta_id) DO UPDATE SET nombre=EXCLUDED.nombre,
          capacidad_cilindros_dia=EXCLUDED.capacidad_cilindros_dia, ubicacion=EXCLUDED.ubicacion""",
        (r["planta_id"], r["nombre"], r["capacidad_cilindros_dia"], r["lon"], r["lat"]))

for r in uc("clientes_geo").collect():
    cur.execute("""INSERT INTO clientes_geo (cliente_id,nombre,tipo,segmento,tiene_credito,ubicacion)
        VALUES (%s,%s,%s,%s,%s, ST_MakePoint(%s,%s)::geography)
        ON CONFLICT (cliente_id) DO UPDATE SET nombre=EXCLUDED.nombre, tipo=EXCLUDED.tipo,
          segmento=EXCLUDED.segmento, tiene_credito=EXCLUDED.tiene_credito, ubicacion=EXCLUDED.ubicacion""",
        (r["cliente_id"], r["nombre"], r["tipo"], r["segmento"], r["tiene_credito"], r["lon"], r["lat"]))

for r in uc("unidades").collect():
    cur.execute("""INSERT INTO unidades (unidad_id,placa,tipo_unidad,capacidad_cilindros,ubicacion)
        VALUES (%s,%s,%s,%s, ST_MakePoint(%s,%s)::geography)
        ON CONFLICT (unidad_id) DO UPDATE SET placa=EXCLUDED.placa, tipo_unidad=EXCLUDED.tipo_unidad,
          capacidad_cilindros=EXCLUDED.capacidad_cilindros, ubicacion=EXCLUDED.ubicacion""",
        (r["unidad_id"], r["placa"], r["tipo_unidad"], r["capacidad_cilindros"], r["lon"], r["lat"]))

for t in ("plantas", "clientes_geo", "unidades"):
    cur.execute(f"SELECT count(*) FROM {t};")
    print(f"✔ {t}: {cur.fetchone()[0]} filas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Productos y pedidos (contexto operacional de la app)

# COMMAND ----------

cur.execute("""
CREATE TABLE IF NOT EXISTS productos (
    producto_id TEXT PRIMARY KEY, nombre TEXT, categoria TEXT, presentacion TEXT,
    unidad_medida TEXT, precio_mxn NUMERIC(10,2), es_comburente BOOLEAN, es_inflamable BOOLEAN);
CREATE TABLE IF NOT EXISTS pedidos (
    pedido_id TEXT PRIMARY KEY, cliente_id TEXT, producto_id TEXT, producto_nombre TEXT,
    cantidad INT, precio_mxn NUMERIC(10,2), subtotal NUMERIC(12,2), total_con_iva NUMERIC(12,2),
    fecha_pedido DATE, estado TEXT, unidad_id TEXT);
""")

for r in uc("productos").collect():
    cur.execute("""INSERT INTO productos VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (producto_id) DO UPDATE SET precio_mxn=EXCLUDED.precio_mxn""",
        (r["producto_id"], r["nombre"], r["categoria"], r["presentacion"],
         r["unidad_medida"], float(r["precio_mxn"]), r["es_comburente"], r["es_inflamable"]))

for r in uc("pedidos").collect():
    cur.execute("""INSERT INTO pedidos VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (pedido_id) DO NOTHING""",
        (r["pedido_id"], r["cliente_id"], r["producto_id"], r["producto_nombre"], r["cantidad"],
         float(r["precio_mxn"]), float(r["subtotal"]), float(r["total_con_iva"]),
         r["fecha_pedido"], r["estado"], r["unidad_id"]))

for t in ("productos", "pedidos"):
    cur.execute(f"SELECT count(*) FROM {t};")
    print(f"✔ {t}: {cur.fetchone()[0]} filas")

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Lakebase sembrado
# MAGIC
# MAGIC La base `infra_ws` ya tiene knowledge base (con embeddings), geo (con PostGIS), productos y
# MAGIC pedidos. Ya puedes correr las fases del workshop con datos reales, y la **App** tiene backend.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 🔍 Validación: verifica tus datos en Lakebase
# MAGIC
# MAGIC Antes de continuar con las fases, confirma que todo quedó bien.

# COMMAND ----------

# DBTITLE 1,Resumen de tablas y conteos en Lakebase
# Validación rápida: conteo de filas por tabla en tu BD de Lakebase
conn_val = get_connection()
cur_val = conn_val.cursor()

tablas_esperadas = {
    "knowledge_base": "doc_id",
    "plantas": "planta_id",
    "clientes_geo": "cliente_id",
    "unidades": "unidad_id",
    "productos": "producto_id",
    "pedidos": "pedido_id",
}

print(f"📊 Validación de datos en Lakebase (BD: {DATABASE})")
print(f"{'='*50}")
todo_ok = True
for tabla, pk in tablas_esperadas.items():
    try:
        cur_val.execute(f"SELECT count(*) FROM {tabla};")
        count = cur_val.fetchone()[0]
        status = "✅" if count > 0 else "⚠️ VACIA"
        if count == 0:
            todo_ok = False
        print(f"  {status} {tabla:20s} {count:>5} filas")
    except Exception as e:
        print(f"  ❌ {tabla:20s} ERROR: {e}")
        todo_ok = False
        conn_val.rollback()

print(f"{'='*50}")
if todo_ok:
    print("✅ Todas las tablas tienen datos. ¡Listo para las fases!")
else:
    print("⚠️  Algunas tablas están vacías o no existen. Revisa las celdas anteriores.")

cur_val.close()
conn_val.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ### 🧭 Explora tus datos desde la UI de Databricks
# MAGIC
# MAGIC Para ver y navegar los datos directamente en la interfaz:
# MAGIC
# MAGIC 1. **Abre tu instancia de Lakebase:**
# MAGIC    - Barra lateral → **Compute** → **Database instances**
# MAGIC    - Click en **`grupo-infra-ws`**
# MAGIC
# MAGIC 2. **Navega a tu base de datos:**
# MAGIC    - En el panel izquierdo verás las bases. Selecciona **`infra_ws_<tu-participante>`**
# MAGIC    - Expande **Tables** — deberías ver: `knowledge_base`, `plantas`, `clientes_geo`, `unidades`, `productos`, `pedidos`
# MAGIC
# MAGIC 3. **Explora los datos:**
# MAGIC    - Click en cualquier tabla para ver su **schema** (columnas y tipos)
# MAGIC    - Usa la pestaña **Data** para ver filas de ejemplo
# MAGIC    - Nota las columnas especiales:
# MAGIC      - `embedding` (vector de 1024 dims) en `knowledge_base`
# MAGIC      - `ubicacion` (geography/Point) en `plantas`, `clientes_geo`, `unidades`
# MAGIC
# MAGIC 4. **Prueba una consulta rápida** desde el **Query Editor** de Lakebase:
# MAGIC    ```sql
# MAGIC    -- ¿Qué clientes tiene tu base?
# MAGIC    SELECT nombre, tipo, segmento FROM clientes_geo ORDER BY nombre;
# MAGIC    
# MAGIC    -- ¿Cuántos pedidos por estado?
# MAGIC    SELECT estado, count(*) FROM pedidos GROUP BY estado;
# MAGIC    ```
# MAGIC
# MAGIC > 💡 **Tip:** desde la UI también puedes ver el **tamaño del índice HNSW** de pgvector
# MAGIC > y el **índice GiST** de PostGIS en la pestaña *Indexes* de cada tabla.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC
# MAGIC ✅ **Si todo está verde arriba, continúa con `01_fase1_agentic_state`.**
