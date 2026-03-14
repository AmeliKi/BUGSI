import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_service import log_action


@pytest.mark.asyncio
async def test_admin_can_list_audit_logs(client: AsyncClient, admin_user, admin_token, db_session: AsyncSession):
    await log_action(db_session, "create", "user", resource_id=str(uuid.uuid4()), actor_id=admin_user.id, actor_email=admin_user.email)
    await db_session.commit()

    resp = await client.get("/api/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["action"] == "create"
    assert data[0]["resource_type"] == "user"
    assert "X-Total-Count" in resp.headers


@pytest.mark.asyncio
async def test_regular_user_cannot_list_audit_logs(client: AsyncClient, regular_user, user_token):
    resp = await client.get("/api/audit-logs", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_logs_pagination(client: AsyncClient, admin_user, admin_token, db_session: AsyncSession):
    for i in range(5):
        await log_action(db_session, "create", "device", resource_id=str(uuid.uuid4()), actor_id=admin_user.id, actor_email=admin_user.email)
    await db_session.commit()

    resp = await client.get("/api/audit-logs?limit=2&offset=0", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert int(resp.headers["X-Total-Count"]) >= 5


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(client: AsyncClient, admin_user, admin_token, db_session: AsyncSession):
    await log_action(db_session, "create", "user", actor_id=admin_user.id, actor_email=admin_user.email)
    await log_action(db_session, "deactivate", "device", actor_id=admin_user.id, actor_email=admin_user.email)
    await db_session.commit()

    resp = await client.get("/api/audit-logs?action=deactivate", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(entry["action"] == "deactivate" for entry in data)


@pytest.mark.asyncio
async def test_audit_logs_filter_by_resource_type(client: AsyncClient, admin_user, admin_token, db_session: AsyncSession):
    await log_action(db_session, "create", "user", actor_id=admin_user.id, actor_email=admin_user.email)
    await log_action(db_session, "activate", "device", actor_id=admin_user.id, actor_email=admin_user.email)
    await db_session.commit()

    resp = await client.get("/api/audit-logs?resource_type=device", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(entry["resource_type"] == "device" for entry in data)


@pytest.mark.asyncio
async def test_unauthenticated_cannot_list_audit_logs(client: AsyncClient):
    resp = await client.get("/api/audit-logs")
    assert resp.status_code == 401
