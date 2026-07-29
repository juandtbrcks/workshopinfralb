# Databricks notebook source
# MAGIC %md
# MAGIC # 🚀 Despliegue de la App — "Asistente de Operaciones INFRA"
# MAGIC
# MAGIC En las 4 fases anteriores construimos las capacidades del agente sobre Lakebase:
# MAGIC - **Fase 1** — Memoria persistente (LangGraph + PostgresSaver)
# MAGIC - **Fase 2** — Búsqueda semántica (pgvector + RAG)
# MAGIC - **Fase 3** — Inteligencia geoespacial (PostGIS)
# MAGIC - **Fase 4** — Experimentación segura (Branching)
# MAGIC
# MAGIC Ahora las integramos en una **Databricks App** — una aplicación web con autenticación SSO
# MAGIC que cualquier miembro del equipo puede usar sin tocar notebooks.
# MAGIC
# MAGIC > **Tiempo estimado:** 10 min (opcional, fuera del lab de 70 min).
# MAGIC >
# MAGIC > **Resultado:** una URL propia como `https://asistente-infra-<workspace>.databricksapps.com`
# MAGIC > con chat, mapa interactivo y panel de métricas.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Qué incluye la App
# MAGIC
# MAGIC El código vive en la carpeta `app/` del repositorio. Es una **FastAPI** con tres vistas:
# MAGIC
# MAGIC | Vista | Capacidad Lakebase | Descripción |
# MAGIC |-------|-------------------|-------------|
# MAGIC | 💬 **Asistente** | pgvector + PostgresSaver | Chat con RAG semántico y memoria de conversación persistente |
# MAGIC | 🗺️ **Reparto** | PostGIS | Mapa Leaflet: planta más cercana, radios de cobertura, rutas |
# MAGIC | 📊 **Panel** | OLTP | Métricas operativas en vivo (pedidos, entregas, inventario) |
# MAGIC
# MAGIC Todo conecta al **mismo proyecto Lakebase** que usaste en las fases.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 1 — Crear la App desde la UI
# MAGIC
# MAGIC 1. Barra lateral → **Compute** → **Apps** → **Create App**
# MAGIC 2. **App name:** `asistente-infra` (o `asistente-infra-<tus-iniciales>` si hay varios participantes)
# MAGIC 3. **Description:** *Asistente de Operaciones para Grupo Infra — chat, mapa y panel sobre Lakebase*
# MAGIC 4. Click **Create**
# MAGIC
# MAGIC > Esto genera un **Service Principal** (SP) automático para la app y una URL única.
# MAGIC > La app aún no tiene código — solo está registrada.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Subir el código fuente
# MAGIC
# MAGIC La forma más sencilla desde la UI:
# MAGIC
# MAGIC 1. En la página de tu app recién creada, busca la sección **Source code**
# MAGIC 2. Click **Browse** y selecciona la carpeta del workspace:
# MAGIC    `/Workspace/Users/<tu-email>/workshopinfralb/app`
# MAGIC 3. Alternativamente, usa **Sync from Git** si tu workspace soporta la integración directa
# MAGIC
# MAGIC > **Archivos clave en `app/`:**
# MAGIC > - `app.py` — servidor FastAPI (rutas, lógica de chat, consultas PostGIS)
# MAGIC > - `app.yaml` — configuración de la app (env vars, recursos, permisos)
# MAGIC > - `requirements.txt` — dependencias Python
# MAGIC > - `static/` — frontend (HTML/JS/CSS, Leaflet para el mapa)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 3 — Configurar `app.yaml`
# MAGIC
# MAGIC Antes de desplegar, verifica que los valores en `app.yaml` coincidan con tu entorno.
# MAGIC Abre el archivo en el workspace y ajusta:
# MAGIC
# MAGIC ```yaml
# MAGIC env:
# MAGIC   - name: LAKEBASE_PROJECT
# MAGIC     value: "grupo-infra-ws"          # ← mismo que en config
# MAGIC   - name: LAKEBASE_BRANCH
# MAGIC     value: "production"
# MAGIC   - name: LAKEBASE_DATABASE
# MAGIC     value: "infra_ws_jgordon"         # ← pon TU base (infra_ws_<PARTICIPANTE>)
# MAGIC   - name: EMBED_ENDPOINT
# MAGIC     value: "databricks-qwen3-embedding-0-6b"
# MAGIC   - name: CHAT_ENDPOINT
# MAGIC     value: "databricks-claude-opus-4-8"
# MAGIC ```
# MAGIC
# MAGIC > **Importante:** estos valores deben ser los mismos que usaste en `notebooks/config`.
# MAGIC > Si no los cambias, la app no conectará a tu base.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 4 — Configurar permisos del Service Principal
# MAGIC
# MAGIC El SP de la app necesita poder **conectarse a Lakebase** con OAuth. Sin esto, la app
# MAGIC arrancará pero fallará al intentar consultar la base.
# MAGIC
# MAGIC **Desde la UI de Lakebase:**
# MAGIC
# MAGIC 1. **Compute** → **Database instances** → click en `grupo-infra-ws`
# MAGIC 2. Tab **Roles** → **Add role**
# MAGIC 3. Busca el SP de tu app (nombre: `asistente-infra` o similar)
# MAGIC 4. Asigna el rol **`CAN_CONNECT_AND_CREATE`**
# MAGIC 5. **Save**
# MAGIC
# MAGIC > **¿Por qué `CAN_CONNECT_AND_CREATE`?** El SP necesita crear sus propias tablas de sesión
# MAGIC > (checkpoints de LangGraph). Si solo le das `CAN_CONNECT`, no podrá escribir.
# MAGIC >
# MAGIC > Ver `app/setup_permisos.md` para instrucciones detalladas y troubleshooting.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 5 — Desplegar
# MAGIC
# MAGIC 1. En la página de tu app, click **Deploy**
# MAGIC 2. Espera a que el estado cambie a **Running** (1–2 min)
# MAGIC 3. Click en la **URL** de la app para abrirla
# MAGIC
# MAGIC > El primer despliegue puede tardar un poco más mientras instala dependencias.
# MAGIC > Los siguientes son incrementales y más rápidos.
# MAGIC
# MAGIC **Si el despliegue falla:**
# MAGIC - Revisa los **Logs** en la pestaña de la app (errores de conexión, imports faltantes)
# MAGIC - Verifica que `app.yaml` tenga los valores correctos
# MAGIC - Confirma que el SP tiene el rol en Lakebase (Paso 4)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 6 — Verificar la app
# MAGIC
# MAGIC Una vez desplegada, prueba las tres vistas:
# MAGIC
# MAGIC 1. **💬 Asistente** — pregunta: *"¿Cuánto cuesta el oxígeno medicinal?"* (debe responder con RAG)
# MAGIC 2. **🗺️ Reparto** — selecciona un cliente y verifica que muestre la planta más cercana
# MAGIC 3. **📊 Panel** — confirma que las métricas cargan (pedidos, productos)
# MAGIC
# MAGIC > La app usa **SSO** — cualquier miembro del workspace puede acceder con su login de
# MAGIC > Databricks. No se requieren credenciales adicionales para los usuarios finales.

# COMMAND ----------

# DBTITLE 1,Verificar estado de la app (opcional)
# Celda opcional: verifica si la app está corriendo desde el notebook
# Descomenta y ajusta el nombre de tu app

# from databricks.sdk import WorkspaceClient
# w = WorkspaceClient()
# app = w.apps.get("asistente-infra")
# print(f"App: {app.name}")
# print(f"Estado: {app.status.state}")
# print(f"URL: {app.url}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen del Workshop
# MAGIC
# MAGIC ¡Felicidades! Completaste el laboratorio completo:
# MAGIC
# MAGIC | Paso | Qué hiciste | Capacidad Lakebase |
# MAGIC |------|-------------|-------------------|
# MAGIC | Setup | `00_poblar_lakebase` | Reverse ETL (Delta → Lakebase) |
# MAGIC | Fase 1 | Agente con memoria | OLTP transaccional (PostgresSaver) |
# MAGIC | Fase 2 | Búsqueda semántica | pgvector (embeddings + índice HNSW) |
# MAGIC | Fase 3 | Inteligencia geoespacial | PostGIS (geography, ST_Distance) |
# MAGIC | Fase 4 | Experimentación segura | Branching (copy-on-write) |
# MAGIC | App | Despliegue web | Todo integrado + SSO |
# MAGIC
# MAGIC **El mensaje clave:** Lakebase es el **backend unificado** para aplicaciones agénticas —
# MAGIC memoria, conocimiento, geografía y operaciones, todo en una sola base Postgres gestionada
# MAGIC que escala a cero y no requiere infraestructura adicional.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC > **Siguientes pasos sugeridos:**
# MAGIC > - Conectar datos reales de tu organización
# MAGIC > - Agregar más tools al agente (e.g., crear pedidos, asignar rutas)
# MAGIC > - Configurar Reverse ETL con Synced Tables (Delta → Lakebase automático)
# MAGIC > - Montar un pipeline CI/CD con branching (un branch por PR)

