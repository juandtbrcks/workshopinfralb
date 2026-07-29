# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 🗺️ Fase 3 — Inteligencia Geoespacial (PostGIS)
# MAGIC
# MAGIC **El problema:** Grupo Infra reparte cilindros desde varias plantas de llenado a cientos de
# MAGIC clientes en la CDMX. El Asistente de Operaciones necesita responder preguntas espaciales:
# MAGIC *¿cuál es la planta más cercana a este hospital? ¿qué clientes quedan dentro del radio de
# MAGIC reparto de una unidad? ¿qué tan lejos está la siguiente parada?*
# MAGIC
# MAGIC **La solución:** **PostGIS**, la extensión geoespacial estándar de la industria, corriendo
# MAGIC dentro de Lakebase. Guardamos ubicaciones como geometrías y consultamos distancias, vecinos
# MAGIC cercanos y contención en polígonos — con SQL.
# MAGIC
# MAGIC **El valor unificado:** el agente ahora tiene en UNA sola base: memoria (Fase 1),
# MAGIC conocimiento semántico (Fase 2) e inteligencia geográfica (Fase 3). Un solo backend
# MAGIC operacional para toda la aplicación agéntica.

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary pgvector databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./00_setup_conexion

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Modelo geoespacial (ya creado en `00_poblar_lakebase`)
# MAGIC
# MAGIC Las tablas geoespaciales ya fueron creadas y pobladas por el notebook `00_poblar_lakebase`.
# MAGIC Aquí explicamos su estructura para entender las consultas que haremos.
# MAGIC
# MAGIC ### Tipo de dato: `geography(Point, 4326)`
# MAGIC
# MAGIC - **`geography`** — tipo de PostGIS que almacena coordenadas sobre el esferoide terrestre.
# MAGIC   A diferencia de `geometry` (que trabaja en un plano), `geography` calcula distancias
# MAGIC   **reales en metros** considerando la curvatura de la Tierra.
# MAGIC - **`Point`** — un solo punto (lat, lon). También existe `Polygon`, `LineString`, etc.
# MAGIC - **`4326`** — el SRID (sistema de referencia). 4326 = WGS84, el estándar de GPS/Google Maps.
# MAGIC
# MAGIC ### Estructura de las tablas
# MAGIC
# MAGIC ```sql
# MAGIC -- Plantas de llenado (7 registros: CDMX, Toluca, Cuernavaca)
# MAGIC CREATE TABLE plantas (
# MAGIC     planta_id               TEXT PRIMARY KEY,
# MAGIC     nombre                  TEXT NOT NULL,
# MAGIC     capacidad_cilindros_dia INT,
# MAGIC     ubicacion               geography(Point, 4326)  -- coordenada de la planta
# MAGIC );
# MAGIC
# MAGIC -- Clientes (25 registros: hospitales, industrias, laboratorios, educación)
# MAGIC CREATE TABLE clientes_geo (
# MAGIC     cliente_id    TEXT PRIMARY KEY,
# MAGIC     nombre        TEXT NOT NULL,
# MAGIC     tipo          TEXT,          -- hospital, industria, distribuidor, laboratorio, educacion
# MAGIC     segmento      TEXT,
# MAGIC     tiene_credito BOOLEAN,
# MAGIC     ubicacion     geography(Point, 4326)
# MAGIC );
# MAGIC
# MAGIC -- Unidades de reparto (8 registros: posición actual por GPS/telemétrica)
# MAGIC CREATE TABLE unidades (
# MAGIC     unidad_id           TEXT PRIMARY KEY,
# MAGIC     placa               TEXT,
# MAGIC     tipo_unidad         TEXT,
# MAGIC     capacidad_cilindros INT,
# MAGIC     ubicacion           geography(Point, 4326)  -- posición actual
# MAGIC );
# MAGIC ```
# MAGIC
# MAGIC ### Índice GiST (Generalized Search Tree)
# MAGIC
# MAGIC Para que las consultas espaciales ("vecino más cercano", "dentro de radio") sean rápidas,
# MAGIC se creó un **índice GiST** sobre la columna `ubicacion`:
# MAGIC
# MAGIC ```sql
# MAGIC CREATE INDEX idx_clientes_geo ON clientes_geo USING gist (ubicacion);
# MAGIC CREATE INDEX idx_plantas_geo  ON plantas      USING gist (ubicacion);
# MAGIC ```
# MAGIC
# MAGIC > **¿Qué es GiST?** Un índice multidimensional que particiona el espacio en rectángulos
# MAGIC > anidados (R-tree internamente). Permite buscar "puntos cercanos a X" sin escanear toda
# MAGIC > la tabla. Similar a como HNSW acelera vectores, GiST acelera geometrías.
# MAGIC
# MAGIC > **Prerrequisito:** haber corrido `00_poblar_lakebase` (las tablas deben existir con datos).

# COMMAND ----------

conn = get_connection()
cur = conn.cursor()

# Verificamos que las tablas existen y tienen datos
tablas_geo = {"plantas": 0, "clientes_geo": 0, "unidades": 0}
for tabla in tablas_geo:
    cur.execute(f"SELECT count(*) FROM {tabla};")
    tablas_geo[tabla] = cur.fetchone()[0]

print(f"✔ Conectado a Lakebase — tablas geoespaciales disponibles:")
for tabla, count in tablas_geo.items():
    print(f"  • {tabla:15s} {count:>3} registros")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Veamos los datos geoespaciales
# MAGIC
# MAGIC Las ubicaciones ya fueron cargadas por `00_poblar_lakebase` desde las tablas Delta de
# MAGIC Unity Catalog. Cada coordenada `lat`/`lon` se convirtió a `geography` con
# MAGIC `ST_MakePoint(lon, lat)` (¡ojo al orden: **longitud primero**, latitud segundo!).
# MAGIC
# MAGIC Verifiquemos un par de registros para entender cómo se ven los datos espaciales:

# COMMAND ----------

# Muestra de plantas con su ubicación geoespacial
cur.execute("""
    SELECT planta_id, nombre, capacidad_cilindros_dia,
           ST_Y(ubicacion::geometry) AS lat,
           ST_X(ubicacion::geometry) AS lon
    FROM plantas
    ORDER BY nombre
    LIMIT 5;
""")
print("🏭 Plantas de llenado:")
print(f"  {'ID':<10} {'Nombre':<30} {'Capacidad/día':>13} {'Lat':>9} {'Lon':>10}")
print(f"  {'-'*75}")
for pid, nombre, cap, lat, lon in cur.fetchall():
    print(f"  {pid:<10} {nombre:<30} {cap:>10} cil  {lat:>9.4f} {lon:>10.4f}")

print("\n🏥 Muestra de clientes:")
cur.execute("""
    SELECT cliente_id, nombre, tipo,
           ST_Y(ubicacion::geometry) AS lat,
           ST_X(ubicacion::geometry) AS lon
    FROM clientes_geo
    LIMIT 5;
""")
print(f"  {'ID':<10} {'Nombre':<30} {'Tipo':<15} {'Lat':>9} {'Lon':>10}")
print(f"  {'-'*80}")
for cid, nombre, tipo, lat, lon in cur.fetchall():
    print(f"  {cid:<10} {nombre:<30} {tipo:<15} {lat:>9.4f} {lon:>10.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Referencia rápida: operadores y funciones de PostGIS
# MAGIC
# MAGIC Antes de ver las consultas, aquí un resumen de lo que PostGIS nos da:
# MAGIC
# MAGIC #### Operadores
# MAGIC
# MAGIC | Operador | Nombre | Qué hace | Escenario |
# MAGIC |----------|--------|----------|------------|
# MAGIC | `<->` | KNN (distancia) | Distancia entre dos geometrías, optimizado con índice GiST | "¿Cuál es la planta más cercana a este cliente?" |
# MAGIC | `&&` | Bounding-box overlap | ¿Los rectángulos envolventes se traslapan? | Pre-filtro rápido antes de cálculos costosos |
# MAGIC
# MAGIC #### Funciones de medición
# MAGIC
# MAGIC | Función | Retorna | Escenario |
# MAGIC |---------|---------|------------|
# MAGIC | `ST_Distance(a, b)` | Distancia en **metros** (con `geography`) | "¿A cuántos km está el cliente X de la planta Y?" |
# MAGIC | `ST_DWithin(a, b, metros)` | `true`/`false` | "¿Qué clientes están a menos de 5 km?" (usa índice) |
# MAGIC | `ST_Length(line)` | Longitud de una línea en metros | "¿Cuánto mide esta ruta?" |
# MAGIC | `ST_Area(polygon)` | Área en m² | "¿Qué tamaño tiene esta zona de cobertura?" |
# MAGIC
# MAGIC #### Funciones de construcción
# MAGIC
# MAGIC | Función | Crea | Escenario |
# MAGIC |---------|------|------------|
# MAGIC | `ST_MakePoint(lon, lat)` | Un `Point` | Convertir coordenadas GPS a geometría |
# MAGIC | `ST_Buffer(geom, metros)` | Un polígono circular | "Zona de cobertura de 12 km alrededor de la planta" |
# MAGIC | `ST_MakeLine(punto_a, punto_b)` | Una línea | Trazar una ruta entre dos puntos |
# MAGIC | `ST_Collect(geom)` | Multi-geometría (agregado) | Agrupar todos los puntos de una ruta |
# MAGIC
# MAGIC #### Funciones de relación espacial
# MAGIC
# MAGIC | Función | Pregunta que responde | Escenario |
# MAGIC |---------|----------------------|------------|
# MAGIC | `ST_Contains(a, b)` | ¿A contiene completamente a B? | "¿Este cliente cae dentro de mi zona de cobertura?" |
# MAGIC | `ST_Intersects(a, b)` | ¿Se tocan o traslapan? | "¿La ruta cruza por zona restringida?" |
# MAGIC | `ST_Within(a, b)` | ¿A está completamente dentro de B? | Inverso de Contains |
# MAGIC | `ST_Crosses(a, b)` | ¿Una línea cruza un polígono? | "¿La ruta pasa por el centro histórico?" |
# MAGIC
# MAGIC #### Funciones de transformación / exportación
# MAGIC
# MAGIC | Función | Resultado | Escenario |
# MAGIC |---------|-----------|------------|
# MAGIC | `ST_AsGeoJSON(geom)` | JSON estándar para mapas | Enviar ubicaciones a un frontend / Databricks App |
# MAGIC | `ST_AsText(geom)` | WKT legible (`POINT(-99.17 19.43)`) | Debugging / logs |
# MAGIC | `ST_X(geom)` / `ST_Y(geom)` | Coordenada individual | Extraer lon/lat de un punto |
# MAGIC | `ST_Centroid(geom)` | Centro de un polígono | "¿Dónde queda el centro de esta zona?" |
# MAGIC
# MAGIC > 💡 **Tip:** Con `geography` (lo que usamos), las distancias salen en **metros reales**.
# MAGIC > Con `geometry` saldrían en las unidades del SRID (grados si es 4326) — menos útil para
# MAGIC > preguntas de negocio. Siempre que trabajes con lat/lon y necesites metros, usa `geography`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Pregunta 1 — Planta más cercana a un cliente (Nearest Neighbor)
# MAGIC
# MAGIC "¿Desde qué planta conviene surtir al Hospital Ángeles Interlomas?"
# MAGIC
# MAGIC Usamos el operador **KNN** (`<->`) de PostGIS que aprovecha el índice GiST para encontrar
# MAGIC vecinos cercanos sin escanear toda la tabla:

# COMMAND ----------

cur.execute("""
SELECT p.nombre,
       ROUND(ST_Distance(p.ubicacion, c.ubicacion)::numeric / 1000, 2) AS km
FROM plantas p
CROSS JOIN clientes_geo c
WHERE c.cliente_id = 'CLI-ANG'
ORDER BY p.ubicacion <-> c.ubicacion   -- operador KNN de PostGIS
LIMIT 3;
""")
print("Planta más cercana al Hospital Ángeles Interlomas:")
for nombre, km in cur.fetchall():
    print(f"  · {nombre:22s} → {km} km")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Pregunta 2 — Clientes dentro del radio de una unidad (`ST_DWithin`)
# MAGIC
# MAGIC "La unidad U-01 tiene espacio para una entrega extra. ¿Qué clientes hay en 5 km?"
# MAGIC
# MAGIC `ST_DWithin(geom_a, geom_b, distancia_metros)` usa el índice GiST para filtrar
# MAGIC eficientemente — no calcula la distancia a *todos* los clientes:

# COMMAND ----------

cur.execute("""
SELECT c.nombre, c.tipo,
       ROUND(ST_Distance(u.ubicacion, c.ubicacion)::numeric) AS metros
FROM unidades u
JOIN clientes_geo c
  ON ST_DWithin(u.ubicacion, c.ubicacion, 5000)   -- 5000 metros
WHERE u.unidad_id = 'U-01'
ORDER BY metros;
""")
print("Clientes a ≤5 km de la unidad U-01:")
for nombre, tipo, metros in cur.fetchall():
    print(f"  · {nombre:28s} ({tipo:12s}) {metros} m")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Pregunta 3 — Optimización de ruta (vecino más cercano encadenado)
# MAGIC
# MAGIC Una heurística simple de ruteo: partir de la planta y siempre ir al cliente pendiente más
# MAGIC cercano. Útil para dar al operador un orden de visita razonable.
# MAGIC
# MAGIC > **Nota:** esto es un *greedy nearest-neighbor*, no un TSP óptimo. Pero es rápido y
# MAGIC > da un buen punto de partida para la operación diaria.

# COMMAND ----------

def ruta_vecino_cercano(planta_id, tipo_cliente=None):
    # punto de inicio = planta
    cur.execute("SELECT nombre, ubicacion FROM plantas WHERE planta_id=%s", (planta_id,))
    nombre_planta, punto_actual = cur.fetchone()

    filtro = "WHERE tipo = %s" if tipo_cliente else ""
    params = (tipo_cliente,) if tipo_cliente else ()
    cur.execute(f"SELECT cliente_id, nombre, ubicacion FROM clientes_geo {filtro}", params)
    pendientes = cur.fetchall()

    ruta, total_km = [], 0.0
    actual = punto_actual
    while pendientes:
        # elegir el pendiente más cercano al punto actual
        mejor, mejor_dist, mejor_idx = None, None, None
        for i, (cid, nom, geo) in enumerate(pendientes):
            cur.execute("SELECT ST_Distance(%s::geography, %s::geography)", (actual, geo))
            d = cur.fetchone()[0]
            if mejor_dist is None or d < mejor_dist:
                mejor, mejor_dist, mejor_idx = (cid, nom, geo), d, i
        ruta.append((mejor[1], round(mejor_dist / 1000, 2)))
        total_km += mejor_dist / 1000
        actual = mejor[2]
        pendientes.pop(mejor_idx)
    return nombre_planta, ruta, round(total_km, 2)

planta, ruta, total = ruta_vecino_cercano("PL-VALL", tipo_cliente="hospital")
print(f"Ruta de reparto a hospitales desde {planta}:\n")
for i, (destino, km) in enumerate(ruta, 1):
    print(f"  {i}. {destino:30s} (+{km} km)")
print(f"\n  Distancia total aproximada: {total} km")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Pregunta 4 — Zona de cobertura (`ST_Buffer` + `ST_Contains`)
# MAGIC
# MAGIC "¿Qué clientes caen dentro de la zona de cobertura de 12 km de la Planta Iztapalapa?"
# MAGIC
# MAGIC `ST_Buffer(geom, metros)` genera un polígono circular alrededor del punto, y
# MAGIC `ST_Contains` verifica qué clientes caen dentro:

# COMMAND ----------

cur.execute("""
WITH cobertura AS (
    SELECT ST_Buffer(ubicacion, 12000) AS zona   -- buffer de 12 km
    FROM plantas WHERE planta_id = 'PL-IZTA'
)
SELECT c.nombre, c.tipo
FROM clientes_geo c, cobertura z
WHERE ST_Contains(z.zona::geometry, c.ubicacion::geometry)
ORDER BY c.tipo;
""")
print("Clientes dentro de la zona de cobertura (12 km) de Planta Iztapalapa:")
rows = cur.fetchall()
if not rows:
    print("  (ninguno)")
for nombre, tipo in rows:
    print(f"  · {nombre} ({tipo})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. (Opcional) Exportar para visualizar en un mapa
# MAGIC
# MAGIC `ST_AsGeoJSON` convierte geometrías a GeoJSON, listo para un mapa en una Databricks App
# MAGIC o cualquier front-end.

# COMMAND ----------

cur.execute("""
SELECT nombre, ST_AsGeoJSON(ubicacion) FROM clientes_geo LIMIT 3;
""")
print("Ubicaciones en formato GeoJSON (para mapas):")
for nombre, geojson in cur.fetchall():
    print(f"  · {nombre}: {geojson}")

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Fase 3 completa
# MAGIC
# MAGIC El agente ahora razona sobre **el espacio físico**: planta más cercana, clientes en radio,
# MAGIC orden de ruta y zonas de cobertura — todo con PostGIS dentro de Lakebase.
# MAGIC
# MAGIC **Siguiente:** `04_fase4_branching` — experimentar con cambios sin arriesgar producción.
