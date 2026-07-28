# Databricks notebook source
# MAGIC %md
# MAGIC # 🔎 Fase 2 — Búsquedas Vectoriales (pgvector)
# MAGIC
# MAGIC **El problema:** el Asistente de Operaciones INFRA debe responder preguntas técnicas y de
# MAGIC seguridad ("¿cómo almaceno acetileno?", "¿qué hago ante una fuga de oxígeno?"). Esa
# MAGIC información vive en manuales, hojas de seguridad (HDS) y tickets históricos. La búsqueda por
# MAGIC palabra clave falla cuando el usuario no usa las palabras exactas del manual.
# MAGIC
# MAGIC **La solución:** **búsqueda semántica**. Convertimos el conocimiento a *embeddings*
# MAGIC (vectores) y los guardamos en Lakebase con la extensión `pgvector`. Buscamos por *significado*,
# MAGIC no por texto exacto.
# MAGIC
# MAGIC **Por qué en Lakebase y no en un vector-store aparte:** el agente ya usa Lakebase para su
# MAGIC estado (Fase 1). Tener los vectores **en la misma base** significa: una sola conexión,
# MAGIC transacciones que combinan datos operacionales + semánticos, y cero sistemas extra que operar.
# MAGIC Esto es el patrón **"Lakebase como backend unificado del agente"**.

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary pgvector databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Base de conocimiento: leemos la tabla Delta de Unity Catalog
# MAGIC
# MAGIC La documentación de Grupo Infra (HDS de gases, procedimientos logísticos, tickets y
# MAGIC normatividad) vive gobernada en Delta:
# MAGIC `{UC_CATALOG}.{UC_SCHEMA}.kb_documentos`. En producción esa tabla la alimentaría un
# MAGIC pipeline que trocea PDFs; aquí ya está poblada con datos sintéticos.
# MAGIC
# MAGIC > **Este es el patrón real:** el conocimiento se cura y gobierna en el lago (Delta + Unity
# MAGIC > Catalog) y se *sirve* con baja latencia desde Lakebase para el agente. Leemos de Delta y
# MAGIC > generamos embeddings hacia Lakebase.
# MAGIC >
# MAGIC > **Prerrequisito:** la tabla Delta `kb_documentos` debe existir. Se crea con
# MAGIC > `data/01_kb_documentos.sql` (ver README). Si no existe, esta celda fallará con
# MAGIC > *"table not found"*.

# COMMAND ----------

# Leemos la base de conocimiento desde Delta (UC_CATALOG/UC_SCHEMA vienen de `config`)
kb_rows = (
    spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.kb_documentos")
         .select("doc_id", "categoria", "titulo", "contenido")
         .collect()
)
KNOWLEDGE = [(r["doc_id"], r["categoria"], r["titulo"], r["contenido"]) for r in kb_rows]
print(f"{len(KNOWLEDGE)} fragmentos de conocimiento leídos de {UC_CATALOG}.{UC_SCHEMA}.kb_documentos")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Generar embeddings con Foundation Models de Databricks
# MAGIC
# MAGIC Usamos el endpoint `databricks-qwen3-embedding-0-6b` (1024 dimensiones), servido
# MAGIC nativamente en el workspace. No necesitamos claves externas.
# MAGIC
# MAGIC > **¿Por qué este modelo?** Es **multilingüe**, así que entiende bien el español de
# MAGIC > nuestros manuales y preguntas. Los modelos solo-inglés (como `bge-large-en` o
# MAGIC > `gte-large-en`, también disponibles) dan relevancia notablemente peor sobre texto en
# MAGIC > español. Elegir el modelo de embeddings correcto para tu idioma es una decisión de diseño
# MAGIC > importante en RAG.
# MAGIC >
# MAGIC > **Técnica adicional:** indexamos cada documento como `"categoría: contenido"` para darle
# MAGIC > un poco más de contexto al embedding.

# COMMAND ----------

# _w, EMBED_ENDPOINT y EMBED_DIM vienen de `config` (vía %run ./00_setup_conexion)

def embed(texts):
    """Devuelve una lista de vectores para una lista de textos."""
    if isinstance(texts, str):
        texts = [texts]
    resp = _w.serving_endpoints.query(name=EMBED_ENDPOINT, input=texts)
    return [d["embedding"] if isinstance(d, dict) else d.embedding for d in resp.data]

# Prueba rápida
_v = embed("prueba de oxígeno")[0]
print(f"✔ Embeddings OK — dimensión: {len(_v)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Tabla vectorial en Lakebase
# MAGIC
# MAGIC La columna `embedding vector(1024)` es lo que habilita `pgvector`. El índice **HNSW** con
# MAGIC distancia coseno acelera la búsqueda por similitud a escala.

# COMMAND ----------

conn = get_connection()
cur = conn.cursor()

cur.execute(f"""
CREATE TABLE IF NOT EXISTS knowledge_base (
    doc_id     TEXT PRIMARY KEY,
    categoria  TEXT,
    titulo     TEXT,
    contenido  TEXT NOT NULL,
    embedding  vector({EMBED_DIM})
);
""")

# Índice HNSW para búsqueda aproximada por coseno (vector_cosine_ops)
cur.execute("""
CREATE INDEX IF NOT EXISTS idx_kb_embedding
ON knowledge_base USING hnsw (embedding vector_cosine_ops);
""")
print("✔ Tabla knowledge_base + índice HNSW creados")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Indexar el conocimiento (generar + guardar embeddings)

# COMMAND ----------

from pgvector.psycopg2 import register_vector
register_vector(conn)

# Indexamos cada documento como "categoría: contenido" (técnica 1)
textos = [f"{cat}: {contenido}" for (_id, cat, _tit, contenido) in KNOWLEDGE]
vectores = embed(textos)

for (doc_id, categoria, titulo, contenido), vec in zip(KNOWLEDGE, vectores):
    cur.execute(
        """INSERT INTO knowledge_base (doc_id, categoria, titulo, contenido, embedding)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (doc_id) DO UPDATE SET
             categoria = EXCLUDED.categoria,
             titulo    = EXCLUDED.titulo,
             contenido = EXCLUDED.contenido,
             embedding = EXCLUDED.embedding""",
        (doc_id, categoria, titulo, contenido, vec),
    )

cur.execute("SELECT count(*) FROM knowledge_base;")
print(f"✔ {cur.fetchone()[0]} documentos indexados con embeddings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Búsqueda semántica
# MAGIC
# MAGIC El operador `<=>` de pgvector calcula **distancia coseno** (menor = más similar).
# MAGIC Nótese: la pregunta NO usa las palabras del manual, pero encuentra lo relevante.

# COMMAND ----------

def buscar(pregunta, k=3, categoria=None):
    qvec = embed(pregunta)[0]
    if categoria:
        cur.execute(
            """SELECT doc_id, categoria, contenido, 1 - (embedding <=> %s::vector) AS similitud
               FROM knowledge_base WHERE categoria = %s
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (qvec, categoria, qvec, k),
        )
    else:
        cur.execute(
            """SELECT doc_id, categoria, contenido, 1 - (embedding <=> %s::vector) AS similitud
               FROM knowledge_base
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (qvec, qvec, k),
        )
    return cur.fetchall()

pregunta = "¿puede el gas causar quemaduras de frío?"
print(f"❓ {pregunta}\n")
for doc_id, cat, contenido, sim in buscar(pregunta):
    print(f"  [{sim:.3f}] {doc_id} ({cat})")
    print(f"          {contenido[:90]}...\n")

# COMMAND ----------

# MAGIC %md
# MAGIC > Observa que la pregunta habla de "quemaduras de frío" y el sistema recuperó la ficha del
# MAGIC > **CO2** (que causa quemaduras *criogénicas*) — sin que la pregunta use la palabra "CO2"
# MAGIC > ni "criogénico". Eso es búsqueda semántica: entiende el *significado*, no el texto exacto.

# COMMAND ----------

for q in [
    "¿es peligroso soldar con acetileno?",
    "riesgo de asfixia en un sótano",
    "un cliente reporta que la válvula no cierra bien",
    "cómo entregar cilindros a un cliente",
]:
    print(f"❓ {q}")
    top = buscar(q, k=1)[0]
    print(f"   → [{top[3]:.3f}] {top[0]} ({top[1]}): {top[2][:80]}...\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. RAG: combinar búsqueda + LLM para una respuesta natural
# MAGIC
# MAGIC Aquí cerramos el ciclo agéntico: recuperamos contexto de Lakebase y se lo damos a un LLM
# MAGIC (Claude) para redactar una respuesta segura y citada.

# COMMAND ----------

from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

# CHAT_ENDPOINT viene de `config`

def responder_con_rag(pregunta, k=3):
    contexto = buscar(pregunta, k=k)
    fragmentos = "\n".join(f"[{d[0]}] {d[2]}" for d in contexto)
    prompt = f"""Eres el Asistente de Operaciones de Grupo Infra (gases industriales y medicinales).
Responde la pregunta del usuario usando SOLO el contexto. Sé conciso y prioriza la seguridad.
Cita las fuentes entre corchetes.

Contexto:
{fragmentos}

Pregunta: {pregunta}
Respuesta:"""
    resp = _w.serving_endpoints.query(
        name=CHAT_ENDPOINT,
        messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
        max_tokens=250,
    )
    return resp.choices[0].message.content, [d[0] for d in contexto]

pregunta = "¿Cómo almaceno de forma segura los cilindros de oxígeno del hospital?"
respuesta, fuentes = responder_con_rag(pregunta)
print(f"❓ {pregunta}\n")
print(f"🤖 {respuesta}\n")
print(f"📚 Fuentes consultadas: {', '.join(fuentes)}")

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Fase 2 completa
# MAGIC
# MAGIC El agente ahora **busca conocimiento por significado** con `pgvector`, todo dentro de la
# MAGIC misma Lakebase que guarda su memoria. Y con RAG entrega respuestas naturales y citadas.
# MAGIC
# MAGIC **Siguiente:** `03_fase3_geospatial` — inteligencia geoespacial de rutas y plantas con PostGIS.
