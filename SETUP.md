# 🛠️ Setup del Workshop (paso a paso)

Guía para preparar y correr el lab desde la **interfaz gráfica** de Databricks.

> **Requisito del workspace:** debe ser *serverless* con **Lakebase** habilitado y acceso a
> **Foundation Model APIs**. Si no estás seguro, tu administrador de Databricks puede confirmarlo.

## Modelo del taller (7 participantes)

- **Infraestructura compartida** — la crea **un solo participante (el "administrador")**, una vez:
  el **proyecto Lakebase**, el **catálogo/esquema** de Unity Catalog y la **ingesta de datos**.
- **Espacio propio de cada participante** — dentro del proyecto compartido, cada quien trabaja en
  **su propia base de datos** (`infra_ws_<iniciales>`) y en **su propio branch** en la Fase 4. Así
  nadie pisa los datos de los demás.

> **Tu identificador (`PARTICIPANTE`):** un nombre corto (tus iniciales, p.ej. `jgordon`) — solo
> minúsculas y números. De él dependen tu base de datos y tu branch.

---

# PARTE A · Participante administrador (una sola vez)

> Solo **una persona** hace esta parte. Prepara la infraestructura que todos comparten.

## A1 · Importar el repositorio como Git Folder

1. Barra lateral → **Workspace** → **Create** → **Git folder**.
2. **Git repository URL:** `https://github.com/juandtbrcks/workshopinfralb` · Provider: **GitHub**.
3. **Create Git folder**.

## A2 · Crear el proyecto Lakebase (compartido)

1. Barra lateral → **Compute** → pestaña **Database instances** (o la app **Lakebase/Postgres**).
2. **Create database instance** / **New project**.
3. En el diálogo:
   - **Name:** `grupo-infra-ws` *(si usas otro, todos deben ponerlo en `config.py` → `LAKEBASE_PROJECT`)*.
   - **Postgres version:** default (PostgreSQL 17).
   - **Capacity:** default (autoscaling). Sube el máximo de CU (p.ej. 4–8) si esperas a los 7 conectados a la vez.
4. **Create**. Se crean el branch `production`, el endpoint `primary` y la base `databricks_postgres`.
5. Espera a **Available / Active** (1–2 min).

## A3 · Crear el catálogo/esquema en Unity Catalog (compartido)

1. Barra lateral → **Catalog**.
2. Crea (o elige) un catálogo, p.ej. **`jgworkspaceclassic_catalog`** o el del taller
   (Create catalog → Standard). Ponlo en `config.py` → `UC_CATALOG` si es distinto.
3. El **esquema** `infra_lakebase_ws` lo crea el notebook de ingesta (A4) — no hace falta a mano.

## A4 · Cargar los datos (ingesta, una vez)

1. Abre `notebooks/config` y verifica que `LAKEBASE_PROJECT`, `UC_CATALOG`, `UC_SCHEMA` y los
   endpoints de modelos (A5) sean los correctos del taller.
2. Adjunta **`00_ingesta_datos`** a un cluster serverless y córrelo con **Run all** → crea el
   esquema `infra_lakebase_ws` y carga los Parquet de `data/parquet/` como tablas Delta.

## A5 · Verificar los modelos (Foundation Models)

1. Barra lateral → **Serving**.
2. Confirma estos endpoints (o equivalentes) y anótalos para `config.py`:
   - Embeddings: **`databricks-qwen3-embedding-0-6b`** (multilingüe, 1024 dims).
   - Chat/RAG: **`databricks-claude-opus-4-8`**.

> Al terminar A1–A5, avisa a los demás los nombres finales de **proyecto**, **catálogo** y
> **endpoints** (si cambiaste alguno respecto a los defaults del repo).

---

# PARTE B · Todos los participantes (cada quien)

> Esto lo hace **cada persona**, incluido el administrador.

## B1 · Importar el repo

**Workspace** → **Create** → **Git folder** → URL `https://github.com/juandtbrcks/workshopinfralb`.

## B2 · Poner tu identificador en `config.py`

Abre `notebooks/config` y edita **solo esta línea**:

```python
PARTICIPANTE = "jgordon"   # ← tus iniciales (minúsculas y números)
```

Con eso, tu base (`infra_ws_jgordon`) y tu branch de la Fase 4 (`experimento-jgordon`) quedan
aislados. **No cambies** `LAKEBASE_PROJECT`, `UC_CATALOG` ni `UC_SCHEMA` — son los compartidos que
preparó el administrador (solo ajústalos si te avisó que usó nombres distintos).

## B3 · Correr el lab

Adjunta cada notebook a un cluster **serverless** y córrelo con **Run all**, en orden:

1. **`05_bootstrap_datos`** — crea **tu** base Lakebase y la siembra (embeddings + geometrías),
   leyendo de las tablas Delta compartidas.
2. **`01_fase1` → `04_fase4`** — las fases del workshop.

> `00_setup_conexion` y `config` se cargan solos vía `%run`; no los corres directo.
> `00_setup_conexion` **crea tu base automáticamente** la primera vez.
> **No corras `00_ingesta_datos`** — eso ya lo hizo el administrador una sola vez.

---

## De dónde salen los datos de cada fase

- **Fase 1** — agente **LangGraph** (`ChatDatabricks` + tool sobre `productos`); usa `clientes_geo`
  para el identificador del hilo y persiste la conversación en Lakebase con `PostgresSaver`.
- **Fase 2** — lee `kb_documentos` (32 docs), genera embeddings hacia tu Lakebase.
- **Fase 3** — lee `plantas`/`clientes_geo`/`unidades`, las carga como geometrías PostGIS.
- **Fase 4** — usa tu tabla `productos` (sembrada por `05_bootstrap_datos`) y experimenta con
  precios sobre **tu** branch aislado.

## (Opcional) Databricks App

La app `app/` integra las 3 capacidades. El administrador puede desplegarla una vez apuntando a una
base común. Sigue `app/setup_permisos.md` (rol OAuth del service principal) y ajusta `app/app.yaml`.

## Checklist

**Administrador (Parte A):** [ ] repo importado · [ ] proyecto Lakebase `grupo-infra-ws` ·
[ ] catálogo + modelos en `config` · [ ] `00_ingesta_datos` corrido.

**Cada participante (Parte B):** [ ] repo importado · [ ] `PARTICIPANTE` en `config` ·
[ ] `05_bootstrap_datos` corrido · [ ] Fases 1–4 ejecutadas.

## Limpieza (post-workshop)

El administrador borra el proyecto Lakebase compartido: **Compute → Database instances →
`grupo-infra-ws` → Delete** (esto elimina todas las bases de los participantes).
