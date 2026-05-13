"""Bot chat-session state — SessionManager, init() lifecycle, LRU eviction.

Carved out of ``bot/core.py`` per ADR 0001. The storage instances
(``transcript_store``, ``tool_result_store``) and configuration tunables
(``MAX_HISTORY``, ``MAX_CONVERSATIONS``, …) remain in ``bot.core`` because
they depend on ``OMICSCLAW_DIR`` at module-load time; this module
late-imports them inside ``init()`` and ``_evict_lru_conversations()`` to
avoid a load-order circular.

``init()`` writes the resolved provider config and the constructed LLM
client onto ``bot.core``'s module globals (``llm``, ``OMICSCLAW_MODEL``,
``LLM_PROVIDER_NAME``, ``memory_store``, ``session_manager``). External
tests read those attributes by ``bot.core.<name>`` — that contract is
preserved.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from omicsclaw.core.provider_registry import (
    PROVIDER_PRESETS,
    normalize_model_for_provider,
    resolve_provider,
)
from omicsclaw.core.provider_runtime import (
    provider_requires_api_key,
    set_active_provider_runtime,
)

logger = logging.getLogger("omicsclaw.bot.session")

# Files received from a chat surface, keyed by chat_id. Lives here per the
# bot/session module contract; ``omicsclaw/app/_attachments.py`` reaches it
# via ``bot.core.received_files``.
received_files: dict[int | str, dict] = {}


class SessionManager:
    """Manages user sessions with memory persistence."""

    def __init__(self, store):
        self.store = store

    async def get_or_create(self, user_id: str, platform: str, chat_id: str):
        """Get existing session or create new one."""
        session_id = f"{platform}:{user_id}:{chat_id}"
        session = await self.store.get_session(session_id)
        if not session:
            session = await self.store.create_session(user_id, platform, chat_id, session_id=session_id)
        else:
            await self.store.update_session(session_id, {"last_activity": datetime.now(timezone.utc)})
        return session

    async def load_context(self, session_id: str) -> str:
        """Load recent memories and format for LLM context."""
        try:
            datasets = []
            analyses = []
            prefs = []
            insights = []
            project_ctx = []

            try:
                datasets = await self.store.get_memories(session_id, "dataset", limit=2)
            except Exception as e:
                logger.warning(f"Failed to load dataset memories: {e}")

            try:
                analyses = await self.store.get_memories(session_id, "analysis", limit=3)
            except Exception as e:
                logger.warning(f"Failed to load analysis memories: {e}")

            try:
                prefs = await self.store.get_memories(session_id, "preference", limit=5)
            except Exception as e:
                logger.warning(f"Failed to load preference memories: {e}")

            try:
                insights = await self.store.get_memories(session_id, "insight", limit=3)
            except Exception as e:
                logger.warning(f"Failed to load insight memories: {e}")

            try:
                project_ctx = await self.store.get_memories(session_id, "project_context", limit=1)
            except Exception as e:
                logger.warning(f"Failed to load project context memories: {e}")

            parts = []

            if project_ctx:
                pc = project_ctx[0]
                ctx_parts = []
                if pc.project_goal:
                    ctx_parts.append(f"Goal: {pc.project_goal}")
                if pc.species:
                    ctx_parts.append(f"Species: {pc.species}")
                if pc.tissue_type:
                    ctx_parts.append(f"Tissue: {pc.tissue_type}")
                if pc.disease_model:
                    ctx_parts.append(f"Disease: {pc.disease_model}")
                if ctx_parts:
                    parts.append("**Project Context**: " + " | ".join(ctx_parts))

            if datasets:
                ds = datasets[0]
                parts.append(
                    f"**Current Dataset**: {ds.file_path} "
                    f"({ds.platform or 'unknown'}, {ds.n_obs or '?'} obs, "
                    f"preprocessed={ds.preprocessing_state})"
                )

            if analyses:
                parts.append("**Recent Analyses**:")
                for i, a in enumerate(analyses[:3], 1):
                    parts.append(f"{i}. {a.skill} ({a.method}) - {a.status}")

            if prefs:
                parts.append("**User Preferences**:")
                for p in prefs:
                    parts.append(f"- {p.key}: {p.value}")

            if insights:
                parts.append("**Known Insights**:")
                for ins in insights:
                    confidence = "confirmed" if ins.confidence == "user_confirmed" else "predicted"
                    parts.append(f"- {ins.entity_type} {ins.entity_id}: {ins.biological_label} ({confidence})")

            return "\n".join(parts) if parts else ""
        except Exception as e:
            logger.error(f"Failed to load memory context: {e}", exc_info=True)
            return ""


def init(
    api_key: str = "",
    base_url: str | None = None,
    model: str = "",
    provider: str = "",
    auth_mode: str = "api_key",
    ccproxy_port: int = 11435,
    strict_oauth: bool = True,
    allow_missing_credentials: bool = False,
):
    """Initialise the shared LLM client. Call once at startup.

    See ``bot.core`` re-export docstring for the full contract; behaviour
    is unchanged from the pre-decomposition implementation. Mutates
    ``bot.core``'s module globals (``llm``, ``OMICSCLAW_MODEL``,
    ``LLM_PROVIDER_NAME``, ``memory_store``, ``session_manager``) via a
    late import.
    """
    import bot.core as _core  # late import — _core fully loaded by call time

    auth_mode_normalized = str(auth_mode or "api_key").strip().lower() or "api_key"

    try:
        from omicsclaw.core.ccproxy_manager import clear_ccproxy_env
        clear_ccproxy_env()
    except Exception:
        pass

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider=provider,
        base_url=base_url or "",
        model=model,
        api_key=api_key,
    )
    if model and str(resolved_model).strip() != str(model).strip():
        _normalized_model, normalized_from_provider = normalize_model_for_provider(
            provider,
            model,
            base_url=base_url or "",
        )
        logger.warning(
            "Normalized stale model '%s' for provider '%s' to '%s' "
            "(matched default model of '%s')",
            model,
            provider,
            resolved_model,
            normalized_from_provider or "another provider",
        )
    _core.OMICSCLAW_MODEL = resolved_model

    if provider:
        _core.LLM_PROVIDER_NAME = provider
    elif resolved_url:
        for pname, (purl, _, _) in PROVIDER_PRESETS.items():
            if purl and resolved_url and purl.rstrip("/") in resolved_url.rstrip("/"):
                _core.LLM_PROVIDER_NAME = pname
                break
        else:
            _core.LLM_PROVIDER_NAME = "custom"
    else:
        _core.LLM_PROVIDER_NAME = "openai"

    effective_api_key = str(resolved_key or api_key or "")
    effective_base_url = str(resolved_url or "")

    if auth_mode_normalized == "oauth":
        from omicsclaw.core.ccproxy_manager import (
            OAUTH_PROVIDERS,
            maybe_start_ccproxy,
            provider_supports_oauth,
        )

        def _oauth_failed(reason: str) -> None:
            nonlocal auth_mode_normalized
            if strict_oauth:
                raise RuntimeError(reason)
            logger.warning(
                "Falling back to auth_mode='api_key' — %s. "
                "Set LLM_AUTH_MODE=api_key in your .env to silence this "
                "warning, or install / authenticate ccproxy.",
                reason,
            )
            auth_mode_normalized = "api_key"

        if not provider_supports_oauth(_core.LLM_PROVIDER_NAME):
            _oauth_failed(
                f"auth_mode='oauth' is not supported for provider "
                f"'{_core.LLM_PROVIDER_NAME}' (supported: "
                f"{sorted(OAUTH_PROVIDERS.keys())})"
            )
        else:
            try:
                maybe_start_ccproxy(
                    anthropic_oauth=(_core.LLM_PROVIDER_NAME == "anthropic"),
                    openai_oauth=(_core.LLM_PROVIDER_NAME == "openai"),
                    port=int(ccproxy_port),
                )
            except RuntimeError as exc:
                _oauth_failed(str(exc))

    runtime = set_active_provider_runtime(
        provider=_core.LLM_PROVIDER_NAME,
        base_url=effective_base_url,
        model=_core.OMICSCLAW_MODEL,
        api_key=effective_api_key,
        auth_mode=auth_mode_normalized,
        ccproxy_port=int(ccproxy_port),
    )

    effective_api_key = runtime.api_key or effective_api_key
    effective_base_url = runtime.base_url or effective_base_url

    kw: dict = {"api_key": effective_api_key}
    if effective_base_url:
        kw["base_url"] = effective_base_url
    kw["timeout"] = _core._build_llm_timeout()
    missing_required_key = (
        not effective_api_key and provider_requires_api_key(_core.LLM_PROVIDER_NAME)
    )
    if allow_missing_credentials and missing_required_key:
        _core.llm = None
        logger.warning(
            "LLM client not initialised because no credentials are "
            "configured yet: provider=%s model=%s. The app-server remains "
            "available so the frontend can finish provider setup.",
            _core.LLM_PROVIDER_NAME,
            _core.OMICSCLAW_MODEL,
        )
    else:
        try:
            _core.llm = _core.AsyncOpenAI(**kw)
        except _core.OpenAIError as exc:
            if allow_missing_credentials and "missing credentials" in str(exc).lower():
                _core.llm = None
                logger.warning(
                    "LLM client not initialised because no credentials are "
                    "configured yet: provider=%s model=%s. The app-server remains "
                    "available so the frontend can finish provider setup.",
                    _core.LLM_PROVIDER_NAME,
                    _core.OMICSCLAW_MODEL,
                )
            else:
                raise
        except ImportError as exc:
            if "socksio" in str(exc) or "socks" in str(exc).lower():
                raise ImportError(
                    "A SOCKS proxy is configured (HTTPS_PROXY / ALL_PROXY) but "
                    "the 'socksio' package is not installed. Run:\n\n"
                    '  pip install "httpx[socks]"\n\n'
                    "then restart the backend."
                ) from exc
            raise

    if _core.llm is not None:
        logger.info(
            f"LLM initialised: provider={_core.LLM_PROVIDER_NAME}, "
            f"model={_core.OMICSCLAW_MODEL}, base_url={effective_base_url or '(default)'}, "
            f"auth_mode={auth_mode_normalized}"
        )

    _core.memory_store = None
    _core.session_manager = None
    if os.getenv("OMICSCLAW_MEMORY_ENABLED", "true").lower() not in ("false", "0", "no"):
        try:
            from omicsclaw.memory.compat import CompatMemoryStore
            from omicsclaw.memory.database import DatabaseManager as _DatabaseManager
            from omicsclaw.memory.search import SearchIndexer as _SearchIndexer
            from omicsclaw.memory.glossary import GlossaryService as _GlossaryService

            del _DatabaseManager, _SearchIndexer, _GlossaryService

            db_url = os.getenv("OMICSCLAW_MEMORY_DB_URL")

            store = CompatMemoryStore(
                database_url=db_url,
            )

            _core.memory_store = store
            _core.session_manager = SessionManager(store)
            logger.info("Graph memory system initialized (omicsclaw.memory)")
        except ImportError:
            logger.warning("Memory dependencies not installed, skipping memory init")
        except Exception as e:
            logger.error(f"Memory init failed: {e}")


def _evict_lru_conversations():
    """Evict least-recently-used conversations when the conversation cap is
    exceeded. Late-imports ``transcript_store`` / ``tool_result_store`` /
    ``MAX_CONVERSATIONS`` from ``bot.core`` since those globals live there."""
    from bot.core import MAX_CONVERSATIONS, tool_result_store, transcript_store

    transcript_store.max_conversations = MAX_CONVERSATIONS
    evicted = transcript_store.evict_lru_conversations()
    for chat_id in evicted:
        tool_result_store.clear(chat_id)
    if evicted:
        logger.debug(f"Evicted {len(evicted)} stale conversation(s)")
