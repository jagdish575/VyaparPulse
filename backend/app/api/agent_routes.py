from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.agent import process_message
from app.ai.euri_client import EuriClient
from app.ai.tools import describe_tools
from app.database import get_db
from app.schemas import AgentRequest, AgentResponse

router = APIRouter(prefix="/api")


@router.post("/agent/process", response_model=AgentResponse)
def agent_process(body: AgentRequest, db: Session = Depends(get_db)):
    """Customer message in -> real workflow out (real steps, real order, real inventory deduction)."""
    return process_message(db, body)


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
