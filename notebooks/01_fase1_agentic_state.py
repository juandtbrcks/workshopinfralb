# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 🧠 Fase 1 — Memoria del Agente con LangGraph (Agentic State)
# MAGIC
# MAGIC **El problema:** los LLMs no tienen memoria. Cada llamada empieza en blanco. Un agente
# MAGIC de operaciones que olvida quién eres y en qué punto quedó el reparto es inútil en producción.
# MAGIC
# MAGIC **La solución:** un agente **LangGraph** real cuyo *estado* (la conversación) se **persiste
# MAGIC en Lakebase** mediante el `PostgresSaver` (checkpointer). Lakebase es Postgres OLTP: baja
# MAGIC latencia, transacciones ACID y escala a cero cuando el agente está inactivo — justo lo que
# MAGIC necesita el estado de un agente.
# MAGIC
# MAGIC **Qué construimos:**
# MAGIC - Un agente **ReAct** (`create_react_agent`) con el LLM de Databricks (`ChatDatabricks`).
# MAGIC - Una *tool* que consulta inventario (datos reales de Lakebase).
# MAGIC - Memoria persistente: cada conversación es un `thread_id`; LangGraph guarda los
# MAGIC   *checkpoints* en Lakebase y los recupera al reanudar.
# MAGIC
# MAGIC > **Analogía de negocio:** la diferencia entre un empleado nuevo cada día vs. uno que
# MAGIC > recuerda a tus clientes y sus pendientes.
# MAGIC >
# MAGIC > **Prerrequisito:** corre antes **`00_poblar_lakebase`** — este notebook usa las tablas
# MAGIC > `productos` y `clientes_geo` de tu base Lakebase.

# COMMAND ----------

# MAGIC %pip install --quiet "langgraph>=1.1,<2" "langgraph-prebuilt>=1.0.9" langgraph-checkpoint-postgres "psycopg[binary]" psycopg-pool databricks-langchain "databricks-sdk>=0.100.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Conexión de LangGraph a Lakebase (checkpointer)
# MAGIC
# MAGIC LangGraph persiste el estado con `PostgresSaver`, que usa **psycopg v3** sobre un *pool* de
# MAGIC conexiones. Reutilizamos los datos de conexión del helper (`lakebase_conn_params`, definido en
# MAGIC `00_setup_conexion`) para armar el *conninfo* apuntando a **tu** base.

# COMMAND ----------

from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

_p = lakebase_conn_params()   # host + token OAuth + usuario, hacia tu base infra_ws_<PARTICIPANTE>
CONNINFO = (
    f"host={_p['host']} port={_p['port']} dbname={_p['dbname']} "
    f"user={_p['user']} password={_p['password']} sslmode=require"
)

# min_size >= 1 y max_size >= min_size (requisito de psycopg_pool)
pool = ConnectionPool(conninfo=CONNINFO, min_size=1, max_size=4, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()   # crea las tablas checkpoints/* la primera vez (idempotente)
print("✔ Checkpointer de LangGraph listo sobre Lakebase")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. El LLM y una herramienta con datos reales
# MAGIC
# MAGIC Usamos `ChatDatabricks` con el endpoint de `config` (`CHAT_ENDPOINT`). Le damos al agente una
# MAGIC *tool* que consulta el catálogo de productos en Lakebase — así el agente combina
# MAGIC razonamiento del LLM con datos operacionales reales.

# COMMAND ----------

from databricks_langchain import ChatDatabricks
from langgraph.prebuilt import create_react_agent

llm = ChatDatabricks(endpoint=CHAT_ENDPOINT, max_tokens=400)

def _consulta(sql, params=()):
    """Ejecuta una consulta breve sobre Lakebase (usando el pool psycopg3 de LangGraph)."""
    with pool.connection() as c:
        cur = c.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def consultar_producto(nombre: str) -> str:
    """Consulta precio y características de un gas en el catálogo de Grupo Infra.

    Args:
        nombre: nombre (o parte) del producto, p.ej. 'oxígeno medicinal', 'acetileno'.
    """
    filas = _consulta(
        """SELECT nombre, categoria, presentacion, precio_mxn, es_comburente, es_inflamable
           FROM productos WHERE lower(nombre) LIKE lower(%s) LIMIT 3""",
        (f"%{nombre}%",),
    )
    if not filas:
        return f"No encontré productos que coincidan con '{nombre}'."
    out = []
    for f in filas:
        flags = []
        if f["es_comburente"]: flags.append("comburente")
        if f["es_inflamable"]: flags.append("inflamable")
        riesgo = f" ({', '.join(flags)})" if flags else ""
        out.append(f"{f['nombre']} — {f['presentacion']}: ${f['precio_mxn']} MXN{riesgo}")
    return "\n".join(out)

SYSTEM = (
    "Eres el Asistente de Operaciones de Grupo Infra (gases industriales y medicinales). "
    "Responde en español, con precisión y priorizando la seguridad. Usa la herramienta "
    "consultar_producto para precios y características. Sé conciso y cordial."
)

agente = create_react_agent(llm, tools=[consultar_producto], checkpointer=checkpointer,
                            prompt=SYSTEM)
print("✔ Agente ReAct creado (LLM + tool + memoria en Lakebase)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Identificar al cliente (dato real de la tabla)
# MAGIC
# MAGIC El `thread_id` de LangGraph identifica cada conversación. Usamos un cliente real de
# MAGIC `clientes_geo` para que su `cliente_id` sea el hilo de su memoria.

# COMMAND ----------

cliente = _consulta("SELECT cliente_id, nombre FROM clientes_geo WHERE tipo='hospital' ORDER BY cliente_id LIMIT 1")[0]
THREAD = {"configurable": {"thread_id": f"cliente-{cliente['cliente_id']}"}}
print(f"Cliente: {cliente['nombre']} (thread_id = cliente-{cliente['cliente_id']})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Conversación — Turno 1
# MAGIC
# MAGIC El cliente se presenta y pregunta por un producto. El agente usa la tool y responde.

# COMMAND ----------

def responder(texto):
    r = agente.invoke({"messages": [("user", texto)]}, THREAD)
    return r["messages"][-1].content

print("👤", "Hola, soy del hospital. ¿Cuánto cuesta el oxígeno medicinal?")
print("\n🤖", responder("Hola, soy del hospital. ¿Cuánto cuesta el oxígeno medicinal?"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Conversación — Turno 2 (la memoria en acción)
# MAGIC
# MAGIC En el **mismo `thread_id`**, preguntamos algo que solo se puede responder recordando el turno
# MAGIC anterior. El agente NO recibe de nuevo el contexto: lo recupera de Lakebase.

# COMMAND ----------

print("👤", "¿También manejan acetileno? ¿es peligroso guardarlo con lo que pregunté antes?")
print("\n🤖", responder("¿También manejan acetileno? ¿es peligroso guardarlo con lo que pregunté antes?"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. La prueba: el estado está PERSISTIDO en Lakebase
# MAGIC
# MAGIC LangGraph escribió los *checkpoints* en tu base. Podemos verlos con SQL (es Postgres), y
# MAGIC recuperar el estado del hilo — esto es lo que permite reanudar una conversación días después.

# COMMAND ----------

# Tablas que creó el checkpointer + cuántos checkpoints tiene este hilo
tablas = _consulta("""SELECT table_name FROM information_schema.tables
                  WHERE table_schema='public' AND table_name LIKE 'checkpoint%%' ORDER BY 1""")
print("Tablas del checkpointer en Lakebase:", [t["table_name"] for t in tablas])

n = _consulta("SELECT count(*) AS n FROM checkpoints WHERE thread_id=%s",
          (f"cliente-{cliente['cliente_id']}",))[0]["n"]
print(f"Checkpoints guardados para este cliente: {n}")

# Recuperar el estado más reciente del hilo (como haría el agente al reanudar)
estado = agente.get_state(THREAD)
print(f"\nMensajes en la memoria del hilo: {len(estado.values['messages'])}")
for m in estado.values["messages"]:
    rol = getattr(m, "type", "?")
    contenido = (m.content or "").strip().replace("\n", " ")
    if contenido:
        print(f"  [{rol:9s}] {contenido[:80]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Reanudar en una "nueva sesión"
# MAGIC
# MAGIC Simulamos que el cliente vuelve más tarde: creamos el agente **desde cero** apuntando al
# MAGIC mismo `thread_id`. Como el estado vive en Lakebase, el agente lo retoma sin repetir nada.

# COMMAND ----------

agente_nuevo = create_react_agent(llm, tools=[consultar_producto], checkpointer=checkpointer, prompt=SYSTEM)
r = agente_nuevo.invoke({"messages": [("user", "¿Qué te había preguntado sobre precios?")]}, THREAD)
print("👤 (nueva sesión) ¿Qué te había preguntado sobre precios?")
print("\n🤖", r["messages"][-1].content)

# COMMAND ----------

pool.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Fase 1 completa
# MAGIC
# MAGIC Construimos un **agente LangGraph real** (`ChatDatabricks` + tool con datos de Lakebase) cuya
# MAGIC **memoria persiste en Lakebase** vía `PostgresSaver`. Vimos que recuerda el contexto entre
# MAGIC turnos y que puede **reanudar** una conversación desde el estado guardado — todo con SQL
# MAGIC transaccional bajo el capó.
# MAGIC
# MAGIC **Siguiente:** `02_fase2_vector_search` — que el agente *busque conocimiento* semánticamente.
