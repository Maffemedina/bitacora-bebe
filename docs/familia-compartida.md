# Diseño técnico: Bitácora familiar compartida

## Objetivo
Varias personas con chats de Telegram distintos comparten la misma bitácora de
uno o más hijos. Lo que cualquiera registre aparece para todos los miembros de la
familia. Multi-familia: un usuario puede pertenecer a más de una familia.

## Modelos
- **Family**(`id`, `name?`, `created_at`)
- **FamilyMember**(`id`, `family_id`, `chat_id` BIGINT, `display_name`, `role` ∈ {editor, admin}, `created_at`): `UNIQUE(family_id, chat_id)`.
- **Invite**(`id`, `family_id`, `token_hash` SHA-256, `created_by`, `role_to_grant`='editor', `expires_at`, `used_at?`, `created_at`).
- **Child**: + `family_id` (dueña de la autorización). `owner_id` se conserva como **creador histórico**, nunca autoriza.
- Milestone/Appointment/Advice/Control/Media siguen colgando de `child_id`; la autorización se resuelve por `child.family_id` + membresía vigente.

### Roles (política, no strings)
`Rol.EDITOR`: leer y editar datos familiares (incluye crear hijos).
`Rol.ADMIN`: editor + invitar, revocar y gestionar miembros.

## Migraciones (Alembic)
- **0001_baseline**: esquema previo a familia (8 tablas actuales).
- **0002_familia**: crea Family/FamilyMember/Invite, agrega `Child.family_id`, y **backfill** idempotente (por cada `owner_id` con hijos → una familia, owner = `admin`, asigna `family_id`).
- Motor **async** reutilizando `app.db._normalize` (`sqlite+aiosqlite` / `postgresql+asyncpg`).

### Baseline y despliegue
- **Base nueva:** `alembic upgrade head` (0001 crea todo + 0002).
- **Base existente creada con `create_all` (sin Alembic):**
  1. `alembic stamp 0001`: marca el baseline como aplicado **sin recrear** las tablas existentes.
  2. `alembic upgrade head`: aplica solo 0002 (familia + backfill).
- **Railway (`railway.json`):** el comando de arranque corre `alembic upgrade head` y luego `uvicorn app.main:app`.
- **`create_all()` deja de ser mecanismo de producción.** Solo se usa en los tests (fixture).

## Flujo Telegram
- **`/compartir`** (solo admin, sobre la familia del hijo activo): crea Invite (`token = secrets.token_urlsafe(32)`, guarda `sha256(token)`, `expires_at = now + 24h`, un solo uso, rol `editor`). Devuelve `https://t.me/<TELEGRAM_BOT_USERNAME>?start=join_<token>`.
- **Deep link:** `/start join_<token>` → **redención atómica** (ver abajo) → mensaje: a qué familia se unió + que un admin puede revocar el acceso. Al unirse: asegura `UserProfile` y activa el primer hijo de la familia.
- **`/mi_familia`** (familia del hijo activo): miembros (`display_name` + rol) e hijos; el admin ve botones de revocar (miembro / invitación pendiente).
- **Revocar** (admin): elimina `FamilyMember`; el revocado pierde acceso de inmediato.

### Redención atómica
`UPDATE invite SET used_at=now WHERE id=? AND used_at IS NULL AND expires_at > now`.
Si `rowcount==1`, en la **misma transacción** se crea el `FamilyMember`; cualquier
fallo hace **rollback total**. Evita doble uso concurrente.

## Autorización
Helper único `resolver_hijo(chat_id, child_id, rol_min) -> Child|None`: devuelve el
hijo solo si `chat_id` es miembro **vigente** de `child.family_id` con rol ≥ `rol_min`.
Se usa en **toda** lectura, mutación y **callback** (borrar/adjuntar re-validan aquí).

### Contexto activo (multi-familia)
- `active_child_id` es personal por chat; el hijo activo fija la **familia activa**.
- `get_active_child` revalida membresía: revocado → `None` inmediato.
- `list_children` = hijos de **todas** las familias donde el usuario es miembro.
- `_resolver_activo` distingue: (1) activo válido → opera; (2) perfil sin membresía vigente (revocado) → mensaje "acceso revocado / sin familia activa", **sin onboarding ni creación de familia**; (3) usuario nuevo real → onboarding (crea su familia, owner=admin).


## Seguridad
- Token de alta entropía; en DB solo el **hash**. Un solo uso + 24h.
- Callbacks siempre re-autorizan (no confían en el botón).
- `owner_id` nunca es fuente de autorización.

## Tests de aceptación clave
1. Dos familias aisladas.
2. Dos miembros de una familia ven/editan el mismo hijo.
3. Usuario en dos familias (ve hijos de ambas; el activo fija la familia).
4. Revocado con hijo activo → sin acceso, sin onboarding, sin crear familia.
5. Redención doble/concurrente → solo una crea membresía; expiración en el `WHERE`.
6. Migración real sobre SQLite temporal desde el esquema previo (backfill).
