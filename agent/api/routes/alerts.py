import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from db import queries

logger = logging.getLogger("syswatcher.api.alerts")
router = APIRouter()

class CreateAlertRequest(BaseModel):
    metric:       str
    condition:    str               # gt | lt | eq
    threshold:    float
    severity:     str               # warn | critical
    server_name:  str  = None
    notify_slack: bool = False
    notify_email: bool = False
    description:  str  = ""

@router.get("")
async def list_alerts(
    server_name: str = Query(None, description="Filter by server"),
):
    try:
        rules = await queries.get_alert_rules(server_name=server_name)
        return {"rules": rules, "count": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_alert(req: CreateAlertRequest):
    valid_conditions = {"gt", "lt", "eq"}
    valid_severities = {"warn", "critical"}

    if req.condition not in valid_conditions:
        raise HTTPException(
            status_code=400,
            detail=f"condition must be one of: {valid_conditions}",
        )
    if req.severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"severity must be one of: {valid_severities}",
        )

    try:
        rule_id = await queries.insert_alert_rule(
            metric=req.metric,
            condition=req.condition,
            threshold=req.threshold,
            severity=req.severity,
            server_name=req.server_name,
            notify_slack=req.notify_slack,
            notify_email=req.notify_email,
            description=req.description,
        )
        return {
            "success": True,
            "rule_id": rule_id,
            "message": (
                f"Alert: {req.metric} {req.condition} {req.threshold} "
                f"→ {req.severity}"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{rule_id}")
async def delete_alert(rule_id: int):
    try:
        success = await queries.delete_alert_rule(rule_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert rule {rule_id} not found",
            )
        return {"success": True, "message": f"Rule {rule_id} removed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
