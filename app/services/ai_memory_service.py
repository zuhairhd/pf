"""AI Memory service for durable, privacy-safe user preferences and context.

Memories are tenant-scoped and user-scoped. The service enforces a safety
policy that rejects secrets, raw account numbers, and other sensitive values.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIMemory, AIMemorySource, AIMemoryType, User


class MemorySafetyError(Exception):
    """Raised when a memory value violates the safety policy."""

    def __init__(self, message: str = "Memory value violates safety policy"):
        self.message = message
        super().__init__(self.message)


class AIMemoryService:
    """Manage durable AI memories for a tenant/user."""

    # Values that should never be stored as memory.
    BLOCKED_KEYWORDS = [
        "password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "otp",
        "ssn",
        "national id",
        "passport",
        "iban",
        "swift",
        "routing number",
        "account number",
        "card number",
        "credit card",
        "debit card",
        "cvv",
        "pin",
    ]

    # Patterns that look like sensitive numeric values.
    SENSITIVE_NUMBER_PATTERNS = [
        re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),  # card-like
        re.compile(r"\b\d{8,}\b"),  # long account/ID numbers
    ]

    def __init__(self, db: AsyncSession, tenant_id: int, user_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _sanitize_value(self, value: str) -> str:
        """Validate and sanitize a memory value.

        Raises MemorySafetyError if the value looks like a secret or sensitive
        personal identifier.
        """
        if not value or not value.strip():
            raise MemorySafetyError("Memory value cannot be empty.")

        lower = value.lower()
        for keyword in self.BLOCKED_KEYWORDS:
            if keyword in lower:
                raise MemorySafetyError(
                    f"Memory cannot contain sensitive keywords such as '{keyword}'."
                )

        for pattern in self.SENSITIVE_NUMBER_PATTERNS:
            if pattern.search(value):
                raise MemorySafetyError(
                    "Memory cannot contain account numbers, card numbers, or similar sensitive numeric values."
                )

        return value.strip()

    @staticmethod
    def _derive_key(value: str) -> str:
        """Derive a stable key from an explicit 'remember that' statement."""
        normalized = re.sub(r"[^a-z0-9\s]", "", value.lower()).strip()
        words = normalized.split()[:8]
        if words:
            key = "_".join(words)[:100]
        else:
            key = "remembered"
        return key

    def _classify_memory_type(self, value: str) -> AIMemoryType:
        """Infer a memory type from value text for explicit statements."""
        lower = value.lower()
        if "dismiss" in lower or "ignore" in lower:
            return AIMemoryType.DISMISSED_ADVICE
        if "goal" in lower or "saving for" in lower:
            return AIMemoryType.GOAL_CONTEXT
        if "risk" in lower or "conservative" in lower or "aggressive" in lower:
            return AIMemoryType.RISK_PROFILE
        if "prefer" in lower or "language" in lower or "monthly summary" in lower:
            return AIMemoryType.PREFERENCE
        return AIMemoryType.CUSTOM

    async def create_memory(
        self,
        *,
        memory_type: AIMemoryType,
        key: str,
        value: str,
        summary: Optional[str] = None,
        source: AIMemorySource = AIMemorySource.EXPLICIT_USER_STATEMENT,
        confidence_score: Optional[Decimal] = None,
        is_sensitive: bool = False,
        expires_at: Optional[datetime] = None,
    ) -> AIMemory:
        """Create or update a memory for the current tenant/user."""
        value = self._sanitize_value(value)
        key = key.strip()[:100]
        if summary:
            summary = summary.strip()[:255]

        # Duplicate prevention: same tenant/user/type/key updates existing memory.
        existing = await self.db.execute(
            select(AIMemory)
            .where(AIMemory.tenant_id == self.tenant_id)
            .where(AIMemory.user_id == self.user_id)
            .where(AIMemory.memory_type == memory_type)
            .where(AIMemory.key == key)
            .where(AIMemory.is_active == True)
        )
        memory = existing.scalar_one_or_none()

        if memory:
            memory.value = value
            memory.summary = summary
            memory.source = source
            memory.confidence_score = confidence_score
            memory.is_sensitive = is_sensitive
            memory.expires_at = expires_at
            memory.is_active = True
            memory.deleted_at = None
        else:
            memory = AIMemory(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                memory_type=memory_type,
                key=key,
                value=value,
                summary=summary,
                source=source,
                confidence_score=confidence_score,
                is_sensitive=is_sensitive,
                expires_at=expires_at,
                is_active=True,
            )
            self.db.add(memory)

        await self.db.flush()
        await self.db.refresh(memory)
        return memory

    async def create_memory_from_explicit_statement(self, statement: str) -> AIMemory:
        """Create a memory from an explicit 'remember that ...' statement."""
        value = statement.strip()
        memory_type = self._classify_memory_type(value)
        key = self._derive_key(value)
        return await self.create_memory(
            memory_type=memory_type,
            key=key,
            value=value,
            source=AIMemorySource.EXPLICIT_USER_STATEMENT,
            confidence_score=Decimal("0.95"),
        )

    async def get_memory(self, memory_id: int) -> Optional[AIMemory]:
        """Get a single memory scoped to tenant/user."""
        result = await self.db.execute(
            select(AIMemory)
            .where(AIMemory.id == memory_id)
            .where(AIMemory.tenant_id == self.tenant_id)
            .where(AIMemory.user_id == self.user_id)
        )
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        *,
        active_only: bool = True,
        memory_type: Optional[AIMemoryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AIMemory]:
        """List memories for the current tenant/user."""
        query = (
            select(AIMemory)
            .where(AIMemory.tenant_id == self.tenant_id)
            .where(AIMemory.user_id == self.user_id)
        )
        if active_only:
            now = datetime.utcnow()
            query = query.where(
                AIMemory.is_active == True,
                (AIMemory.expires_at == None) | (AIMemory.expires_at > now),
                AIMemory.deleted_at == None,
            )
        if memory_type:
            query = query.where(AIMemory.memory_type == memory_type)
        query = (
            query.order_by(AIMemory.last_used_at.desc().nullslast(), AIMemory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_memory(
        self,
        memory_id: int,
        *,
        value: Optional[str] = None,
        summary: Optional[str] = None,
        memory_type: Optional[AIMemoryType] = None,
        is_active: Optional[bool] = None,
        is_sensitive: Optional[bool] = None,
        expires_at: Optional[datetime] = None,
        confidence_score: Optional[Decimal] = None,
    ) -> Optional[AIMemory]:
        """Update a memory scoped to tenant/user."""
        memory = await self.get_memory(memory_id)
        if memory is None:
            return None

        if value is not None:
            memory.value = self._sanitize_value(value)
        if summary is not None:
            memory.summary = summary.strip()[:255] if summary.strip() else None
        if memory_type is not None:
            memory.memory_type = memory_type
        if is_active is not None:
            memory.is_active = is_active
            if not is_active and memory.deleted_at is None:
                memory.deleted_at = datetime.utcnow()
            elif is_active:
                memory.deleted_at = None
        if is_sensitive is not None:
            memory.is_sensitive = is_sensitive
        if expires_at is not None:
            memory.expires_at = expires_at
        if confidence_score is not None:
            memory.confidence_score = confidence_score

        await self.db.flush()
        await self.db.refresh(memory)
        return memory

    async def forget_memory(self, memory_id: int) -> bool:
        """Soft-delete/deactivate a memory."""
        memory = await self.update_memory(memory_id, is_active=False)
        return memory is not None

    async def forget_by_query(self, query: str) -> int:
        """Deactivate memories whose key or value matches the query string."""
        pattern = f"%{query}%"
        result = await self.db.execute(
            select(AIMemory)
            .where(AIMemory.tenant_id == self.tenant_id)
            .where(AIMemory.user_id == self.user_id)
            .where(AIMemory.is_active == True)
            .where(
                (AIMemory.key.ilike(pattern)) | (AIMemory.value.ilike(pattern))
            )
        )
        memories = result.scalars().all()
        now = datetime.utcnow()
        for memory in memories:
            memory.is_active = False
            memory.deleted_at = now
        await self.db.flush()
        return len(memories)

    async def search_memories(self, query: str, *, limit: int = 20) -> list[AIMemory]:
        """Search active memories by key/value substring."""
        pattern = f"%{query}%"
        now = datetime.utcnow()
        result = await self.db.execute(
            select(AIMemory)
            .where(AIMemory.tenant_id == self.tenant_id)
            .where(AIMemory.user_id == self.user_id)
            .where(AIMemory.is_active == True)
            .where(AIMemory.deleted_at == None)
            .where((AIMemory.expires_at == None) | (AIMemory.expires_at > now))
            .where(
                (AIMemory.key.ilike(pattern)) | (AIMemory.value.ilike(pattern))
            )
            .order_by(AIMemory.last_used_at.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def record_usage(self, memory_id: int) -> None:
        """Update last_used_at for a memory."""
        memory = await self.get_memory(memory_id)
        if memory:
            memory.last_used_at = datetime.utcnow()
            await self.db.flush()

    async def get_prompt_context(self, *, limit: int = 10) -> str:
        """Build a concise, sanitized memory context block for LLM prompts.

        Excludes sensitive memories and anything expired or inactive.
        """
        memories = await self.list_memories(active_only=True, limit=limit)
        lines = []
        for memory in memories:
            if memory.is_sensitive:
                continue
            text = memory.summary or memory.value
            lines.append(f"- {text}")
            memory.last_used_at = datetime.utcnow()
        if lines:
            await self.db.flush()
            return "Known user preferences and durable context:\n" + "\n".join(lines)
        return ""

    async def get_memory_summary(self) -> str:
        """Return a safe user-facing summary of active memories."""
        memories = await self.list_memories(active_only=True, limit=50)
        if not memories:
            return "I don't have any saved preferences or context about you yet."
        lines = []
        for memory in memories:
            if memory.is_sensitive:
                continue
            text = memory.summary or memory.value
            lines.append(f"- {text}")
        return "Here is what I remember about you:\n" + "\n".join(lines)

    def extract_memory_command(self, message: str) -> dict[str, Any]:
        """Detect explicit remember/forget commands in a chat message.

        Returns a dict with 'command' (remember/forget/query/none) and 'content'.
        """
        lower = message.lower().strip()

        remember_prefixes = [
            "remember that ",
            "please remember that ",
            "remember ",
            "please remember ",
        ]
        for prefix in remember_prefixes:
            if lower.startswith(prefix):
                content = message[len(prefix):].strip()
                return {"command": "remember", "content": content}

        forget_prefixes = [
            "forget that ",
            "please forget that ",
            "forget ",
            "please forget ",
        ]
        for prefix in forget_prefixes:
            if lower.startswith(prefix):
                content = message[len(prefix):].strip()
                return {"command": "forget", "content": content}

        query_patterns = [
            "what do you remember about me",
            "what do you remember",
            "tell me what you remember",
        ]
        for pattern in query_patterns:
            if pattern in lower:
                return {"command": "query", "content": ""}

        return {"command": "none", "content": message}
