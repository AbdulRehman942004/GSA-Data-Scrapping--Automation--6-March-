import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import state
from link_generation.gsa_link_automation_fast import GSALinkAutomationFast
from settings import EXCEL_FILE_PATH

router = APIRouter(prefix="/api/links", tags=["Link Generation"])
logger = logging.getLogger(__name__)

VALID_MODES = {"test", "full", "custom"}


class LinkGenerationRequest(BaseModel):
    mode: str = "test"       # "test" | "full" | "custom"
    item_limit: int = 5
    start_row: int = 1
    end_row: int = 100


def _validate_range(start_row: int, end_row: int) -> None:
    if start_row < 1:
        raise HTTPException(status_code=422, detail="start_row must be >= 1.")
    if end_row < start_row:
        raise HTTPException(status_code=422, detail="end_row must be >= start_row.")
    if end_row - start_row > 50_000:
        raise HTTPException(status_code=422, detail="Range cannot exceed 50,000 rows.")


def _run_link_generation(req: LinkGenerationRequest) -> None:
    """Background task: runs link generation and resets state when done."""
    try:
        automation = GSALinkAutomationFast(EXCEL_FILE_PATH)
        state.active_link_automation = automation

        if req.mode == "test":
            automation.run_automation_fast_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_automation_fast()
        elif req.mode == "custom":
            automation.run_automation_fast_custom_range(req.start_row, req.end_row)

    except Exception as e:
        logger.error(f"Link generation background task error: {e}")
    finally:
        with state.state_lock:
            state.is_link_generation_running = False
            state.active_link_automation = None


@router.post("/generate")
async def generate_links(req: LinkGenerationRequest, background_tasks: BackgroundTasks):
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{req.mode}'. Choose from: {VALID_MODES}")
    if req.mode == "custom":
        _validate_range(req.start_row, req.end_row)
    if req.item_limit < 1:
        raise HTTPException(status_code=422, detail="item_limit must be >= 1.")

    with state.state_lock:
        if state.is_link_generation_running:
            raise HTTPException(status_code=400, detail="Link generation is already actively running.")
        state.is_link_generation_running = True

    background_tasks.add_task(_run_link_generation, req)
    return {"status": "started", "message": f"Link generation mode '{req.mode}' has been queued."}


@router.post("/stop")
async def stop_links():
    if state.active_link_automation:
        state.active_link_automation.stop()
        return {"status": "stopping", "message": "Link generation stop signal sent."}
    return {"status": "idle", "message": "Link generation is not running."}
