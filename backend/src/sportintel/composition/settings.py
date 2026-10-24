"""API настроек (BE-T4.10): значения, JSON Schema для форм, default, аудит изменений."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from sportintel.modules.audit import public as audit
from sportintel.modules.identity import public as identity
from sportintel.platform import settings_store

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], route_class=identity.PermissionedRoute
)


class SettingItem(BaseModel):
    key: str
    value: dict[str, Any]
    schema_: dict[str, Any] = Field(alias="schema")
    default: dict[str, Any]
    updated_by: uuid.UUID | None
    updated_at: datetime | None

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class SettingList(BaseModel):
    items: list[SettingItem]


class SettingPut(BaseModel):
    value: dict[str, Any]


async def _item(uow: Any, key: str) -> SettingItem:
    schema = settings_store.schema_for(key)
    row = await settings_store.get_row(uow, key)
    default = settings_store.default_value(key)
    value = schema.model_validate({**default, **(row["value"] if row else {})}).model_dump(
        mode="json"
    )
    return SettingItem.model_validate(
        {
            "key": key,
            "value": value,
            "schema": schema.model_json_schema(),
            "default": default,
            "updated_by": row["updated_by"] if row else None,
            "updated_at": row["updated_at"] if row else None,
        }
    )


@router.get("", openapi_extra=identity.route_permission(P.SETTINGS_MANAGE))
async def list_settings(
    request: Request, _: Annotated[identity.CurrentUser, identity.require(P.SETTINGS_MANAGE)]
) -> SettingList:
    async with request.app.state.db.uow() as uow:
        return SettingList(
            items=[await _item(uow, k) for k in sorted(settings_store.SETTINGS_SCHEMAS)]
        )


@router.get("/{key}", openapi_extra=identity.route_permission(P.SETTINGS_MANAGE))
async def get_setting(
    key: str,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.SETTINGS_MANAGE)],
) -> SettingItem:
    async with request.app.state.db.uow() as uow:
        return await _item(uow, key)


@router.put("/{key}", openapi_extra=identity.route_permission(P.SETTINGS_MANAGE))
async def put_setting(
    key: str,
    body: SettingPut,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.SETTINGS_MANAGE)],
) -> SettingItem:
    state = request.app.state
    async with state.db.uow() as uow:
        before = (await settings_store.get_row(uow, key) or {}).get("value")
        model = await settings_store.put(uow, key, body.value, user.id, state.clock.now())
        b, a = audit.diff(before or {}, model.model_dump(mode="json"))
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.SETTINGS_UPDATED,
            target_type="settings",
            target_id=key,
            before=b,
            after=a,
        )
        return await _item(uow, key)
