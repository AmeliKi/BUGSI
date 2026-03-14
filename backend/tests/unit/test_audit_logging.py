import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.audit_service import log_action


@pytest.mark.asyncio
class TestAuditLogging:
    async def test_log_action_creates_entry(self, db_session: AsyncSession):
        actor_id = uuid.uuid4()
        await log_action(
            db_session,
            action="create",
            resource_type="user",
            resource_id=str(uuid.uuid4()),
            actor_id=actor_id,
            actor_email="admin@test.local",
        )

        result = await db_session.execute(select(AuditLog))
        entry = result.scalar_one()

        assert entry.action == "create"
        assert entry.resource_type == "user"
        assert entry.actor_id == actor_id
        assert entry.actor_email == "admin@test.local"
        assert entry.resource_id is not None
        assert entry.created_at is not None

    async def test_log_action_all_fields(self, db_session: AsyncSession):
        actor_id = uuid.uuid4()
        resource_id = str(uuid.uuid4())
        details = {"reason": "scheduled maintenance", "version": "1.2.3"}

        await log_action(
            db_session,
            action="deploy",
            resource_type="ota_deployment",
            resource_id=resource_id,
            actor_id=actor_id,
            actor_email="ops@test.local",
            details=details,
        )

        result = await db_session.execute(select(AuditLog))
        entry = result.scalar_one()

        assert entry.action == "deploy"
        assert entry.resource_type == "ota_deployment"
        assert entry.resource_id == resource_id
        assert entry.actor_id == actor_id
        assert entry.actor_email == "ops@test.local"
        assert json.loads(entry.details) == details
        assert entry.id is not None
        assert entry.created_at is not None

    async def test_log_action_minimal_fields(self, db_session: AsyncSession):
        await log_action(
            db_session,
            action="cleanup",
            resource_type="system",
        )

        result = await db_session.execute(select(AuditLog))
        entry = result.scalar_one()

        assert entry.action == "cleanup"
        assert entry.resource_type == "system"
        assert entry.actor_id is None
        assert entry.actor_email is None
        assert entry.resource_id is None
        assert entry.details is None
        assert entry.id is not None
        assert entry.created_at is not None
