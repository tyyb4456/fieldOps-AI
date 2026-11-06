from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment import Equipment
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)


def equipment_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "manufacturer": "Acme Solar",
        "model": "INV-5000",
        "serial_number": f"SN-{uuid.uuid4().hex[:10]}",
        "equipment_type": "solar_inverter",
        "installation_date": "2025-06-01",
    }
    payload.update(overrides)
    return payload


async def test_equipment_endpoints_require_authentication(api_client) -> None:
    response = await api_client.get("/api/v1/customers/me/equipment")

    assert response.status_code == 401


async def test_customer_can_create_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    payload = equipment_payload()

    response = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=bearer(token),
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == str(customer.id)
    assert body["manufacturer"] == payload["manufacturer"]
    assert body["serial_number"] == payload["serial_number"]

    count = await migrated_db_session.scalar(
        select(func.count(Equipment.id)).where(
            Equipment.customer_id == customer.id
        )
    )
    assert count == 1


async def test_customer_cannot_spoof_equipment_ownership(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    _, other_customer, _ = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=bearer(token),
        json=equipment_payload(customer_id=str(other_customer.id)),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_customer_lists_only_own_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer_a, token_a = await seed_customer(migrated_db_session)
    _, customer_b, _ = await seed_customer(migrated_db_session)
    own = await seed_equipment(migrated_db_session, customer_a)
    await seed_equipment(migrated_db_session, customer_b)

    response = await api_client.get(
        "/api/v1/customers/me/equipment",
        headers=bearer(token_a),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(own.id)]


async def test_customer_can_filter_equipment_by_type(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    inverter = await seed_equipment(
        migrated_db_session,
        customer,
        equipment_type="solar_inverter",
    )
    await seed_equipment(
        migrated_db_session,
        customer,
        equipment_type="battery",
    )

    response = await api_client.get(
        "/api/v1/customers/me/equipment?equipment_type=solar_inverter",
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(inverter.id)


async def test_customer_can_read_own_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)

    response = await api_client.get(
        f"/api/v1/customers/me/equipment/{equipment.id}",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(equipment.id)


async def test_customer_cannot_read_another_customers_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_equipment = await seed_equipment(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/me/equipment/{other_equipment.id}",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customer_can_update_own_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)

    response = await api_client.patch(
        f"/api/v1/customers/me/equipment/{equipment.id}",
        headers=bearer(token),
        json={"model": "INV-6000"},
    )

    assert response.status_code == 200
    assert response.json()["model"] == "INV-6000"


async def test_customer_cannot_update_another_customers_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_equipment = await seed_equipment(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.patch(
        f"/api/v1/customers/me/equipment/{other_equipment.id}",
        headers=bearer(token),
        json={"model": "INV-6000"},
    )

    assert response.status_code == 404


async def test_customer_cannot_transfer_equipment_ownership(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    _, other_customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)

    response = await api_client.patch(
        f"/api/v1/customers/me/equipment/{equipment.id}",
        headers=bearer(token),
        json={"customer_id": str(other_customer.id)},
    )

    assert response.status_code == 422


async def test_customer_can_delete_own_unreferenced_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)

    response = await api_client.delete(
        f"/api/v1/customers/me/equipment/{equipment.id}",
        headers=bearer(token),
    )

    assert response.status_code == 204
    remaining = await migrated_db_session.scalar(
        select(Equipment.id).where(Equipment.id == equipment.id)
    )
    assert remaining is None


async def test_customer_cannot_delete_another_customers_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_equipment = await seed_equipment(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.delete(
        f"/api/v1/customers/me/equipment/{other_equipment.id}",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert (
        await migrated_db_session.get(Equipment, other_equipment.id)
        is not None
    )


async def test_equipment_with_complaint_cannot_be_deleted(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
    )

    response = await api_client.delete(
        f"/api/v1/customers/me/equipment/{equipment.id}",
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "equipment_in_use"
    assert await migrated_db_session.get(Equipment, equipment.id) is not None


async def test_technician_cannot_manage_customer_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    _, _, token = await seed_technician(migrated_db_session)
    headers = bearer(token)

    assert (
        await api_client.get(
            "/api/v1/customers/me/equipment",
            headers=headers,
        )
    ).status_code == 403
    assert (
        await api_client.post(
            "/api/v1/customers/me/equipment",
            headers=headers,
            json=equipment_payload(),
        )
    ).status_code == 403
    assert (
        await api_client.get(
            f"/api/v1/customers/me/equipment/{equipment.id}",
            headers=headers,
        )
    ).status_code == 403


async def test_invalid_equipment_fields_are_rejected(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)
    future = (date.today() + timedelta(days=1)).isoformat()

    invalid_payloads = [
        equipment_payload(manufacturer="   "),
        equipment_payload(model=""),
        equipment_payload(equipment_type=""),
        equipment_payload(serial_number="x" * 151),
        equipment_payload(installation_date=future),
        equipment_payload(installation_date="not-a-date"),
    ]

    for payload in invalid_payloads:
        response = await api_client.post(
            "/api/v1/customers/me/equipment",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422, payload


async def test_duplicate_serial_number_policy_follows_database_constraint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)
    serial = "SERIAL-DUPLICATE-1"

    first = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=headers,
        json=equipment_payload(
            manufacturer="Acme",
            serial_number=serial,
        ),
    )
    duplicate = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=headers,
        json=equipment_payload(
            manufacturer="Acme",
            serial_number=serial,
        ),
    )
    different_manufacturer = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=headers,
        json=equipment_payload(
            manufacturer="Other Manufacturer",
            serial_number=serial,
        ),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "equipment_conflict"
    assert different_manufacturer.status_code == 201


async def test_null_equipment_serials_are_allowed(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)

    first = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=headers,
        json=equipment_payload(serial_number=None),
    )
    second = await api_client.post(
        "/api/v1/customers/me/equipment",
        headers=headers,
        json=equipment_payload(serial_number=None),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["serial_number"] is None


async def test_equipment_pagination_is_bounded(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)

    too_large = await api_client.get(
        "/api/v1/customers/me/equipment?limit=101",
        headers=headers,
    )
    negative_offset = await api_client.get(
        "/api/v1/customers/me/equipment?offset=-1",
        headers=headers,
    )

    assert too_large.status_code == 422
    assert negative_offset.status_code == 422


async def test_customer_cannot_use_admin_equipment_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        "/api/v1/admin/equipment",
        headers=bearer(token),
    )

    assert response.status_code == 403


async def test_admin_can_manage_any_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    _, other_customer, _ = await seed_customer(migrated_db_session)
    own = await seed_equipment(migrated_db_session, customer)
    await seed_equipment(migrated_db_session, other_customer)
    _, admin_token = await seed_admin(migrated_db_session)
    headers = bearer(admin_token)

    listing = await api_client.get(
        "/api/v1/admin/equipment",
        headers=headers,
    )
    detail = await api_client.get(
        f"/api/v1/admin/equipment/{own.id}",
        headers=headers,
    )
    created = await api_client.post(
        f"/api/v1/admin/customers/{customer.id}/equipment",
        headers=headers,
        json=equipment_payload(),
    )
    updated = await api_client.patch(
        f"/api/v1/admin/equipment/{own.id}",
        headers=headers,
        json={"model": "INV-7000"},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert detail.status_code == 200
    assert created.status_code == 201
    assert created.json()["customer_id"] == str(customer.id)
    assert updated.status_code == 200
    assert updated.json()["model"] == "INV-7000"


async def test_admin_delete_respects_integrity_constraints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    referenced = await seed_equipment(migrated_db_session, customer)
    unreferenced = await seed_equipment(migrated_db_session, customer)
    await seed_complaint(
        migrated_db_session,
        customer,
        equipment=referenced,
    )
    _, admin_token = await seed_admin(migrated_db_session)
    headers = bearer(admin_token)

    blocked = await api_client.delete(
        f"/api/v1/admin/equipment/{referenced.id}",
        headers=headers,
    )
    allowed = await api_client.delete(
        f"/api/v1/admin/equipment/{unreferenced.id}",
        headers=headers,
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "equipment_in_use"
    assert allowed.status_code == 204
    assert (
        await migrated_db_session.scalar(
            select(Equipment.id).where(
                Equipment.id == unreferenced.id
            )
        )
        is None
    )
