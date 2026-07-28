# Permisos de la App sobre Lakebase (paso obligatorio)

La Databricks App corre como un **service principal** (SP). Para que pueda conectarse a
Lakebase (autoscaling), el SP debe existir como **rol OAuth de Postgres** dentro de la base.
Esto NO se crea solo — hay que ejecutarlo una vez.

## 1. Obtén el client_id del SP de la app

```bash
databricks apps get asistente-infra -p <perfil> -o json \
  | jq -r '.service_principal_client_id'
# → un UUID, p.ej. 00000000-0000-0000-0000-000000000000
```

## 2. Crea el rol OAuth y otorga permisos

Conéctate a tu base del workshop como tu usuario (admin) y ejecuta, sustituyendo `<SP>` por el
client_id del paso anterior:

```sql
-- Habilita el helper de identidades de Databricks (una vez)
CREATE EXTENSION IF NOT EXISTS databricks_auth;

-- Crea el rol ligado a la identidad OAuth del service principal
-- (NO uses CREATE ROLE normal: no queda registrado para OAuth)
SELECT databricks_create_role('<SP>', 'SERVICE_PRINCIPAL');

-- Permisos sobre los datos del workshop
GRANT USAGE, CREATE ON SCHEMA public TO "<SP>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "<SP>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<SP>";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<SP>";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO "<SP>";
```

Verifica que quedó registrado como identidad OAuth:

```sql
SELECT role_name, identity_type
FROM databricks_list_roles_impl()
WHERE role_name = '<SP>';
-- Debe devolver: <SP> | service_principal
```

## 3. Serving endpoints (Foundation Models)

Los endpoints `databricks-qwen3-embedding-0-6b` y `databricks-claude-opus-4-8` son Foundation
Model APIs (pay-per-token) y el SP puede consultarlos por defecto. No requieren permiso extra.

## Notas

- Si `databricks_create_role` dice *"role already exists"* por un `CREATE ROLE` manual previo:
  revoca sus grants, `DROP ROLE`, y vuelve a crearlo con `databricks_create_role`.
- El token OAuth que la app usa como password de Postgres se **regenera automáticamente**
  cada ~45 min (ver `db.py` → `_TOKEN_TTL`).
- La app conecta vía SDK (`w.postgres.generate_database_credential`), sin recurso `database`
  adjunto, porque el proyecto es **autoscaling** (no una database-instance del tier provisioned).
