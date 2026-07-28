# Databricks notebook source
# MAGIC %md
# MAGIC # 🧪 Workshop Lakebase · Grupo Infra
# MAGIC ## Notebook 00 — Setup y Conexión
# MAGIC
# MAGIC **Caso de negocio (hilo conductor de todo el lab):**
# MAGIC Vamos a construir el **"Asistente de Operaciones INFRA"**, un agente que apoya al equipo de
# MAGIC logística y atención de Grupo Infra (distribución de gases industriales y medicinales):
# MAGIC responde dudas de seguridad, recuerda el contexto de cada conversación, encuentra información
# MAGIC en manuales técnicos y optimiza las rutas de reparto de cilindros.
# MAGIC
# MAGIC A lo largo de 4 fases usaremos **Lakebase** (Postgres gestionado en Databricks) como el
# MAGIC cerebro operacional del agente:
# MAGIC
# MAGIC | Fase | Capacidad Lakebase | Qué construimos |
# MAGIC |------|--------------------|-----------------|
# MAGIC | 1 | OLTP transaccional | Memoria de largo plazo del agente (Agentic State) |
# MAGIC | 2 | `pgvector` | Búsqueda semántica sobre base de conocimiento |
# MAGIC | 3 | `PostGIS` | Inteligencia geoespacial de rutas y plantas |
# MAGIC | 4 | Branching | Experimentación segura sin tocar producción |
# MAGIC
# MAGIC > **Nota para la audiencia mixta:** cada notebook empieza con el *por qué de negocio* antes
# MAGIC > del código. Si vienes del lado técnico, el código es ejecutable tal cual; si vienes de
# MAGIC > negocio, los bloques markdown te cuentan la historia completa.

# COMMAND ----------

# MAGIC %md
# MAGIC ## ¿Qué es Lakebase y por qué importa?
# MAGIC
# MAGIC Lakebase es **PostgreSQL gestionado, serverless y con branching**, nativo del Data Intelligence
# MAGIC Platform. A diferencia de un Postgres tradicional:
# MAGIC
# MAGIC - **Separación cómputo/almacenamiento** → escala a cero cuando no se usa (pagas por uso).
# MAGIC - **Branching estilo Git** → clonas la base entera en segundos para probar sin riesgo.
# MAGIC - **Integración con Unity Catalog** → gobernanza unificada y sync bidireccional con Delta.
# MAGIC - **Baja latencia (OLTP)** → ideal para apps y agentes que necesitan lectura/escritura en ms.
# MAGIC
# MAGIC Esto lo convierte en la pieza que faltaba para las **aplicaciones agénticas**: los agentes
# MAGIC necesitan un estado transaccional rápido (memoria), y a la vez cercanía al lago analítico.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Parámetros del workshop
# MAGIC
# MAGIC Los parámetros viven en el notebook central **`config`**. Aquí lo cargamos con `%run`
# MAGIC (queda disponible para todas las fases porque ellas cargan este setup) y exponemos los
# MAGIC valores de Lakebase también como *widgets*, para poder reapuntar de forma interactiva sin
# MAGIC editar código. **Para cambiar los defaults, edita `config`.**

# COMMAND ----------

# MAGIC %run ./config

# COMMAND ----------

# Widgets de Lakebase con defaults tomados del config (permiten override interactivo)
dbutils.widgets.text("project_id", LAKEBASE_PROJECT, "Proyecto Lakebase")
dbutils.widgets.text("branch", LAKEBASE_BRANCH, "Branch")
dbutils.widgets.text("endpoint", LAKEBASE_ENDPOINT, "Endpoint")
dbutils.widgets.text("database", LAKEBASE_DATABASE, "Base de datos")

PROJECT_ID = dbutils.widgets.get("project_id")
BRANCH     = dbutils.widgets.get("branch")
ENDPOINT   = dbutils.widgets.get("endpoint")
DATABASE   = dbutils.widgets.get("database")

print(f"Proyecto : {PROJECT_ID}")
print(f"Branch   : {BRANCH}")
print(f"Endpoint : {ENDPOINT}")
print(f"Database : {DATABASE}")

# COMMAND ----------

# MAGIC %md
# MAGIC > **Dependencias:** cada notebook de fase instala `psycopg2-binary`, `pgvector` y
# MAGIC > `databricks-sdk` en su **primera celda** (antes de invocar este setup con `%run`). Por eso
# MAGIC > aquí NO instalamos ni reiniciamos Python: este notebook solo *define* el helper de conexión.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Helper de conexión (reutilizado en todas las fases)
# MAGIC
# MAGIC Este patrón es el corazón del lab. El SDK de Databricks nos da:
# MAGIC - el **host** del endpoint,
# MAGIC - un **token OAuth** de corta duración (no manejamos contraseñas),
# MAGIC - nuestro **usuario** (email) como rol de Postgres.
# MAGIC
# MAGIC > El token OAuth expira ~1 hora. Si una fase falla por autenticación, vuelve a ejecutar
# MAGIC > `get_connection()` para regenerarlo.

# COMMAND ----------

import psycopg2
from databricks.sdk import WorkspaceClient

_w = WorkspaceClient()

def lakebase_conn_params(project_id=PROJECT_ID, branch=BRANCH, endpoint=ENDPOINT, database=DATABASE):
    """Resuelve host + token OAuth + usuario para conectarse a Lakebase."""
    branch_path   = f"projects/{project_id}/branches/{branch}"
    endpoint_path = f"{branch_path}/endpoints/{endpoint}"
    eps  = list(_w.postgres.list_endpoints(branch_path))
    host = eps[0].status.hosts.host
    token = _w.postgres.generate_database_credential(endpoint=endpoint_path).token
    email = _w.current_user.me().user_name
    return dict(host=host, port=5432, dbname=database, user=email, password=token, sslmode="require")

def get_connection(**kw):
    """Devuelve una conexión psycopg2 lista para usar."""
    params = lakebase_conn_params(**kw)
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    return conn

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Crear la base de datos (si no existe)
# MAGIC
# MAGIC Dentro de **tu propio proyecto Lakebase** creamos la base `infra_ws`. Nos conectamos primero
# MAGIC a la base `postgres` por defecto para crearla si aún no existe (idempotente).
# MAGIC
# MAGIC > Si esto falla con un error de proyecto/endpoint no encontrado, es que **aún no creaste tu
# MAGIC > proyecto Lakebase** `{LAKEBASE_PROJECT}` en la UI. Revisa el Paso correspondiente de `SETUP.md`.

# COMMAND ----------

# Validación temprana con mensaje claro si el proyecto Lakebase no existe todavía
try:
    _eps = list(_w.postgres.list_endpoints(f"projects/{PROJECT_ID}/branches/{BRANCH}"))
except Exception as e:
    raise RuntimeError(
        f"No encuentro el proyecto Lakebase 'projects/{PROJECT_ID}' (branch '{BRANCH}'). "
        f"Créalo primero en la UI (Compute → Database instances → Create) con el nombre "
        f"'{PROJECT_ID}'. Ver SETUP.md."
    ) from e

_admin = get_connection(database="postgres")
_admin_cur = _admin.cursor()
_admin_cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))
if _admin_cur.fetchone():
    print(f"ℹ La base '{DATABASE}' ya existe — continuamos")
else:
    _admin_cur.execute(f'CREATE DATABASE "{DATABASE}"')
    print(f"✔ Base '{DATABASE}' creada")
_admin_cur.close()
_admin.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Probar la conexión y habilitar extensiones
# MAGIC
# MAGIC Habilitamos `pgvector` (Fase 2) y `PostGIS` (Fase 3) una sola vez aquí, ya sobre tu base.

# COMMAND ----------

conn = get_connection()
cur = conn.cursor()

cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

cur.execute("SELECT version();")
print("Postgres:", cur.fetchone()[0].split(",")[0])

cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','postgis') ORDER BY extname;")
print("\nExtensiones habilitadas:")
for name, ver in cur.fetchall():
    print(f"  ✔ {name:10s} {ver}")

cur.close()
conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Setup completo
# MAGIC
# MAGIC Ya tienes:
# MAGIC - Conexión verificada a Lakebase (`infra_ws`).
# MAGIC - Helper `get_connection()` disponible.
# MAGIC - Extensiones `vector` y `postgis` habilitadas.
# MAGIC
# MAGIC **Siguiente:** `01_fase1_agentic_state` — le damos memoria de largo plazo al agente.
