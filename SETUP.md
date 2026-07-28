# 🛠️ Setup del Workshop (paso a paso)

Guía para que **cada participante** prepare y corra el lab por su cuenta, desde la **interfaz
gráfica** de Databricks. Cada quien crea su propia infraestructura, así que todos son
independientes (el instructor solo guía). Son ~10 minutos de setup.

> **Requisito del workspace:** debe ser *serverless* con **Lakebase** habilitado y acceso a
> **Foundation Model APIs**. Si no estás seguro, tu administrador de Databricks puede confirmarlo.

> **Tu identificador:** a lo largo de la guía usarás un nombre corto (tus iniciales, p.ej.
> `jgordon`) — solo minúsculas/números. De él dependen los nombres de **tu** proyecto y esquema,
> para no chocar con los de tus compañeros.

---

## Paso 1 · Importar el repositorio como Git Folder

1. Barra lateral → **Workspace** → tu carpeta → **Create** → **Git folder**.
2. **Git repository URL:** `https://github.com/juandtbrcks/workshopinfralb` · Provider: **GitHub**.
3. **Create Git folder**. Los `.py` se abren como notebooks.

## Paso 2 · Crear tu proyecto Lakebase

1. Barra lateral → **Compute** → pestaña **Database instances** (o la app **Lakebase/Postgres**).
2. **Create database instance** / **New project**.
3. En el diálogo:
   - **Name:** `infra-ws-<tus-iniciales>` (p.ej. `infra-ws-jgordon`). *Solo minúsculas, números y guiones.*
   - **Postgres version:** default (PostgreSQL 17).
   - **Capacity:** default (autoscaling, scale-to-zero activo).
4. **Create**. Se crean automáticamente el branch `production`, el endpoint `primary` y la base
   `databricks_postgres`.
5. Espera a **Available / Active** (1–2 min).

> La base `infra_ws` del workshop la crea por ti el notebook `00_setup_conexion` — no la creas a mano.

## Paso 3 · Verificar el catálogo y los modelos

1. **Catalog:** confirma que existe un catálogo donde tengas permiso de crear esquemas
   (p.ej. `jgworkspaceclassic_catalog` o el que indique el instructor). Tu **esquema** propio lo
   crea el notebook de ingesta.
2. **Serving:** confirma que existen estos endpoints (o equivalentes):
   - Embeddings: **`databricks-qwen3-embedding-0-6b`** (multilingüe, 1024 dims).
   - Chat/RAG: **`databricks-claude-opus-4-8`**.

## Paso 4 · Configurar `config.py`

Abre `notebooks/config` y edita:

```python
PARTICIPANTE = "jgordon"     # ← tus iniciales (igual que en el Paso 2)
```

De ahí se derivan **tu** proyecto (`infra-ws-jgordon`) y **tu** esquema
(`infra_lakebase_ws_jgordon`). Verifica también que `UC_CATALOG` apunte al catálogo del Paso 3 y
que los endpoints de modelos coincidan. **Nada más se toca.**

## Paso 5 · Correr los notebooks (en orden)

Adjunta cada notebook a un cluster **serverless** y córrelo con **Run all**:

1. **`00_ingesta_datos`** — crea tu esquema en Unity Catalog y carga los Parquet de
   `data/parquet/` como tablas Delta.
2. **`05_bootstrap_datos`** — crea tu base Lakebase y la siembra (embeddings + geometrías PostGIS),
   leyendo de tus tablas Delta.
3. **`01_fase1` → `04_fase4`** — las fases del workshop.

> `00_setup_conexion` y `config` se cargan solos vía `%run` desde cada notebook; no los corres
> directo. `00_setup_conexion` crea tu base `infra_ws` la primera vez.

---

## De dónde salen los datos de cada fase

- **Fase 1** — lee un cliente hospitalario real de `clientes_geo`; los mensajes de la conversación
  se generan en runtime (la memoria que el agente escribe, no una tabla).
- **Fase 2** — lee `kb_documentos` (32 docs), genera embeddings hacia tu Lakebase.
- **Fase 3** — lee `plantas`/`clientes_geo`/`unidades`, las carga como geometrías PostGIS.
- **Fase 4** — usa tu tabla `productos` (sembrada por `05_bootstrap_datos`) y experimenta con
  precios sobre un branch aislado dentro de tu proyecto.

## (Opcional) Databricks App

La app `app/` integra las 3 capacidades. Para desplegarla, sigue `app/setup_permisos.md` (crea el
rol OAuth del service principal en tu Lakebase) y ajusta `app/app.yaml` con los nombres de tu
proyecto/base.

## Checklist

- [ ] Repo importado como Git Folder
- [ ] Mi proyecto Lakebase `infra-ws-<iniciales>` creado (Available)
- [ ] Catálogo con permiso + modelos confirmados
- [ ] `config.py` con mi `PARTICIPANTE`
- [ ] `00_ingesta_datos` corrido (tablas Delta)
- [ ] `05_bootstrap_datos` corrido (Lakebase sembrado)
- [ ] Fases 1–4 ejecutadas

## Limpieza (post-workshop)

Borra tu proyecto Lakebase para no dejar cómputo: **Compute → Database instances → tu proyecto →
Delete**. (O por CLI: `databricks postgres delete-project projects/infra-ws-<iniciales> -p <perfil>`.)
