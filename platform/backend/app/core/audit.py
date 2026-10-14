from prisma import Json

from .db import db


async def audit(actor_id: str | None, action: str, entity: str, entity_id: str, diff: dict | None = None) -> None:
    data: dict = {"action": action, "entity": entity, "entityId": entity_id}
    if actor_id:
        data["actor"] = {"connect": {"id": actor_id}}
    if diff is not None:
        data["diff"] = Json(diff)
    await db.auditlog.create(data=data)
