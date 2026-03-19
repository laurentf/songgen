# Code Conventions

> Conventions Python pour projets FastAPI + asyncpg.
> Réutilisable tel quel dans d'autres projets.

---

## Table des matières

1. [Stack & tooling](#1-stack--tooling)
2. [Structure du projet](#2-structure-du-projet)
3. [Typage strict](#3-typage-strict)
4. [Imports](#4-imports)
5. [Configuration](#5-configuration)
6. [Base de données & repositories](#6-base-de-données--repositories)
7. [Services](#7-services)
8. [API / Routers](#8-api--routers)
9. [Injection de dépendances](#9-injection-de-dépendances)
10. [Gestion d'erreurs](#10-gestion-derreurs)
11. [Logging structuré](#11-logging-structuré)
12. [Registry & Factory](#12-registry--factory)
13. [Protocols & Adapters](#13-protocols--adapters)
14. [Workers & tâches async](#14-workers--tâches-async)
15. [Tests](#15-tests)
16. [Clean code](#16-clean-code)
17. [Linting & qualité](#17-linting--qualité)

---

## 1. Stack & tooling

| Outil | Usage |
|-------|-------|
| **Python 3.12+** | Syntaxe moderne (`X \| None`, `list[str]`, PEP 695) |
| **uv** | Package manager (remplace pip/poetry) |
| **FastAPI** | Framework web async |
| **asyncpg** | Driver PostgreSQL natif async |
| **Pydantic v2** | Validation, settings, schemas |
| **structlog** | Logging structuré JSON |
| **ARQ** | File de tâches async (Redis) |
| **ruff** | Linter + formatter (remplace flake8/isort/black) |
| **mypy** | Type-checking strict |
| **vulture** | Détection de code mort |
| **pytest** | Tests unitaires et intégration |

---

## 2. Structure du projet

Architecture **vertical slice** — chaque feature est autonome :

```
project/
├── main.py                          # Entry point + lifespan
├── pyproject.toml                   # Config unique (deps, ruff, mypy, pytest)
├── app/
│   ├── core/                        # Infrastructure partagée
│   │   ├── config.py                # Pydantic BaseSettings (@cache)
│   │   ├── database.py              # Pool asyncpg factory
│   │   ├── exceptions.py            # Hiérarchie d'erreurs custom
│   │   ├── logging.py               # Setup structlog
│   │   ├── security.py              # JWT + auth dependencies
│   │   ├── deps/                    # FastAPI dependencies (DI)
│   │   ├── text_utils.py            # Fonctions pures (regex, nettoyage)
│   │   ├── time_utils.py            # Fonctions pures (dates, durées)
│   │   └── audio_utils.py           # Transcodage audio
│   ├── features/                    # Domaines métier (vertical slicing)
│   │   └── <feature>/
│   │       ├── api/                 # Routers FastAPI
│   │       ├── services/            # Logique métier (orchestration)
│   │       ├── repositories/        # Accès données (SQL brut)
│   │       └── schemas/             # Pydantic models (request/response)
│   ├── providers/                   # Intégrations externes (pluggable)
│   │   ├── <type>/
│   │   │   ├── protocol.py          # Interface abstraite (Protocol)
│   │   │   └── <impl>/adapter.py    # Implémentation concrète
│   │   ├── registry.py              # Factory pattern générique
│   │   └── factory.py               # Instanciation des adapters
│   └── workers/
│       └── arq_app.py               # Définitions de tâches ARQ
├── tests/
│   ├── conftest.py                  # Fixtures partagées
│   └── test_*.py                    # Tests par fonctionnalité
└── docs/                            # Documentation
```

**Règles :**
- Un fichier = **< 400 lignes**. Au-delà, découper.
- Pas de répertoire `models/` partagé — les modèles vivent dans `schemas/` de chaque feature.
- Dépendances unidirectionnelles : `api → services → repositories → database`.
- Pas d'import circulaire (lazy imports uniquement dans les workers).

---

## 3. Typage strict

### Règles générales

```python
# ✅ Union moderne
value: str | None

# ✅ Builtins directement (pas de typing.List, typing.Dict)
items: list[str]
mapping: dict[str, int]
unique: set[float]

# ✅ Toutes les fonctions publiques typées (params + retour)
def compute(data: list[int], *, threshold: float = 0.5) -> float: ...

# ❌ Jamais de Any, jamais de # type: ignore
# ❌ Jamais de TYPE_CHECKING — importer directement
# ❌ Jamais de Optional[X] — utiliser X | None
```

### Quel type pour quel usage

| Besoin | Type | Exemple |
|--------|------|---------|
| **Validation request/response** | `Pydantic BaseModel` | `LoginRequest(BaseModel)` |
| **Shape d'une row SQL** | `TypedDict` | `HostRow(TypedDict)` |
| **Énumérations string** | `StrEnum` | `ContentSegmentType(StrEnum)` |
| **Value object immutable** | `@dataclass(frozen=True, slots=True)` | `SegmentContext` |
| **Contexte optionnel** | `TypedDict(total=False)` | `ScheduleCtx` |
| **Interface abstraite** | `Protocol` | `LLMAdapter(Protocol)` |

### Exemples

```python
from enum import StrEnum
from typing import TypedDict, Required
from dataclasses import dataclass, field

# StrEnum — valeurs explicites
class HostStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"

# TypedDict — shape de données
class TrackRow(TypedDict):
    id: str
    title: str
    artist: str
    genre: str | None

# TypedDict partiel (tout optionnel sauf Required)
class ScheduleCtx(TypedDict, total=False):
    pool: Required[asyncpg.Pool]
    redis: ArqRedis | None
    last_tick_ts: float

# Dataclass immutable — value object
@dataclass(frozen=True, slots=True)
class SegmentContext:
    track_info: TrackRow | None = None
    position: int = 0
    required_tools: list[str] = field(default_factory=list)
```

---

## 4. Imports

```python
"""Module docstring."""

from __future__ import annotations          # 1. Future

import asyncio                               # 2. Stdlib
from datetime import datetime
from uuid import UUID

import asyncpg                               # 3. Third-party
import structlog
from fastapi import APIRouter, Depends

from app.core.config import get_settings     # 4. App (absolus)
from app.core.exceptions import NotFoundError
from app.features.hosts.repositories.host_repository import HostRepository

logger = structlog.get_logger(__name__)       # 5. Logger en module-level
```

**Règles :**
- **Toujours** imports en haut du fichier.
- **Toujours** imports absolus (`from app.xxx`, jamais `from .xxx`).
- **Jamais** de wildcard (`from x import *`).
- **Jamais** de `TYPE_CHECKING` block.
- **Jamais** d'import inline dans une fonction (sauf workers ARQ pour éviter les circulaires, ou lazy-loading volontaire type `pydub`).
- Ordre : `future → stdlib → third-party → app` (géré par ruff `I`).

---

## 5. Configuration

Pydantic `BaseSettings` avec `@cache` pour singleton :

```python
from functools import cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Grouper par domaine
    # -- Database
    database_url: SecretStr = Field(...)
    db_pool_min_size: int = Field(default=5)
    db_pool_max_size: int = Field(default=10)

    # -- LLM
    llm_provider: Literal["mistral"] = Field(default="mistral")
    mistral_api_key: SecretStr | None = Field(default=None)

    # -- Feature flags
    debug: bool = Field(default=False)

@cache
def get_settings() -> Settings:
    return Settings()
```

**Règles :**
- Secrets toujours en `SecretStr` (accès via `.get_secret_value()`).
- Valeurs par défaut raisonnables.
- `extra="ignore"` pour tolérer les variables d'env inconnues.

---

## 6. Base de données & repositories

> **Migrations** : le schéma SQL est géré côté **Supabase** (dashboard ou `supabase db push`).
> L'application ne porte aucun DDL ni outil de migration (pas d'Alembic).
> Les repositories ne font que du DML (SELECT, INSERT, UPDATE, DELETE).

### Pool factory

```python
async def create_pool() -> asyncpg.Pool:
    settings = get_settings()

    async def _init_connection(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    return await asyncpg.create_pool(
        dsn=settings.database_url.get_secret_value(),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        statement_cache_size=0,    # requis avec pgbouncer/Supabase
        init=_init_connection,
    )
```

### Repository pattern

```python
class TrackRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_id(self, track_id: UUID) -> TrackRow | None:
        async with self._pool.acquire(timeout=10) as conn:
            return await conn.fetchrow(
                "SELECT id, title, artist, genre FROM tracks WHERE id = $1",
                track_id,
            )

    async def batch_update(self, items: list[tuple[UUID, str]]) -> int:
        async with self._pool.acquire(timeout=10) as conn, conn.transaction():
            for item_id, value in items:
                await conn.execute("UPDATE tracks SET genre = $1 WHERE id = $2", value, item_id)
        return len(items)
```

**Règles :**
- SQL brut (pas d'ORM). Requêtes paramétrées ($1, $2…).
- Retour typé en `TypedDict` ou `TypedDict | None`.
- Toujours `acquire(timeout=10)` pour éviter les deadlocks.
- Transactions explicites pour les écritures multiples.
- Protection injection SQL : allowlist pour les colonnes dynamiques.

```python
_UPDATABLE_COLUMNS = frozenset({"name", "status", "description"})

async def update_column(self, id: str, column: str, value: str) -> None:
    if column not in _UPDATABLE_COLUMNS:
        raise ValueError(f"Cannot update {column}")
    # ...
```

---

## 7. Services

Orchestrateurs légers — délèguent à repos + providers :

```python
class HostService:
    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._repo = HostRepository(pool)
        self._settings = settings

    async def create(self, data: HostCreate, user_id: str) -> HostResponse:
        template = get_template(data.template_id)
        if template is None:
            raise ValidationError(f"Unknown template: {data.template_id}")

        host_id = await self._repo.create(
            user_id=user_id,
            name=data.name,
            template_id=data.template_id,
        )

        row = await self._repo.get_by_id(host_id, user_id)
        if row is None:
            raise NotFoundError("Host")

        logger.info("host_created", host_id=host_id)
        return _row_to_response(row)
```

**Règles :**
- Un service ne fait **pas** de SQL directement.
- Un service ne connaît **pas** FastAPI (pas de Request, Response, Depends).
- Fonctions de conversion `_row_to_response()` en module-level, pas en méthode.

---

## 8. API / Routers

```python
from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/hosts", tags=["hosts"])

@router.post("/", response_model=HostResponse, status_code=status.HTTP_201_CREATED)
async def create_host(
    body: HostCreate,
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> HostResponse:
    service = HostService(pool, settings)
    return await service.create(body, user_id)
```

**Agrégation centrale :**

```python
# app/features/api.py
router = APIRouter()
router.include_router(auth_router)
router.include_router(hosts_router)
router.include_router(tracks_router)

# main.py
app.include_router(api_router, prefix="/api/v1")
```

**Règles :**
- Le router ne contient **pas** de logique métier.
- Les erreurs métier sont levées dans les services ; le router les laisse remonter.
- Rate limiting via décorateur `@limiter.limit("5/minute")`.

---

## 9. Injection de dépendances

```python
# app/core/deps/db.py
async def get_db_pool(request: Request) -> asyncpg.Pool:
    if not hasattr(request.app.state, "pool"):
        raise ServiceUnavailableError("Database not available")
    return request.app.state.pool

async def get_db_connection(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AsyncGenerator[asyncpg.Connection, None]:
    async with pool.acquire(timeout=10) as conn:
        yield conn

# app/core/security.py
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    if credentials is None:
        raise AuthenticationError("Bearer auth required")
    return _extract_user_id(credentials.credentials, settings)
```

**Règles :**
- Les ressources partagées vivent dans `app.state` (initialisées dans `lifespan`).
- Les deps FastAPI sont de simples fonctions, pas des classes.
- En test, on override via `app.dependency_overrides[dep_fn] = lambda: mock`.

---

## 10. Gestion d'erreurs

### Hiérarchie custom

```python
class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code

class NotFoundError(AppError):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found", status_code=404)

class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)

class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, status_code=401)

class ForbiddenError(AppError): ...
class ConflictError(AppError): ...
class ServiceUnavailableError(AppError): ...
```

### Handler global

```python
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
```

**Règles :**
- Toujours `raise XxxError(...)` — jamais return d'un dict d'erreur.
- Chaîner les exceptions : `raise ValidationError("...") from e`.
- Pas de try/except générique sauf au niveau handler.

---

## 11. Logging structuré

```python
import structlog

logger = structlog.get_logger(__name__)

# Événement + contexte clé-valeur
logger.info("host_created", host_id=host_id, template=template_id)
logger.warning("pool_creation_failed", error=str(exc))
logger.exception("unexpected_error", exc_info=exc)
logger.debug("cache_hit", key=cache_key)
```

**Règles :**
- Event name en `snake_case` (premier argument).
- Contexte en keyword arguments (pas de f-string).
- Un `RequestIDMiddleware` injecte `request_id` dans chaque log.
- `logger = structlog.get_logger(__name__)` en module-level.

---

## 12. Registry & Factory

### Registry générique (avec generics)

```python
class ProviderRegistry[T]:
    def __init__(self, provider_type: str) -> None:
        self._provider_type = provider_type
        self._providers: dict[str, type[T]] = {}

    def register(self, name: str, adapter_class: type[T]) -> None:
        self._providers[name.lower()] = adapter_class

    def create(self, name: str, **kwargs: object) -> T:
        adapter_class = self._providers.get(name.lower())
        if not adapter_class:
            raise ProviderNotFoundError(self._provider_type, name, list(self._providers))
        return adapter_class(**kwargs)

# Instanciation
llm_registry: ProviderRegistry[LLMAdapter] = ProviderRegistry("LLM")
llm_registry.register("mistral", MistralLLMAdapter)
llm_registry.register("openai", OpenAILLMAdapter)
```

### Factory functions

```python
def create_llm() -> LLMAdapter | None:
    settings = get_settings()
    if settings.mistral_api_key:
        return llm_registry.create(
            settings.llm_provider,
            api_key=settings.mistral_api_key.get_secret_value(),
        )
    return None
```

**Règles :**
- Les registries sont des singletons module-level.
- Les enregistrements se font au chargement du module.
- Les factories retournent `T | None` quand la config est absente.

---

## 13. Protocols & Adapters

### Protocol (interface abstraite, duck-typed)

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class TTSAdapter(Protocol):
    @property
    def is_configured(self) -> bool: ...

    @property
    def supports_long_input(self) -> bool: ...

    async def synthesize(self, text: str, voice_id: str) -> bytes: ...

    async def register_voice(self, name: str, wav_bytes: bytes) -> bool: ...
```

### Adapter concret (pas d'héritage, juste conformité structurelle)

```python
class ElevenLabsTTSAdapter:
    """Conforme à TTSAdapter par duck typing."""

    def __init__(self, api_key: str, default_model: str = "eleven_turbo_v2") -> None:
        self._client = AsyncElevenLabs(api_key=api_key)
        self._default_model = default_model

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def supports_long_input(self) -> bool:
        return True

    async def synthesize(self, text: str, voice_id: str) -> bytes:
        audio = await self._client.generate(text=text, voice=voice_id, model=self._default_model)
        return b"".join([chunk async for chunk in audio])

    async def register_voice(self, name: str, wav_bytes: bytes) -> bool:
        # ...
```

**Règles :**
- Pas d'héritage — le Protocol est vérifié par mypy structurellement.
- `@runtime_checkable` si besoin de `isinstance()` au runtime.
- Un adapter = un provider externe. Le code métier ne connaît que le Protocol.

---

## 14. Workers & tâches async

```python
# app/workers/arq_app.py
class WorkerCtx(TypedDict, total=False):
    pool: asyncpg.Pool

async def startup(ctx: WorkerCtx) -> None:
    ctx["pool"] = await create_pool()

async def shutdown(ctx: WorkerCtx) -> None:
    pool = ctx.get("pool")
    if pool:
        await pool.close()

# Lazy imports (seule exception autorisée) pour éviter les circulaires
def _get_avatar_task() -> ArqCoroutine:
    from app.features.hosts.services.avatar_service import generate_host_avatar
    return generate_host_avatar
```

**Règles :**
- Contexte worker typé en `TypedDict`.
- Lazy imports **uniquement** dans les workers.
- Startup/shutdown gèrent le lifecycle des ressources.

---

## 15. Tests

### Configuration pytest

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow-running tests",
]
filterwarnings = [
    "error",
    "ignore::pydantic.warnings.PydanticDeprecatedSince212",
    "ignore::ResourceWarning",
]
```

### Fixtures

```python
# tests/conftest.py

# ⚠️ Variables d'env AVANT tout import app
import os
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:54322/test"
os.environ["REDIS_URL"] = ""

from app.core.config import Settings, get_settings

@pytest.fixture(autouse=True)
def _override_settings() -> Generator[None, None, None]:
    """Reset le cache settings entre chaque test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

@pytest.fixture
def mock_db_pool() -> AsyncMock:
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value="OK")

    mock_pool = AsyncMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)
    mock_pool.acquire().__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire().__aexit__ = AsyncMock(return_value=None)
    return mock_pool

@pytest.fixture
async def async_client(mock_db_pool) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db_pool] = lambda: mock_db_pool
    try:
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client
    finally:
        app.dependency_overrides.clear()
```

### Organisation des tests

```python
# Tests unitaires simples
@pytest.mark.unit
async def test_health_returns_200(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

# Tests groupés par classe
class TestHostRepository:
    @pytest.fixture
    def repo(self, mock_db_pool: AsyncMock) -> HostRepository:
        return HostRepository(mock_db_pool)

    async def test_get_by_id_returns_host(self, repo: HostRepository) -> None:
        # ...

    async def test_get_by_id_returns_none_when_missing(self, repo: HostRepository) -> None:
        # ...
```

**Règles :**
- Markers systématiques : `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`.
- `asyncio_mode = "auto"` — pas besoin de `@pytest.mark.asyncio`.
- Isolation : `dependency_overrides` pour mocker le DI FastAPI.
- `get_settings.cache_clear()` en `autouse` fixture.
- Nommage : `test_<action>_<condition>` (ex: `test_get_by_id_returns_none_when_missing`).

---

## 16. Clean code

### Taille & structure

- **Fonctions < 30 lignes.** Au-delà, extraire.
- **Fichiers < 400 lignes.** Au-delà, découper.
- **Guard clauses** en haut des fonctions (early return).
- **Keyword-only** pour 3+ paramètres : `def f(a: str, *, b: int, c: bool)`.

### Principes

- **SRP** — une fonction/classe = une responsabilité.
- **Dependency inversion** — dépendre de Protocols, pas d'implémentations.
- **Pas de code mort** — vulture pour détecter, supprimer immédiatement.
- **Pas de commentaires évidents** — le code est sa propre documentation.
- **Docstrings** uniquement sur les fonctions/classes publiques non triviales.

### Utilitaires

- Fonctions pures dans `core/*_utils.py`.
- Regex compilées en module-level (`re.compile(...)`).
- Pas d'abstraction prématurée — 3 lignes dupliquées > une abstraction inutile.

```python
# ✅ Regex compilées une seule fois
EMOJI_RE = re.compile(r"[\U0001f600-\U0001f64f]", re.UNICODE)
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

def strip_emojis(text: str) -> str:
    return EMOJI_RE.sub("", text)
```

---

## 17. Linting & qualité

### Ruff

```toml
[tool.ruff]
target-version = "py312"
line-length = 99

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort (tri des imports)
    "UP",     # pyupgrade (syntaxe moderne)
    "B",      # bugbear (pièges courants)
    "SIM",    # simplify (simplifications)
    "RUF",    # ruff-specific
    "ASYNC",  # async best practices
]
ignore = [
    "B008",      # Depends() en default — pattern FastAPI standard
    "RUF005",    # list concat vs unpacking — les deux sont lisibles
    "RUF006",    # create_task sans ref — fire-and-forget intentionnel
    "ASYNC240",  # pathlib en async — ok avec uvicorn (pas trio)
]
```

### MyPy

```toml
[tool.mypy]
python_version = "3.12"
strict = true
```

### Vulture

Détection de code mort. Lancer régulièrement :

```bash
vulture app/ --min-confidence 80
```

Supprimer le code détecté, sauf les faux positifs (entry points, handlers dynamiques) documentés dans un whitelist.

### Commandes qualité

```bash
# Lint + fix
ruff check . --fix
ruff format .

# Type check
mypy app/

# Code mort
vulture app/ --min-confidence 80

# Tests
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

---

## Récapitulatif rapide

| Principe | Règle |
|----------|-------|
| **Typage** | Strict, `X \| None`, `list[str]`, TypedDict/StrEnum/dataclass |
| **Imports** | Top-level, absolus, pas de `TYPE_CHECKING` |
| **Config** | Pydantic BaseSettings + `@cache` |
| **Data access** | Repository pattern + TypedDict, SQL brut paramétré |
| **Services** | Orchestrateurs légers, pas de SQL, pas de HTTP |
| **API** | Router mince, Depends pour DI, pas de logique |
| **Erreurs** | Hiérarchie custom `AppError`, handler global |
| **Logging** | structlog, event snake_case, contexte en kwargs |
| **Extensibilité** | Protocol + Registry + Factory |
| **Tests** | pytest async, markers, dependency_overrides |
| **Qualité** | ruff + mypy strict + vulture |
| **Clean code** | < 30 lignes/fn, < 400 lignes/fichier, SOLID, guard clauses |
