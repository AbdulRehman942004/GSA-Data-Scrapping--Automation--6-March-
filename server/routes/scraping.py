import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

import state
from services.scraping_service import GSAScrapingAutomation
from settings import EXCEL_FILE_PATH, MFR_MAPPING_FILE_PATH
from models.requests import ScrapingRequest

router = APIRouter(prefix="/api/scrape", tags=["Scraping"])
logger = logging.getLogger(__name__)

VALID_MODES = {"test", "full", "missing", "custom"}


def _validate_range(start_row: int, end_row: int) -> None:
    if start_row < 1:
        raise HTTPException(status_code=422, detail="start_row must be >= 1.")
    if end_row < start_row:
        raise HTTPException(status_code=422, detail="end_row must be >= start_row.")
    if end_row - start_row > 50_000:
        raise HTTPException(status_code=422, detail="Range cannot exceed 50,000 rows.")


def _run_scraping(req: ScrapingRequest) -> None:
    """Background task: runs scraping and resets state when done."""
    try:
        automation = GSAScrapingAutomation(EXCEL_FILE_PATH, MFR_MAPPING_FILE_PATH)
        state.active_scraping_automation = automation

        if req.mode == "test":
            automation.run_scraping_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_scraping_full()
        elif req.mode == "missing":
            automation.run_scraping_missing_only()
        elif req.mode == "custom":
            automation.run_scraping_custom_range(req.start_row, req.end_row)

    except Exception as e:
        logger.error(f"Scraping background task error: {e}")
    finally:
        with state.state_lock:
            state.is_scraping_running = False
            state.active_scraping_automation = None


@router.post("/start")
async def start_scraping(req: ScrapingRequest, background_tasks: BackgroundTasks):
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{req.mode}'. Choose from: {VALID_MODES}")
    if req.mode == "custom":
        _validate_range(req.start_row, req.end_row)
    if req.item_limit < 1:
        raise HTTPException(status_code=422, detail="item_limit must be >= 1.")

    with state.state_lock:
        if state.is_scraping_running:
            raise HTTPException(status_code=400, detail="Scraping process is already actively running.")
        state.is_scraping_running = True

    background_tasks.add_task(_run_scraping, req)
    return {"status": "started", "message": f"Scraping mode '{req.mode}' has been queued."}


@router.post("/stop")
async def stop_scrape():
    if state.active_scraping_automation:
        state.active_scraping_automation.stop()
        return {"status": "stopping", "message": "Scraping stop signal sent."}
    return {"status": "idle", "message": "Scraping is not running."}
