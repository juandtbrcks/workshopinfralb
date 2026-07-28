# Workshop Lakebase · Grupo Infra — Laboratorio Práctico (Sección 3)

Notebooks ejecutables para la **Fase 3 de la agenda**: *Desarrollo de una Aplicación Agéntica*
sobre Lakebase (70 min). Audiencia mixta (técnica + negocio).

> ### 🚀 ¿Empiezas desde cero en tu propio workspace?
> Sigue **[SETUP.md](SETUP.md)** — guía paso a paso por la **interfaz gráfica** para importar el
> repo, crear el proyecto Lakebase, la base de datos, el catálogo/esquema y ajustar `config`.
> Todo lo demás en este README asume que esa infra ya existe.

## Hilo conductor

Construimos el **"Asistente de Operaciones INFRA"**, un agente para el equipo de logística y
atención de Grupo Infra (distribución de gases industriales y medicinales). A lo largo de 4 fases,
Lakebase actúa como el **backend unificado** del agente:

| Notebook | Fase | Capacidad Lakebase | Resultado |
|----------|------|--------------------|-----------|
| `config` | — | Parámetros | **Único lugar** con project/branch/DB, catálogo/esquema UC y modelos |
| `00_ingesta_datos` | — | Parquet → Delta | Crea las tablas Delta desde `data/parquet/` (primer paso) |
| `00_setup_conexion` | — | Conexión + extensiones | Helper `get_connection()` + `pgvector`/`postgis` |
| `01_fase1_agentic_state` | 1 | OLTP transaccional | El agente **recuerda** (memoria corto/largo plazo + checkpoints) |
| `02_fase2_vector_search` | 2 | `pgvector` | El agente **busca conocimiento** por significado (RAG) |
| `03_fase3_geospatial` | 3 | `PostGIS` | El agente **razona sobre el espacio** (rutas, cobertura) |
| `04_fase4_branching` | 4 | Branching | El equipo **experimenta sin riesgo** (DataOps / CI-CD) |
| `05_bootstrap_datos` | — | Reverse ETL | Carga los datos de UC a Lakebase (KB con embeddings, geo, productos, pedidos) |

### Configuración centralizada

Todos los parámetros del lab viven en el notebook **`config`** (proyecto/branch/endpoint/DB de
Lakebase, catálogo y esquema de UC, endpoints de embeddings/chat, y el nombre del branch de la
Fase 4). No hay valores hardcodeados repartidos.

El encadenamiento es `fase → %run ./00_setup_conexion → %run ./config`. Como `%run` es
**transitivo** en Databricks, las variables del `config` quedan disponibles en todos los
notebooks automáticamente. **Para reapuntar el workshop a otro entorno, edita solo `config`.**
Los valores de Lakebase también se exponen como *widgets* en `00_setup_conexion` para override
interactivo sin tocar código.

## Datos sintéticos (empaquetados en el repo)

Datos curados con sentido de negocio de Grupo Infra, incluidos como **archivos Parquet** en
`data/parquet/`. El notebook `00_ingesta_datos` los carga como tablas Delta en Unity Catalog.

| Archivo Parquet | → Tabla Delta | Filas | Alimenta |
|-----------------|---------------|-------|----------|
| `kb_documentos.parquet` | `kb_documentos` | 32 | Fase 2 — HDS de gases, procedimientos, tickets, normatividad |
| `plantas.parquet` | `plantas` | 5 | Fase 3 — plantas de llenado (zona metro CDMX) |
| `clientes_geo.parquet` | `clientes_geo` | 20 | Fase 3 — hospitales/industrias/distribuidores |
| `unidades.parquet` | `unidades` | 6 | Fase 3 — unidades de reparto |
| `productos.parquet` | `productos` | 12 | App / Fase 4 — catálogo de gases con precios |
| `pedidos.parquet` | `pedidos` | 200 | App — pedidos/entregas |

> Son datos **sintéticos** (no información real de Grupo Infra), aptos para un repo compartido.
> El flujo es: `data/parquet/*.parquet` → **`00_ingesta_datos`** → tablas Delta → **`05_bootstrap_datos`** → Lakebase.

## Databricks App: "Asistente de Operaciones INFRA"

App FastAPI + Leaflet desplegada que integra las 3 capacidades sobre Lakebase (código en `app/`):

- **💬 Asistente** — chat con RAG semántico (`pgvector` + Claude) y memoria de conversación persistente.
- **🗺️ Reparto** — mapa interactivo (PostGIS): planta más cercana, radios de cobertura.
- **📊 Panel** — métricas operativas en vivo desde Lakebase.

**URL:** https://asistente-infra-7474648405668119.aws.databricksapps.com
(requiere login SSO del workspace)

> ⚠️ **Setup obligatorio de permisos:** el service principal de la app necesita un rol OAuth
> en Lakebase. Ver `app/setup_permisos.md`. Sin esto, la app no conecta a la base.

Desplegar cambios:
```bash
cd app
databricks sync . /Workspace/Users/<tu-email>/apps/asistente-infra \
  --exclude .venv --exclude __pycache__ -p fe-vm-jgworkspaceclassic
databricks apps deploy asistente-infra \
  --source-code-path /Workspace/Users/<tu-email>/apps/asistente-infra -p fe-vm-jgworkspaceclassic
```

## Entorno de referencia

Valores usados durante el desarrollo (**úsalos como referencia**; en tu tenant defines los tuyos
en `config` — ver [SETUP.md](SETUP.md)):

- **Proyecto Lakebase:** `grupo-infra-ws` (tier Autoscaling)
- **Base de datos:** `infra_ws`
- **Extensiones:** `vector` 0.8.0, `postgis` 3.5.0 (las habilita `00_setup_conexion`)
- **Foundation Models:**
  - Embeddings: `databricks-qwen3-embedding-0-6b` (multilingüe, 1024 dims)
  - Chat/RAG: `databricks-claude-opus-4-8`

> Verificado end-to-end: las 4 fases corren contra Lakebase real (memoria + upserts, búsqueda
> semántica en español, consultas PostGIS, y branching con aislamiento de producción confirmado).

## Cómo importar el repo al workspace

**Recomendado — Git Folder (Repos):** Workspace → **Create → Git folder** → URL
`https://github.com/juandtbrcks/workshopinfralb`. Los `.py` se abren como notebooks. Ver
[SETUP.md](SETUP.md) para el paso a paso.

Los notebooks usan `%run ./00_setup_conexion` y `%run ./config`, así que **deben quedar en la
misma carpeta** (importar el repo completo lo garantiza).

## Cómo correr el lab

> **Los notebooks leen de las tablas Delta de Unity Catalog** — no traen datos embebidos. Por eso
> las tablas deben existir antes. Orden recomendado:

0. **Prerrequisito (una vez):** corre **`00_ingesta_datos`** — carga los Parquet de `data/parquet/`
   como tablas Delta en el catálogo/esquema de `config`. Luego corre **`05_bootstrap_datos`** para
   sembrar Lakebase (necesario para la App y para la Fase 4, que lee `productos` de Lakebase).
1. Adjunta cualquier notebook a un cluster **serverless** o con runtime reciente (el SDK ya viene).
2. Abre `01_fase1_agentic_state` y ejecuta de arriba a abajo. La **primera celda** instala
   dependencias (`psycopg2-binary`, `pgvector`, `databricks-sdk`) y reinicia Python; luego
   `%run ./00_setup_conexion` (que a su vez carga `config`).
3. Repite con `02`, `03`, `04` en orden.

**De dónde salen los datos de cada fase:**
- **Fase 1** — lee un cliente hospitalario real de `clientes_geo`; los mensajes de la
  conversación se generan en runtime (es la memoria que el agente escribe, no una tabla).
- **Fase 2** — lee `kb_documentos` (32 docs), genera embeddings hacia Lakebase.
- **Fase 3** — lee `plantas`/`clientes_geo`/`unidades`, las carga como geometrías PostGIS.
- **Fase 4** — lee la tabla `productos` (debe estar sembrada en Lakebase por `05_bootstrap_datos`)
  y experimenta con precios sobre un branch aislado.

### Parámetros (widgets)

`00_setup_conexion` expone widgets (`project_id`, `branch`, `endpoint`, `database`). Si el
instructor asignó otro proyecto/branch por participante, ajústalos ahí.

## Notas para el instructor

- **Tokens OAuth** expiran ~1 h. Si una fase falla por autenticación, re-ejecuta la celda de
  `get_connection()` (regenera el token).
- **Fase 2** (embeddings en español): elegimos el modelo *multilingüe* `qwen3` a propósito —
  los modelos solo-inglés (`bge`/`gte`) dan relevancia notablemente peor sobre texto en español.
  Es un buen punto de discusión de diseño de RAG con la audiencia.
- **Fase 4** (branching): `create_branch` del SDK **auto-crea** el endpoint `primary`, por eso el
  notebook no lo crea aparte. El branch se borra al final (cascada). Si varios participantes
  corren la fase a la vez, dales `branch_id` distintos (p.ej. `experimento-<iniciales>`) para
  evitar colisión de nombres.
- **Costo:** el proyecto es Autoscaling (escala a cero). Cada branch levanta cómputo temporal
  (0.5–2 CU). Borra branches sobrantes con
  `databricks postgres delete-branch projects/grupo-infra-ws/branches/<branch> -p fe-vm-jgworkspaceclassic`.

## Limpieza total (post-workshop)

```bash
databricks postgres delete-project projects/grupo-infra-ws -p fe-vm-jgworkspaceclassic
```
