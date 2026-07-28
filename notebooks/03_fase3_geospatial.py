# Databricks notebook source
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
# MAGIC ## 1. Modelo geoespacial
# MAGIC
# MAGIC Usamos el tipo `geography(Point, 4326)` (coordenadas lat/lon, SRID 4326 = WGS84). Con
# MAGIC `geography` las distancias salen en **metros reales** sobre la superficie terrestre.

# COMMAND ----------

conn = get_connection()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS plantas (
    planta_id  TEXT PRIMARY KEY,
    nombre     TEXT NOT NULL,
    capacidad_cilindros_dia INT,
    ubicacion  geography(Point, 4326)
);

CREATE TABLE IF NOT EXISTS clientes_geo (
    cliente_id TEXT PRIMARY KEY,
    nombre     TEXT NOT NULL,
    tipo       TEXT,                          -- hospital, industria, distribuidor
    segmento   TEXT,
    tiene_credito BOOLEAN,
    ubicacion  geography(Point, 4326)
);

CREATE TABLE IF NOT EXISTS unidades (
    unidad_id  TEXT PRIMARY KEY,
    placa      TEXT,
    tipo_unidad TEXT,
    capacidad_cilindros INT,
    ubicacion  geography(Point, 4326)          -- posición actual (telemetría)
);

CREATE INDEX IF NOT EXISTS idx_clientes_geo ON clientes_geo USING gist (ubicacion);
CREATE INDEX IF NOT EXISTS idx_plantas_geo  ON plantas      USING gist (ubicacion);
""")
print("✔ Tablas geoespaciales + índices GiST creados")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Cargar ubicaciones desde las tablas Delta de Unity Catalog
# MAGIC
# MAGIC Las plantas, clientes y unidades viven gobernadas en Delta
# MAGIC (`{UC_CATALOG}.{UC_SCHEMA}.plantas` / `.clientes_geo` / `.unidades`, con `lat`/`lon`).
# MAGIC Las leemos y las convertimos a geometrías `geography` con `ST_MakePoint(lon, lat)`
# MAGIC (¡ojo al orden: longitud primero!).
# MAGIC
# MAGIC > **Prerrequisito:** las tablas Delta se crean con `data/02_geo.sql` (ver README).

# COMMAND ----------

plantas   = spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.plantas").collect()
clientes  = spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.clientes_geo").collect()
unidades  = spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.unidades").collect()

for r in plantas:
    cur.execute(
        """INSERT INTO plantas (planta_id, nombre, capacidad_cilindros_dia, ubicacion)
           VALUES (%s,%s,%s, ST_MakePoint(%s,%s)::geography)
           ON CONFLICT (planta_id) DO UPDATE SET nombre=EXCLUDED.nombre,
             capacidad_cilindros_dia=EXCLUDED.capacidad_cilindros_dia, ubicacion=EXCLUDED.ubicacion""",
        (r["planta_id"], r["nombre"], r["capacidad_cilindros_dia"], r["lon"], r["lat"]))
for r in clientes:
    cur.execute(
        """INSERT INTO clientes_geo (cliente_id, nombre, tipo, segmento, tiene_credito, ubicacion)
           VALUES (%s,%s,%s,%s,%s, ST_MakePoint(%s,%s)::geography)
           ON CONFLICT (cliente_id) DO UPDATE SET nombre=EXCLUDED.nombre, tipo=EXCLUDED.tipo,
             segmento=EXCLUDED.segmento, tiene_credito=EXCLUDED.tiene_credito, ubicacion=EXCLUDED.ubicacion""",
        (r["cliente_id"], r["nombre"], r["tipo"], r["segmento"], r["tiene_credito"], r["lon"], r["lat"]))
for r in unidades:
    cur.execute(
        """INSERT INTO unidades (unidad_id, placa, tipo_unidad, capacidad_cilindros, ubicacion)
           VALUES (%s,%s,%s,%s, ST_MakePoint(%s,%s)::geography)
           ON CONFLICT (unidad_id) DO UPDATE SET placa=EXCLUDED.placa, tipo_unidad=EXCLUDED.tipo_unidad,
             capacidad_cilindros=EXCLUDED.capacidad_cilindros, ubicacion=EXCLUDED.ubicacion""",
        (r["unidad_id"], r["placa"], r["tipo_unidad"], r["capacidad_cilindros"], r["lon"], r["lat"]))

print(f"✔ {len(plantas)} plantas, {len(clientes)} clientes, {len(unidades)} unidades leídas de Delta y cargadas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Pregunta 1 — Planta más cercana a un cliente (Nearest Neighbor)
# MAGIC
# MAGIC "¿Desde qué planta conviene surtir al Hospital Ángeles Interlomas?"

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
# MAGIC ## 4. Pregunta 2 — Clientes dentro del radio de una unidad
# MAGIC
# MAGIC "La unidad U-01 tiene espacio para una entrega extra. ¿Qué clientes hay en 5 km?"

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
# MAGIC ## 6. Pregunta 4 — Zona de cobertura (buffer / polígono)
# MAGIC
# MAGIC "¿Qué clientes caen dentro de la zona de cobertura de 12 km de la Planta Iztapalapa?"
# MAGIC Generamos un polígono de cobertura con `ST_Buffer` y contamos clientes contenidos.

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
