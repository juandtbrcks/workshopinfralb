# 🛠️ Setup desde cero (tenant del cliente)

Guía para preparar el workshop en **un workspace nuevo**, creando la infraestructura desde la
**interfaz gráfica** de Databricks. Al terminar, editas un solo archivo (`notebooks/config.py`)
y ya puedes correr el lab.

> **Requisito del workspace:** debe ser *serverless* con **Lakebase** habilitado y acceso a
> **Foundation Model APIs**. Si no estás seguro, tu administrador de Databricks puede confirmarlo.

---

## Paso 1 · Importar el repositorio como Git Folder

1. En la barra lateral, ve a **Workspace** → tu carpeta → **Create** → **Git folder**.
   (También: **Repos** → **Add Repo**.)
2. En **Git repository URL** pega:
   ```
   https://github.com/juandtbrcks/workshopinfralb
   ```
3. **Git provider:** GitHub. Deja el nombre de carpeta como `workshopinfralb`.
4. Click **Create Git folder**. Los notebooks aparecerán listos (los `.py` se abren como notebooks).

---

## Paso 2 · Crear el proyecto Lakebase (UI)

1. En el selector de la barra lateral, abre **Compute** → pestaña **Database instances**
   (o la app **Lakebase / Postgres** desde el switcher de apps, según tu versión).
2. Click **Create database instance** / **New project**.
3. En el diálogo:
   - **Name / Display name:** `grupo-infra-ws` *(puedes usar otro; lo pondrás en `config`)*.
   - **Postgres version:** deja la default (PostgreSQL 17).
   - **Capacity / Autoscaling:** deja los valores por defecto (autoscaling, scale-to-zero activo).
4. Click **Create**. Esto crea automáticamente:
   - un branch **`production`**,
   - un endpoint/compute primario **`primary`** (read-write),
   - la base por defecto `databricks_postgres`.
5. Espera a que el estado quede **Available / Active** (1–2 min).

> Estos tres valores — proyecto, branch `production`, endpoint `primary` — son los que irán en `config`.

---

## Paso 3 · Crear la base de datos del workshop (UI)

1. En tu proyecto Lakebase, abre el branch **production** → pestaña **Roles & Databases**
   (o **Databases**).
2. Click **Add database**.
   - **Name:** `infra_ws`
   - **Owner:** tu usuario (rol por defecto).
3. Click **Add**. Verás `infra_ws` en la lista.

> Si tu UI no tiene el botón, puedes crearla luego con SQL: en el notebook `00_setup_conexion`
> el helper se conecta; alternativamente usa el diálogo **Connect** → copia el `psql` y corre
> `CREATE DATABASE infra_ws;`.

---

## Paso 4 · Crear el catálogo y esquema en Unity Catalog (UI)

1. En la barra lateral ve a **Catalog**.
2. Si no tienes un catálogo destino: click **Create catalog** → nombre (p.ej. `infra_workshop`)
   → tipo **Standard** → **Create**. *(O usa un catálogo existente donde tengas permisos.)*
3. Dentro del catálogo, click **Create schema** → nombre `infra_lakebase_ws` → **Create**.

> El esquema también se crea solo al correr `00_ingesta_datos` (hace `CREATE SCHEMA IF NOT EXISTS`),
> así que este paso es opcional si prefieres dejar que el notebook lo cree. **El catálogo sí debe
> existir de antemano** (o tener permiso para crearlo).

---

## Paso 5 · Verificar los modelos (Foundation Models)

1. En la barra lateral ve a **Serving** (o **Machine Learning → Serving**).
2. Confirma que existen estos endpoints (o sus equivalentes en el workspace):
   - Embeddings: **`databricks-qwen3-embedding-0-6b`** (multilingüe, 1024 dims).
   - Chat/RAG: **`databricks-claude-opus-4-8`**.
3. Si tienen otros nombres, anótalos: los pondrás en `config`.

> Si el modelo de embeddings multilingüe no está disponible, puedes usar otro de embeddings del
> workspace, pero ajusta `EMBED_DIM` a la dimensión que devuelva (ver nota en `config`).

---

## Paso 6 · Editar `notebooks/config.py`

Abre `notebooks/config` en el Git Folder y ajusta los valores a **tu** entorno:

```python
# Lakebase (lo que creaste en el Paso 2 y 3)
LAKEBASE_PROJECT  = "grupo-infra-ws"     # ← nombre de tu proyecto/instancia Lakebase
LAKEBASE_BRANCH   = "production"
LAKEBASE_ENDPOINT = "primary"
LAKEBASE_DATABASE = "infra_ws"           # ← la base que creaste en el Paso 3

# Unity Catalog (Paso 4)
UC_CATALOG = "infra_workshop"            # ← TU catálogo
UC_SCHEMA  = "infra_lakebase_ws"

# Foundation Models (Paso 5)
EMBED_ENDPOINT = "databricks-qwen3-embedding-0-6b"
EMBED_DIM      = 1024
CHAT_ENDPOINT  = "databricks-claude-opus-4-8"

BRANCH_EXPERIMENTO = "experimento-precios"
```

Guarda. **Este es el único archivo que necesitas tocar.**

---

## Paso 7 · Cargar los datos y correr el lab

En orden (cada notebook se adjunta a un cluster serverless y se corre con **Run all**):

1. **`00_ingesta_datos`** — carga los Parquet de `data/parquet/` a tablas Delta en tu catálogo.
2. **`05_bootstrap_datos`** — siembra Lakebase (genera embeddings + geometrías PostGIS).
3. **`01_fase1` → `04_fase4`** — las fases del workshop.

> `00_setup_conexion` y `config` se cargan solos vía `%run` desde cada fase; no los corres directo.

---

## (Opcional) Paso 8 · Desplegar la Databricks App

La app **"Asistente de Operaciones INFRA"** (carpeta `app/`) integra las 3 capacidades. Para
desplegarla en el tenant del cliente, sigue `app/setup_permisos.md` (crea el rol OAuth del service
principal) y actualiza los `value:` de `app/app.yaml` con los mismos nombres que pusiste en `config`.

---

## Checklist rápido

- [ ] Repo importado como Git Folder
- [ ] Proyecto Lakebase creado (estado Available)
- [ ] Base `infra_ws` creada
- [ ] Catálogo + esquema en Unity Catalog
- [ ] Endpoints de modelos confirmados
- [ ] `config.py` editado con mis nombres
- [ ] `00_ingesta_datos` → `05_bootstrap_datos` corridos
- [ ] Fases 1–4 ejecutadas
