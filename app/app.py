"""Asistente de Operaciones INFRA — Databricks App sobre Lakebase.

Integra las capacidades del workshop en una sola app:
  • Chat con memoria persistente (Fase 1 · agent_*)
  • RAG semántico sobre base de conocimiento (Fase 2 · pgvector)
  • Inteligencia geoespacial de reparto (Fase 3 · PostGIS)
"""
import os
import json
import uuid
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import llm

app = FastAPI(title="Asistente de Operaciones INFRA")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


# ----------------------------- Modelos -----------------------------
class ChatIn(BaseModel):
    session_id: str | None = None
    user_id: str = "operador-demo"
    message: str


# ----------------------------- Salud -----------------------------
@app.get("/api/health")
def health():
    try:
        db.query("SELECT 1 AS ok")
        return {"status": "ok", "lakebase": "connected"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)[:200]}


# ----------------------------- Stats (home) -----------------------------
@app.get("/api/stats")
def stats():
    def scalar(sql):
        r = db.query(sql)
        return list(r[0].values())[0] if r else 0
    return {
        "documentos": scalar("SELECT count(*) FROM knowledge_base"),
        "clientes": scalar("SELECT count(*) FROM clientes_geo"),
        "plantas": scalar("SELECT count(*) FROM plantas"),
        "unidades": scalar("SELECT count(*) FROM unidades"),
        "pedidos": scalar("SELECT count(*) FROM pedidos"),
        "pedidos_en_ruta": scalar("SELECT count(*) FROM pedidos WHERE estado='en_ruta'"),
    }


# ----------------------------- Sugerencias (derivadas de la KB real) -----------------------------
@app.get("/api/suggestions")
def suggestions():
    """Preguntas sugeridas derivadas de documentos reales de la knowledge base.

    Tomamos títulos de categorías de seguridad (HDS/Seguridad) y los convertimos en preguntas,
    para que las sugerencias siempre reflejen el contenido realmente indexado."""
    try:
        rows = db.query("""
            SELECT titulo FROM knowledge_base
            WHERE categoria IN ('Oxígeno','Acetileno','Nitrógeno','CO2','Argón','Seguridad','Logística')
            ORDER BY random() LIMIT 5
        """)
        return {"sugerencias": [f"¿Qué debo saber sobre: {r['titulo'].lower()}?" for r in rows]}
    except Exception:
        return {"sugerencias": []}


# ----------------------------- Chat (RAG + memoria) -----------------------------
def _ensure_memory_schema():
    db.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL, started_at TIMESTAMPTZ DEFAULT now(),
            last_seen_at TIMESTAMPTZ DEFAULT now());
        CREATE TABLE IF NOT EXISTS agent_messages (
            message_id BIGSERIAL PRIMARY KEY,
            session_id UUID REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
    """)


def _search_kb(pregunta, k=4):
    qvec = llm.embed(pregunta)[0]
    return db.query(
        """SELECT doc_id, categoria, titulo, contenido,
                  1 - (embedding <=> %s::vector) AS sim
           FROM knowledge_base ORDER BY embedding <=> %s::vector LIMIT %s""",
        (qvec, qvec, k),
    )


@app.post("/api/chat")
def chat(inp: ChatIn):
    try:
        return _chat_impl(inp)
    except Exception as e:
        return {"session_id": inp.session_id,
                "respuesta": f"(No pude completar la solicitud: {type(e).__name__}: {str(e)[:200]})",
                "fuentes": []}


def _chat_impl(inp: ChatIn):
    _ensure_memory_schema()

    # sesión (memoria)
    sid = inp.session_id
    if not sid:
        row = db.query("INSERT INTO agent_sessions (user_id) VALUES (%s) RETURNING session_id",
                       (inp.user_id,))
        sid = str(row[0]["session_id"])
    db.execute("INSERT INTO agent_messages (session_id, role, content) VALUES (%s,'user',%s)",
               (sid, inp.message))

    # recuperación semántica
    try:
        ctx = _search_kb(inp.message)
    except Exception as e:
        return {"session_id": sid, "respuesta": f"(Error en búsqueda semántica: {type(e).__name__}: {str(e)[:200]})", "fuentes": []}
    fragmentos = "\n".join(f"[{d['doc_id']}] {d['titulo']}: {d['contenido']}" for d in ctx)

    # historial breve (memoria de corto plazo)
    hist = db.query(
        "SELECT role, content FROM agent_messages WHERE session_id=%s ORDER BY created_at DESC LIMIT 6",
        (sid,))
    hist = list(reversed(hist))
    historial = "\n".join(f"{h['role']}: {h['content']}" for h in hist[:-1])

    system = (
        "Eres el Asistente de Operaciones de Grupo Infra (gases industriales y medicinales). "
        "Responde en español, con precisión y priorizando la seguridad. Usa SOLO el contexto "
        "proporcionado y cita las fuentes entre corchetes, p.ej. [HDS-O2-02]. Si el contexto no "
        "cubre la pregunta, dilo con claridad."
    )
    user = f"""Contexto recuperado:
{fragmentos}

Historial reciente:
{historial or '(sin historial)'}

Pregunta del usuario: {inp.message}"""

    try:
        respuesta = llm.chat(system, user)
    except Exception as e:
        respuesta = f"(No pude generar respuesta del modelo: {str(e)[:150]})"

    db.execute("INSERT INTO agent_messages (session_id, role, content) VALUES (%s,'assistant',%s)",
               (sid, respuesta))
    db.execute("UPDATE agent_sessions SET last_seen_at=now() WHERE session_id=%s", (sid,))

    return {
        "session_id": sid,
        "respuesta": respuesta,
        "fuentes": [{"doc_id": d["doc_id"], "titulo": d["titulo"],
                     "categoria": d["categoria"], "sim": round(float(d["sim"]), 3)} for d in ctx],
    }


# ----------------------------- Geo -----------------------------
@app.get("/api/geo")
def geo():
    plantas = db.query("""SELECT planta_id, nombre, capacidad_cilindros_dia,
        ST_Y(ubicacion::geometry) AS lat, ST_X(ubicacion::geometry) AS lon FROM plantas""")
    clientes = db.query("""SELECT cliente_id, nombre, tipo, segmento, tiene_credito,
        ST_Y(ubicacion::geometry) AS lat, ST_X(ubicacion::geometry) AS lon FROM clientes_geo""")
    unidades = db.query("""SELECT unidad_id, placa, tipo_unidad, capacidad_cilindros,
        ST_Y(ubicacion::geometry) AS lat, ST_X(ubicacion::geometry) AS lon FROM unidades""")
    return {"plantas": plantas, "clientes": clientes, "unidades": unidades}


@app.get("/api/geo/nearest")
def nearest(cliente_id: str):
    """Planta más cercana a un cliente + distancia."""
    r = db.query("""
        SELECT p.planta_id, p.nombre,
               ROUND(ST_Distance(p.ubicacion, c.ubicacion)::numeric/1000, 2) AS km
        FROM plantas p, clientes_geo c
        WHERE c.cliente_id=%s
        ORDER BY p.ubicacion <-> c.ubicacion LIMIT 3""", (cliente_id,))
    return {"cliente_id": cliente_id, "plantas": r}


@app.get("/api/geo/coverage")
def coverage(planta_id: str, km: float = 12):
    """Clientes dentro del radio (km) de una planta."""
    r = db.query("""
        SELECT c.cliente_id, c.nombre, c.tipo,
               ROUND(ST_Distance(p.ubicacion, c.ubicacion)::numeric/1000, 2) AS km
        FROM plantas p JOIN clientes_geo c
          ON ST_DWithin(p.ubicacion, c.ubicacion, %s)
        WHERE p.planta_id=%s ORDER BY km""", (km * 1000, planta_id))
    return {"planta_id": planta_id, "radio_km": km, "clientes": r}


# ----------------------------- Frontend estático -----------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
