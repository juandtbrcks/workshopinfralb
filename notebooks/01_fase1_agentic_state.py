# Databricks notebook source
# MAGIC %md
# MAGIC # 🧠 Fase 1 — Memoria a Largo Plazo del Agente (Agentic State)
# MAGIC
# MAGIC **El problema:** los LLMs no tienen memoria. Cada llamada empieza en blanco. Un agente
# MAGIC de operaciones que olvida quién eres, qué pediste ayer y en qué punto quedó el reparto
# MAGIC es inútil en producción.
# MAGIC
# MAGIC **La solución:** persistir el *estado del agente* en un almacén transaccional rápido.
# MAGIC Lakebase (Postgres OLTP) es ideal: lecturas/escrituras en milisegundos, transacciones ACID,
# MAGIC y escala a cero cuando el agente está inactivo.
# MAGIC
# MAGIC **Qué construimos en esta fase:**
# MAGIC - `agent_sessions` — cada conversación del Asistente de Operaciones INFRA con un usuario.
# MAGIC - `agent_messages` — historial de mensajes (memoria de corto plazo / contexto).
# MAGIC - `agent_memory` — hechos duraderos que el agente "recuerda" entre sesiones (memoria de largo plazo).
# MAGIC - `agent_checkpoints` — estado serializado del agente para reanudar tareas largas.
# MAGIC
# MAGIC > **Analogía de negocio:** es la diferencia entre un empleado nuevo cada día vs. uno que
# MAGIC > conoce a tus clientes y recuerda pendientes.

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary pgvector databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Esquema de memoria del agente
# MAGIC
# MAGIC Modelamos las tablas que todo framework agéntico (LangGraph, custom, etc.) necesita.

# COMMAND ----------

conn = get_connection()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT NOT NULL,
    channel      TEXT DEFAULT 'app',           -- app, whatsapp, call-center
    started_at   TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    status       TEXT DEFAULT 'active'         -- active, closed
);

CREATE TABLE IF NOT EXISTS agent_messages (
    message_id   BIGSERIAL PRIMARY KEY,
    session_id   UUID REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    role         TEXT NOT NULL,                -- user, assistant, tool
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Memoria de largo plazo: hechos que persisten ENTRE sesiones (por usuario)
CREATE TABLE IF NOT EXISTS agent_memory (
    memory_id    BIGSERIAL PRIMARY KEY,
    user_id      TEXT NOT NULL,
    memory_key   TEXT NOT NULL,                -- p.ej. 'cliente_preferente', 'gas_frecuente'
    memory_value TEXT NOT NULL,
    confidence   REAL DEFAULT 1.0,
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, memory_key)
);

-- Checkpoint: estado serializado para reanudar flujos largos (JSONB)
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    session_id   UUID PRIMARY KEY REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    state        JSONB NOT NULL,
    updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON agent_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_user      ON agent_memory(user_id);
""")

print("✔ Esquema de memoria del agente creado")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Funciones de memoria (la "API" del agente)
# MAGIC
# MAGIC Encapsulamos las operaciones que el agente invoca. En producción estas serían *tools*
# MAGIC del agente o llamadas de tu framework.

# COMMAND ----------

import json

def start_session(user_id, channel="app"):
    cur.execute(
        "INSERT INTO agent_sessions (user_id, channel) VALUES (%s, %s) RETURNING session_id",
        (user_id, channel),
    )
    return cur.fetchone()[0]

def add_message(session_id, role, content):
    cur.execute(
        "INSERT INTO agent_messages (session_id, role, content) VALUES (%s, %s, %s)",
        (session_id, role, content),
    )
    cur.execute("UPDATE agent_sessions SET last_seen_at = now() WHERE session_id = %s", (session_id,))

def get_history(session_id, limit=20):
    cur.execute(
        "SELECT role, content, created_at FROM agent_messages WHERE session_id = %s ORDER BY created_at LIMIT %s",
        (session_id, limit),
    )
    return cur.fetchall()

def remember(user_id, key, value, confidence=1.0):
    """Guarda/actualiza un hecho de largo plazo (upsert)."""
    cur.execute(
        """INSERT INTO agent_memory (user_id, memory_key, memory_value, confidence)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_id, memory_key)
           DO UPDATE SET memory_value = EXCLUDED.memory_value,
                         confidence   = EXCLUDED.confidence,
                         updated_at   = now()""",
        (user_id, key, value, confidence),
    )

def recall(user_id):
    """Recupera todo lo que el agente sabe de este usuario."""
    cur.execute(
        "SELECT memory_key, memory_value, confidence FROM agent_memory WHERE user_id = %s ORDER BY updated_at DESC",
        (user_id,),
    )
    return cur.fetchall()

def save_checkpoint(session_id, state: dict):
    cur.execute(
        """INSERT INTO agent_checkpoints (session_id, state) VALUES (%s, %s)
           ON CONFLICT (session_id) DO UPDATE SET state = EXCLUDED.state, updated_at = now()""",
        (session_id, json.dumps(state)),
    )

def load_checkpoint(session_id):
    cur.execute("SELECT state FROM agent_checkpoints WHERE session_id = %s", (session_id,))
    row = cur.fetchone()
    return row[0] if row else None

print("✔ API de memoria lista: start_session, add_message, get_history, remember, recall, save/load_checkpoint")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Simulación: una conversación con el Asistente de Operaciones INFRA
# MAGIC
# MAGIC Tomamos un **cliente real** de la tabla `clientes_geo` (Unity Catalog) y simulamos su
# MAGIC conversación con el agente. Los mensajes se generan en runtime (así funciona un agente:
# MAGIC escribe su memoria conforme conversa), pero el cliente y sus datos salen de la tabla.
# MAGIC
# MAGIC > **Prerrequisito:** la tabla Delta `clientes_geo` existe (`data/02_geo.sql`).

# COMMAND ----------

# Elegimos un cliente hospitalario real desde Delta
cliente = (
    spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.clientes_geo")
         .where("tipo = 'hospital'")
         .orderBy("cliente_id")
         .first()
)
USER = cliente["cliente_id"]
NOMBRE_CLIENTE = cliente["nombre"]
print(f"Cliente: {NOMBRE_CLIENTE} (user_id={USER}, segmento={cliente['segmento']})")

# El agente recuerda lo que aprendió en sesiones anteriores
memoria_previa = recall(USER)
print("\nMemoria de largo plazo ANTES de la sesión:")
print("  (vacía — primer contacto)" if not memoria_previa else "")
for k, v, c in memoria_previa:
    print(f"  · {k} = {v} (conf {c})")

# Nueva sesión
sid = start_session(USER, channel="whatsapp")
print(f"\nSesión iniciada: {sid}")

add_message(sid, "user",      "Hola, necesito reabastecer oxígeno medicinal para el hospital.")
add_message(sid, "assistant", "Con gusto. ¿Confirmas entrega en la misma dirección registrada como la última vez?")
add_message(sid, "user",      "Sí, misma dirección. Y por favor siempre cilindros de 6m³.")
add_message(sid, "assistant", "Anotado. Programo oxígeno medicinal, cilindros de 6m³.")

# El agente EXTRAE y PERSISTE hechos de largo plazo (el nombre viene de la tabla real)
remember(USER, "razon_social",      NOMBRE_CLIENTE)
remember(USER, "producto_frecuente", "Oxígeno medicinal")
remember(USER, "presentacion_pref",  "Cilindro 6m³")

print("✔ Conversación registrada y hechos aprendidos")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: pausar y reanudar una tarea larga
# MAGIC
# MAGIC El pedido requiere validar crédito + inventario + agendar ruta. Guardamos el estado
# MAGIC intermedio para poder reanudar aunque el proceso se interrumpa.

# COMMAND ----------

save_checkpoint(sid, {
    "flujo": "reabastecimiento",
    "paso_actual": "validacion_credito",
    "pasos_completados": ["captura_pedido"],
    "pedido": {"cliente": NOMBRE_CLIENTE, "producto": "O2 medicinal", "presentacion": "6m3", "cantidad": 12},
})

estado = load_checkpoint(sid)
print("Checkpoint recuperado:")
print(json.dumps(estado, indent=2, ensure_ascii=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. El valor: memoria que persiste entre sesiones
# MAGIC
# MAGIC Días después, el mismo cliente vuelve. El agente **ya lo conoce** — no vuelve a preguntar.

# COMMAND ----------

print(f"El agente recuerda a {USER}:")
for k, v, c in recall(USER):
    print(f"  · {k:20s} → {v}")

print("\nHistorial de la sesión previa:")
for role, content, ts in get_history(sid):
    print(f"  [{role:9s}] {content}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. (Opcional) Observabilidad: métricas operativas del agente
# MAGIC
# MAGIC Como es Postgres, monitorear el estado del agente es SQL puro. Esto alimenta dashboards
# MAGIC de observabilidad (tema de la sección teórica).

# COMMAND ----------

cur.execute("""
SELECT
  (SELECT count(*) FROM agent_sessions)                        AS sesiones,
  (SELECT count(*) FROM agent_messages)                        AS mensajes,
  (SELECT count(DISTINCT user_id) FROM agent_memory)           AS usuarios_con_memoria,
  (SELECT count(*) FROM agent_checkpoints)                     AS checkpoints_activos;
""")
sesiones, mensajes, usuarios, checkpoints = cur.fetchone()
print(f"📊 Sesiones: {sesiones} | Mensajes: {mensajes} | Usuarios con memoria: {usuarios} | Checkpoints: {checkpoints}")

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Fase 1 completa
# MAGIC
# MAGIC Le dimos al agente **memoria transaccional persistente** sobre Lakebase:
# MAGIC memoria de corto plazo (mensajes), largo plazo (hechos del cliente) y checkpoints (reanudar tareas).
# MAGIC
# MAGIC **Siguiente:** `02_fase2_vector_search` — que el agente *busque conocimiento* semánticamente.
