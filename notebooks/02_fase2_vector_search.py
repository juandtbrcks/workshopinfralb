# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "1"
# ///
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
# MAGIC ## 1. Base de conocimiento (ya indexada en Lakebase)
# MAGIC
# MAGIC La documentación de Grupo Infra (HDS de gases, procedimientos logísticos, tickets y
# MAGIC normatividad) ya fue **indexada con embeddings** en el notebook `00_poblar_lakebase`.
# MAGIC
# MAGIC ### Estructura de la tabla
# MAGIC
# MAGIC El notebook `00_poblar_lakebase` creó la tabla con esta estructura:
# MAGIC
# MAGIC ```sql
# MAGIC CREATE TABLE knowledge_base (
# MAGIC     doc_id     TEXT PRIMARY KEY,        -- identificador único del documento
# MAGIC     categoria  TEXT,                     -- tipo: Oxígeno, Acetileno, Logística, Normatividad...
# MAGIC     titulo     TEXT,                     -- título descriptivo
# MAGIC     contenido  TEXT,                     -- texto completo del fragmento
# MAGIC     embedding  vector(1024)              -- vector de 1024 dims (pgvector)
# MAGIC );
# MAGIC ```
# MAGIC
# MAGIC ### Índice HNSW (búsqueda aproximada rápida)
# MAGIC
# MAGIC Para que la búsqueda por similitud sea rápida (O(log n) en vez de O(n)), se creó un índice
# MAGIC **HNSW** (Hierarchical Navigable Small World) con distancia coseno:
# MAGIC
# MAGIC ```sql
# MAGIC CREATE INDEX idx_kb_embedding
# MAGIC     ON knowledge_base
# MAGIC     USING hnsw (embedding vector_cosine_ops);
# MAGIC ```
# MAGIC
# MAGIC > **¿Qué es HNSW?** Un grafo multicapa que permite encontrar los vecinos más cercanos sin
# MAGIC > comparar contra *todos* los vectores. Ideal para producción: añades documentos sin
# MAGIC > reindexar todo.
# MAGIC
# MAGIC ### Contenido actual
# MAGIC
# MAGIC - **40 fragmentos** de conocimiento (HDS, procedimientos, normatividad, tickets)
# MAGIC - Embeddings de **1024 dimensiones** (modelo `databricks-qwen3-embedding-0-6b`)
# MAGIC - Cada documento se indexó como `"categoría: contenido"` para enriquecer el embedding
# MAGIC
# MAGIC > **El patrón real:** el conocimiento se cura y gobierna en el lago (Delta + Unity Catalog)
# MAGIC > y se *sirve* con baja latencia desde Lakebase para el agente. El notebook `00_poblar_lakebase`
# MAGIC > ejecutó ese flujo: leyó de Delta, generó embeddings y los guardó en Lakebase.
# MAGIC >
# MAGIC > **Prerrequisito:** haber corrido `00_poblar_lakebase` (la tabla `knowledge_base` debe
# MAGIC > existir con datos y embeddings).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ¿Qué es un embedding?
# MAGIC
# MAGIC Un **embedding** es una representación numérica del *significado* de un texto. El modelo de
# MAGIC lenguaje convierte cada frase en una lista de números (un vector) de tal forma que:
# MAGIC
# MAGIC - Textos con **significado similar** quedan **cerca** en el espacio vectorial
# MAGIC - Textos con **significado diferente** quedan **lejos**
# MAGIC
# MAGIC Imagínalo como un mapa: palabras relacionadas ("perro" y "mascota") están cerca,
# MAGIC mientras que palabras de otro tema ("lluvia" y "sombrilla") están en otra zona del mapa
# MAGIC — pero también cercanas entre sí porque comparten contexto.
# MAGIC
# MAGIC La celda siguiente genera una visualización simplificada (2D) de este concepto:
# MAGIC
# MAGIC ### Generación de embeddings para este workshop
# MAGIC
# MAGIC El notebook `00_poblar_lakebase` ya generó los embeddings usando el endpoint
# MAGIC `databricks-qwen3-embedding-0-6b` (1024 dimensiones), servido nativamente en el workspace.
# MAGIC
# MAGIC > **¿Por qué este modelo?** Es **multilingüe**, así que entiende bien el español de
# MAGIC > nuestros manuales y preguntas. Los modelos solo-inglés (como `bge-large-en` o
# MAGIC > `gte-large-en`, también disponibles) dan relevancia notablemente peor sobre texto en
# MAGIC > español. Elegir el modelo de embeddings correcto para tu idioma es una decisión de diseño
# MAGIC > importante en RAG.
# MAGIC >
# MAGIC > **Técnica adicional:** cada documento se indexó como `"categoría: contenido"` para darle
# MAGIC > un poco más de contexto al embedding.
# MAGIC
# MAGIC Aquí definimos la función `embed()` que usaremos para convertir las **preguntas** en
# MAGIC vectores y compararlas contra los documentos ya indexados:

# COMMAND ----------

# DBTITLE 1,Visualización: embeddings en 2D (concepto simplificado)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Simulamos posiciones 2D para ilustrar el concepto de cercanía semántica
# (en realidad los embeddings tienen 1024 dims, aquí simplificamos a 2D)
palabras = {
    "perro":     (2.1, 3.8),
    "mascota":   (2.5, 3.3),
    "gato":      (2.8, 3.9),
    "veterinario": (3.2, 3.0),
    "lluvia":    (7.2, 7.5),
    "sombrilla": (7.6, 7.0),
    "tormenta":  (7.0, 8.0),
    "nube":      (7.8, 7.8),
}

colores = {
    "perro": "#2196F3", "mascota": "#2196F3", "gato": "#2196F3", "veterinario": "#2196F3",
    "lluvia": "#FF9800", "sombrilla": "#FF9800", "tormenta": "#FF9800", "nube": "#FF9800",
}

fig, ax = plt.subplots(1, 1, figsize=(8, 6))

for palabra, (x, y) in palabras.items():
    ax.scatter(x, y, c=colores[palabra], s=200, zorder=5, edgecolors='white', linewidth=1.5)
    ax.annotate(f'  {palabra}', (x, y), fontsize=12, fontweight='bold',
                va='center', color=colores[palabra])

# Círculos para agrupar visualmente
circulo1 = plt.Circle((2.6, 3.5), 1.2, fill=False, linestyle='--', color='#2196F3', linewidth=1.5)
circulo2 = plt.Circle((7.4, 7.6), 1.2, fill=False, linestyle='--', color='#FF9800', linewidth=1.5)
ax.add_patch(circulo1)
ax.add_patch(circulo2)

# Leyenda
leg1 = mpatches.Patch(color='#2196F3', label='Cluster "animales/mascotas"')
leg2 = mpatches.Patch(color='#FF9800', label='Cluster "clima/lluvia"')
ax.legend(handles=[leg1, leg2], loc='upper left', fontsize=11)

ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.set_xlabel('Dimensión X (simplificada)', fontsize=11)
ax.set_ylabel('Dimensión Y (simplificada)', fontsize=11)
ax.set_title('Embeddings: palabras similares quedan cerca en el espacio vectorial', fontsize=13, fontweight='bold')
ax.grid(True, alpha=0.3)
ax.set_aspect('equal')

plt.tight_layout()
plt.show()

print("\n💡 En realidad los embeddings tienen 1024 dimensiones (no 2).")
print("   Pero el concepto es el mismo: significado similar = cercanía en el espacio.")

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

# DBTITLE 1,Conexión a Lakebase para consultas
from pgvector.psycopg2 import register_vector

conn = get_connection()
cur = conn.cursor()
register_vector(conn)

# Verificamos que la tabla existe y tiene datos
cur.execute("SELECT count(*) FROM knowledge_base;")
print(f"✔ Conectado a Lakebase — knowledge_base tiene {cur.fetchone()[0]} documentos indexados")

# COMMAND ----------

# DBTITLE 1,Muestra de la tabla knowledge_base (con embeddings)
# Veamos cómo se ve la tabla — incluyendo los primeros valores del embedding
cur.execute("""
    SELECT doc_id, categoria, titulo,
           LEFT(contenido, 80) AS contenido_preview,
           embedding::text
    FROM knowledge_base
    LIMIT 3;
""")

print("📋 Muestra de knowledge_base (3 docs):\n")
for doc_id, cat, titulo, contenido, emb_text in cur.fetchall():
    # Mostrar solo los primeros 5 valores del vector (de 1024)
    emb_preview = emb_text[:80] + "..."
    print(f"  📄 {doc_id} ({cat})")
    print(f"     Título: {titulo}")
    print(f"     Contenido: {contenido}...")
    print(f"     Embedding (primeros valores): {emb_preview}")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Búsqueda semántica
# MAGIC
# MAGIC Ahora viene lo interesante: buscamos por **significado**. Convertimos la pregunta a un
# MAGIC vector y usamos el operador `<=>` de pgvector que calcula **distancia coseno**
# MAGIC (menor = más similar). El índice HNSW hace esto rápido incluso con miles de documentos.
# MAGIC
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

# MAGIC %md
# MAGIC ### Operadores de distancia en pgvector
# MAGIC
# MAGIC pgvector soporta **3 métricas** de distancia, cada una con su operador SQL:
# MAGIC
# MAGIC | Operador | Métrica | Cuándo usarlo |
# MAGIC |----------|---------|---------------|
# MAGIC | `<=>` | **Distancia coseno** | La más común para embeddings de texto. Mide el ángulo entre vectores (ignora magnitud). |
# MAGIC | `<->` | **Distancia L2 (euclidiana)** | Cuando importa la distancia absoluta en el espacio. Útil si los vectores NO están normalizados. |
# MAGIC | `<#>` | **Producto interno negativo** | Cuando los vectores ya están normalizados a norma 1. Equivale a coseno pero más rápido. |
# MAGIC
# MAGIC > **Regla práctica:** para embeddings de modelos de lenguaje (como Qwen, BGE, GTE),
# MAGIC > usa **coseno** (`<=>`). Los modelos de texto suelen producir vectores de magnitud variable,
# MAGIC > y coseno los compara por dirección, no por longitud.
# MAGIC
# MAGIC ### ¿Qué significa "normalizado" en este contexto?
# MAGIC
# MAGIC Un vector está **normalizado** cuando su magnitud (norma L2) es exactamente 1. Imagínalo así:
# MAGIC
# MAGIC - **Vector normalizado:** una flecha que siempre mide 1 cm de largo. Solo importa hacia
# MAGIC   dónde apunta (ángulo). Ejemplo: `[0.6, 0.8]` → norma = √(0.36+0.64) = 1.0 ✔
# MAGIC - **Vector NO normalizado:** una flecha de largo variable. Dos textos podrían apuntar en
# MAGIC   la misma dirección pero tener distinta magnitud. Ejemplo: `[3.0, 4.0]` → norma = 5.0
# MAGIC
# MAGIC **¿Por qué importa?**
# MAGIC - Si usas **producto interno** (`<#>`) con vectores no normalizados, un texto largo con
# MAGIC   valores grandes "gana" sobre uno corto aunque apunten en la misma dirección. Resultado:
# MAGIC   sesgo por longitud del texto, no por relevancia.
# MAGIC - **Coseno** (`<=>`) divide por las normas automáticamente, así que ignora la magnitud y
# MAGIC   solo compara la *dirección* — por eso es más robusto para texto donde los embeddings
# MAGIC   varían en magnitud.
# MAGIC - **L2** (`<->`) mide distancia absoluta, así que un vector de norma 5 y otro de norma 1
# MAGIC   estarán "lejos" incluso si apuntan igual.
# MAGIC
# MAGIC > **En resumen:** si no estás seguro de si tu modelo normaliza los vectores, usa coseno.
# MAGIC > Si sabes que sí (como `text-embedding-ada-002` de OpenAI), puedes usar inner product
# MAGIC > para ganar un poco de velocidad.

# COMMAND ----------

# DBTITLE 1,Comparación de los 3 operadores de distancia
# Comparamos los 3 operadores con la misma pregunta
pregunta_demo = "¿cómo manejar una fuga de gas?"
qvec = embed(pregunta_demo)[0]

print(f"❓ \"{pregunta_demo}\"\n")
print(f"{'Operador':<12} {'Métrica':<20} {'Top-1 resultado':<20} {'Score':>8}")
print(f"{'-'*70}")

# 1. Coseno (<=>): menor = más similar (distancia, no similitud)
cur.execute("""
    SELECT doc_id, embedding <=> %s::vector AS dist_coseno
    FROM knowledge_base ORDER BY embedding <=> %s::vector LIMIT 1
""", (qvec, qvec))
r = cur.fetchone()
print(f"{'<=>':<12} {'Coseno (distancia)':<20} {r[0]:<20} {r[1]:>8.4f}")

# 2. L2 / Euclidiana (<->): menor = más cercano
cur.execute("""
    SELECT doc_id, embedding <-> %s::vector AS dist_l2
    FROM knowledge_base ORDER BY embedding <-> %s::vector LIMIT 1
""", (qvec, qvec))
r = cur.fetchone()
print(f"{'<->':<12} {'L2 (euclidiana)':<20} {r[0]:<20} {r[1]:>8.4f}")

# 3. Producto interno negativo (<#>): menor = más similar
cur.execute("""
    SELECT doc_id, embedding <#> %s::vector AS neg_inner_product
    FROM knowledge_base ORDER BY embedding <#> %s::vector LIMIT 1
""", (qvec, qvec))
r = cur.fetchone()
print(f"{'<#>':<12} {'Inner product (neg)':<20} {r[0]:<20} {r[1]:>8.4f}")

print(f"\n💡 Los 3 devuelven el mismo documento — la diferencia es la escala del score.")
print(f"   Coseno: 0 = idéntico, 2 = opuesto. L2: 0 = idéntico, ∞ = lejano.")
print(f"   Inner product: más negativo = más similar (pgvector lo niega para ORDER BY ASC).")

# COMMAND ----------

for q in [
    "¿es peligroso soldar con acetileno?",
    "riesgo de asfixia en un sótano",
    "un cliente reporta que la válvula no cierra bien",
    "cómo entregar cilindros a un cliente",
]:
    print(f"❓ {q}")
    top = buscar(q, k=1)[0]
    print(f"   → [{top[3]:.3f}] {top[0]} ({top[1]}): {top[2][:100]}...\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. RAG: combinar búsqueda + LLM para una respuesta natural
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

# MAGIC %md
# MAGIC ## 5. ¡Prueba tu propia pregunta!
# MAGIC
# MAGIC Cambia la pregunta en la celda siguiente y observa cómo el RAG recupera contexto relevante
# MAGIC y genera una respuesta natural. Prueba con lenguaje coloquial — no necesitas usar términos
# MAGIC técnicos para que encuentre lo correcto.
# MAGIC
# MAGIC > **Ideas:**
# MAGIC > - *"¿Qué hago si huele a huevo podrido cerca de los cilindros?"* (fuga de H2S)
# MAGIC > - *"¿Puedo guardar oxígeno y acetileno en el mismo cuarto?"* (seguridad)
# MAGIC > - *"¿Qué papeles necesita el chofer para transportar cilindros?"* (normatividad)

# COMMAND ----------

# DBTITLE 1,Haz tu propia pregunta con RAG
# ✂️ Cambia esta pregunta por la tuya:
mi_pregunta = "¿Qué hago si huele a huevo podrido cerca de los cilindros?"

respuesta, fuentes = responder_con_rag(mi_pregunta)
print(f"❓ {mi_pregunta}\n")
print(f"🤖 {respuesta}\n")
print(f"📚 Fuentes: {', '.join(fuentes)}")

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
