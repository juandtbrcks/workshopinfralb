# Databricks notebook source
# MAGIC %md
# MAGIC # 🌿 Fase 4 — Experimentación Segura con Branching
# MAGIC
# MAGIC **El problema:** el equipo quiere probar un cambio grande — reajustar precios de todos los
# MAGIC clientes, migrar un esquema, o dejar que un agente autónomo escriba en la base — pero
# MAGIC **no puede arriesgar la base de producción** que atiende pedidos en vivo.
# MAGIC
# MAGIC **La solución:** **Branching de Lakebase**, igual que Git pero para tu base de datos.
# MAGIC Creamos un *branch* (una copia instantánea, copy-on-write) de producción. El branch tiene
# MAGIC **todos los datos** de producción en el momento del corte, pero es **totalmente aislado**:
# MAGIC lo que escribas ahí no toca producción. Si el experimento sale bien, lo aplicas; si sale
# MAGIC mal, borras el branch. Segundos, no horas. Sin copiar terabytes.
# MAGIC
# MAGIC **Casos de uso (DataOps):**
# MAGIC - CI/CD: cada Pull Request corre sus pruebas contra un branch efímero con datos reales.
# MAGIC - Sandbox para agentes autónomos: dejar que el agente experimente sin riesgo.
# MAGIC - Migraciones de esquema y "what-if" analytics sobre datos de producción.

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary pgvector databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Estado de producción (línea base)
# MAGIC
# MAGIC Leemos el catálogo real de productos en producción y vemos su estado actual. Este es el
# MAGIC dato que NO queremos arriesgar.
# MAGIC
# MAGIC > **Prerrequisito:** la tabla `productos` debe estar poblada en Lakebase. La siembra el
# MAGIC > notebook `00_bootstrap_datos` desde la tabla Delta `{UC_CATALOG}.{UC_SCHEMA}.productos`.

# COMMAND ----------

conn = get_connection()   # conecta al branch 'production' por defecto
cur = conn.cursor()

# Usamos la tabla real de productos (poblada desde Delta por el notebook 00_bootstrap_datos).
# Este es el catálogo de precios que NO queremos arriesgar.
cur.execute("SELECT nombre, precio_mxn FROM productos ORDER BY nombre;")
filas = cur.fetchall()
print("💰 Lista de precios en PRODUCCIÓN (tabla productos):")
for nombre, precio in filas:
    print(f"  · {nombre:26s} ${precio}")
conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Crear un branch desde producción
# MAGIC
# MAGIC Usamos el SDK de Databricks (se autentica automáticamente dentro del notebook). El branch
# MAGIC `experimento-precios` nace como copia exacta de `production`, pero aislado.
# MAGIC
# MAGIC > **Nota:** `create_branch` **crea automáticamente** un endpoint `primary` read-write en el
# MAGIC > nuevo branch, así que no hay que crearlo por separado. Si tu instructor ya creó el branch,
# MAGIC > el bloque lo detecta y sigue adelante.

# COMMAND ----------

import time
from databricks.sdk.service.postgres import Branch, BranchSpec

PROJECT = dbutils.widgets.get("project_id")   # del widget (default = LAKEBASE_PROJECT del config)
BRANCH_EXP = BRANCH_EXPERIMENTO               # del config
parent = f"projects/{PROJECT}"

try:
    _w.postgres.create_branch(
        parent=parent,
        branch=Branch(spec=BranchSpec(
            source_branch=f"{parent}/branches/production",
            no_expiry=True,
        )),
        branch_id=BRANCH_EXP,
    )
    print(f"✔ Branch '{BRANCH_EXP}' creado desde production (con endpoint primary automático)")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"ℹ El branch '{BRANCH_EXP}' ya existía — continuamos")
    else:
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Esperar a que el endpoint del branch esté activo

# COMMAND ----------

for i in range(24):
    eps = list(_w.postgres.list_endpoints(f"{parent}/branches/{BRANCH_EXP}"))
    state = str(eps[0].status.current_state) if eps and eps[0].status else "PENDING"
    print(f"intento {i+1}: {state}")
    if "ACTIVE" in state:
        break
    time.sleep(10)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verificar: el branch tiene los datos de producción
# MAGIC
# MAGIC Conectamos al branch usando nuestro helper (parámetro `branch=`) y confirmamos que los
# MAGIC precios están ahí — la copia fue instantánea.

# COMMAND ----------

conn_exp = get_connection(branch=BRANCH_EXP)
cur_exp = conn_exp.cursor()
cur_exp.execute("SELECT nombre, precio_mxn FROM productos ORDER BY nombre;")
print(f"💰 Precios en el BRANCH '{BRANCH_EXP}' (copiados de producción):")
for nombre, precio in cur_exp.fetchall():
    print(f"  · {nombre:26s} ${precio}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Experimentar en el branch: subir precios 12%
# MAGIC
# MAGIC Aplicamos un cambio agresivo a todo el catálogo. Esto SOLO afecta al branch.

# COMMAND ----------

cur_exp.execute("UPDATE productos SET precio_mxn = ROUND(precio_mxn * 1.12, 2);")
cur_exp.execute("SELECT nombre, precio_mxn FROM productos ORDER BY nombre;")
print(f"🧪 Precios DESPUÉS del experimento (+12%) en el branch '{BRANCH_EXP}':")
for nombre, precio in cur_exp.fetchall():
    print(f"  · {nombre:26s} ${precio}")
conn_exp.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. La prueba del aislamiento: producción NO cambió
# MAGIC
# MAGIC Volvemos a leer producción. Los precios originales siguen intactos. 👇

# COMMAND ----------

conn_prod = get_connection(branch="production")
cur_prod = conn_prod.cursor()
cur_prod.execute("SELECT nombre, precio_mxn FROM productos ORDER BY nombre;")
print("✅ PRODUCCIÓN sigue intacta (sin el +12%):")
for nombre, precio in cur_prod.fetchall():
    print(f"  · {nombre:26s} ${precio}")
conn_prod.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Limpieza: borrar el branch experimental
# MAGIC
# MAGIC Terminado el experimento, borramos el branch (cascada: elimina su endpoint y datos).
# MAGIC En un flujo de CI/CD esto es automático al cerrar el Pull Request.

# COMMAND ----------

_w.postgres.delete_branch(f"{parent}/branches/{BRANCH_EXP}")
print(f"🗑️  Branch '{BRANCH_EXP}' eliminado (cascada: endpoint + datos). Producción intacta.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Fase 4 completa — y fin del laboratorio
# MAGIC
# MAGIC Demostramos **branching**: una copia instantánea y aislada de producción para experimentar
# MAGIC sin riesgo, y desecharla en segundos.
# MAGIC
# MAGIC ### 🎓 Lo que construimos en el workshop
# MAGIC Un backend agéntico completo sobre **una sola Lakebase**:
# MAGIC
# MAGIC | Fase | Capacidad | Resultado |
# MAGIC |------|-----------|-----------|
# MAGIC | 1 | OLTP transaccional | El agente **recuerda** (memoria corto/largo plazo + checkpoints) |
# MAGIC | 2 | `pgvector` | El agente **busca conocimiento** por significado (RAG) |
# MAGIC | 3 | `PostGIS` | El agente **razona sobre el espacio** (rutas, cobertura) |
# MAGIC | 4 | Branching | El equipo **experimenta sin riesgo** (DataOps / CI-CD) |
# MAGIC
# MAGIC **La gran idea:** Lakebase unifica estado transaccional, semántico y geoespacial de una
# MAGIC aplicación agéntica en un solo Postgres gestionado, gobernado por Unity Catalog y cercano
# MAGIC al lago analítico. Menos sistemas, menos integración, más velocidad.
