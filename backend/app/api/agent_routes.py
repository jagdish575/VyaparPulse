from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.ai.agent import process_message
from app.ai.euri_client import EuriClient
from app.ai.tools import describe_tools
from app.database import get_db
from app.schemas import AgentRequest, AgentResponse

router = APIRouter(prefix="/api")
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]


@router.post("/agent/process", response_model=AgentResponse)
def agent_process(body: AgentRequest, db: Session = Depends(get_db), key: IdemKey = None):
    """Customer message in -> real workflow out (real steps, real order, real inventory deduction).
    With an `Idempotency-Key`, retrying the same request never creates a second order or deducts stock twice."""
    return process_message(db, body, idempotency_key=key)


@router.get("/agent/tools")
def agent_tools():
    """The allow-list of operations the AI pipeline may run (it never executes SQL)."""
    return describe_tools()


@router.get("/ai/status")
def ai_status(check: bool = Query(default=False)):
    """EURI configuration status. `check=true` makes one tiny live request. The API key is never returned."""
    client = EuriClient()
    result = {
        "provider": "EURI",
        "model": client.model,
        "base_url": client.base_url,
        "configured": client.configured,
        "connected": None,
        "error": None,
    }
    if check:
        connected, error = client.ping()
        result["connected"], result["error"] = connected, error
    return result
