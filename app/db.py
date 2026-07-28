"""Conexión a Lakebase (autoscaling) con refresh de token OAuth."""
import time
import threading
import psycopg2
from psycopg2 import pool as pgpool
from pgvector.psycopg2 import register_vector

from config import get_workspace_client, PROJECT_ID, BRANCH, ENDPOINT, DATABASE

_lock = threading.Lock()
_pool = None
_pool_created_at = 0.0
_TOKEN_TTL = 45 * 60  # refrescar el pool cada ~45 min (el token OAuth dura ~1h)


def _conn_kwargs():
    w = get_workspace_client()
    branch_path = f"projects/{PROJECT_ID}/branches/{BRANCH}"
    endpoint_path = f"{branch_path}/endpoints/{ENDPOINT}"
    host = list(w.postgres.list_endpoints(branch_path))[0].status.hosts.host
    token = w.postgres.generate_database_credential(endpoint=endpoint_path).token
    email = w.current_user.me().user_name
    return dict(host=host, port=5432, dbname=DATABASE, user=email,
                password=token, sslmode="require")


def _build_pool():
    kw = _conn_kwargs()
    return pgpool.ThreadedConnectionPool(minconn=1, maxconn=5, **kw)


def get_pool():
    global _pool, _pool_created_at
    with _lock:
        if _pool is None or (time.time() - _pool_created_at) > _TOKEN_TTL:
            if _pool is not None:
                try:
                    _pool.closeall()
                except Exception:
                    pass
            _pool = _build_pool()
            _pool_created_at = time.time()
    return _pool


class connection:
    """Context manager que presta una conexión del pool y registra pgvector."""
    def __enter__(self):
        self._pool = get_pool()
        self.conn = self._pool.getconn()
        self.conn.autocommit = True
        try:
            register_vector(self.conn)
        except Exception:
            pass
        return self.conn

    def __exit__(self, *exc):
        try:
            self._pool.putconn(self.conn)
        except Exception:
            pass


def query(sql, params=None):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        cur.close()
        return [dict(zip(cols, r)) for r in rows]


def execute(sql, params=None):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        cur.close()
