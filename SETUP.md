# 🛠️ Setup del Workshop (tenant del cliente)

Guía para preparar el workshop en **un workspace nuevo**, desde la **interfaz gráfica** de Databricks.

> **Requisito del workspace:** debe ser *serverless* con **Lakebase** habilitado y acceso a
> **Foundation Model APIs**. Si no estás seguro, tu administrador de Databricks puede confirmarlo.

## Modelo del taller (7 participantes)

- **Infraestructura compartida** (la crea el **instructor una sola vez**): un proyecto Lakebase,
  el catálogo/esquema de Unity Catalog con las tablas Delta, y la ingesta de datos.
- **Espacio propio por participante:** cada quien trabaja en su **propia base de datos**
  (`infra_ws_<tus-iniciales>`) dentro del proyecto compartido, y en su **propio branch** en la
  Fase 4. Así nadie pisa los datos de los demás.

---

# PARTE A · Instructor (una sola vez)

## A1 · Importar el repositorio como Git Folder

1. **Workspace** → **Create** → **Git folder**.
2. **Git repository URL:** `https://github.com/juandtbrcks/workshopinfralb` · Provider: GitHub.
3. **Create Git folder**. (Cada participante hará esto también en su propia carpeta.)

## A2 · Crear el proyecto Lakebase (compartido)

1. Barra lateral → **Compute** → pestaña **Database instances** (o la app **Lakebase/Postgres**).
2. **Create database instance** / **New project**.
3. En el diálogo:
   - **Name:** `grupo-infra-ws` *(si usas otro, cámbialo en `config.py`)*.
   - **Postgres version:** default (PostgreSQL 17).
   - **Capacity:** default (autoscaling, scale-to-zero activo).
4. **Create**. Se crean el branch `production`, el endpoint `primary` y la base `databricks_postgres`.
5. Espera a **Available / Active** (1–2 min).

> Sube el mínimo/máximo de CU si esperas los 7 conectados a la vez (p.ej. min 1, max 4 CU).

## A3 · Crear el catálogo/esquema en Unity Catalog (compartido)

1. Barra lateral → **Catalog**.
2. Crea (o elige) un catálogo, p.ej. **`infra_workshop`** (Create catalog → Standard).
3. Dentro, **Create schema** → `infra_lakebase_ws`.

> El esquema también lo crea `00_ingesta_datos` con `CREATE SCHEMA IF NOT EXISTS`. El **catálogo**
> sí debe existir de antemano (o dar permiso de crearlo a los participantes).

## A4 · Ajustar `config.py` con los nombres compartidos y correr la ingesta

1. Abre `notebooks/config` y ajusta **lo compartido**: `LAKEBASE_PROJECT`, `UC_CATALOG`,
   `UC_SCHEMA` y los endpoints de modelos (Paso A5). Deja el `PARTICIPANTE` como esté.
2. Corre **`00_ingesta_datos`** → carga los Parquet de `data/parquet/` a las tablas Delta.
3. (Opcional) comparte el Git Folder ya configurado, o indica a cada quien que clone el repo.

## A5 · Verificar los modelos (Foundation Models)

1. Barra lateral → **Serving**.
2. Confirma estos endpoints (o equivalentes) y ponlos en `config.py`:
   - Embeddings: **`databricks-qwen3-embedding-0-6b`** (multilingüe, 1024 dims).
   - Chat/RAG: **`databricks-claude-opus-4-8`**.

---

# PARTE B · Cada participante

## B1 · Importar el repo

**Workspace** → **Create** → **Git folder** → URL `https://github.com/juandtbrcks/workshopinfralb`.

## B2 · Poner tu identificador en `config.py`

Abre `notebooks/config` y edita **solo esta línea** con tus iniciales/nombre corto
(minúsculas, sin espacios):

```python
PARTICIPANTE = "jgordon"   # ← el tuyo, p.ej. "amlopez"
```

Con eso, tu base (`infra_ws_jgordon`) y tu branch de la Fase 4 (`experimento-jgordon`) quedan
aislados. **No cambies** `LAKEBASE_PROJECT`, `UC_CATALOG` ni `UC_SCHEMA` (son los compartidos que
puso el instructor).

## B3 · Correr el lab

Adjunta cada notebook a un cluster **serverless** y córrelo con **Run all**, en orden:

1. **`05_bootstrap_datos`** — siembra **tu** base Lakebase (crea tu base si no existe, genera
   embeddings + geometrías). Lee del Delta compartido.
2. **`01_fase1` → `04_fase4`** — las fases del workshop.

> `00_setup_conexion` y `config` se cargan solos vía `%run` desde cada notebook. `00_setup_conexion`
> **crea tu base automáticamente** la primera vez. No necesitas correr `00_ingesta_datos` (eso lo
> hizo el instructor una vez).

---

## De dónde salen los datos de cada fase

- **Fase 1** — lee un cliente hospitalario real de `clientes_geo`; los mensajes de la conversación
  se generan en runtime (la memoria que el agente escribe, no una tabla).
- **Fase 2** — lee `kb_documentos` (32 docs), genera embeddings hacia tu Lakebase.
- **Fase 3** — lee `plantas`/`clientes_geo`/`unidades`, las carga como geometrías PostGIS.
- **Fase 4** — usa tu tabla `productos` (sembrada por `05_bootstrap_datos`) y experimenta con
  precios sobre **tu** branch aislado.

## (Opcional) Databricks App

La app `app/` puede desplegarse una vez (por el instructor) apuntando a una base común, o cada
quien la suya. Sigue `app/setup_permisos.md` (rol OAuth del service principal) y ajusta
`app/app.yaml` con los nombres correspondientes.

## Checklist

**Instructor:** [ ] repo importado · [ ] proyecto Lakebase · [ ] catálogo+esquema · [ ] modelos
confirmados en `config` · [ ] `00_ingesta_datos` corrido.

**Participante:** [ ] repo importado · [ ] `PARTICIPANTE` puesto en `config` · [ ]
`05_bootstrap_datos` corrido · [ ] Fases 1–4 ejecutadas.
