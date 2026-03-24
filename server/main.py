from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import threading

# Project modules
from link_generation.gsa_link_automation_fast import GSALinkAutomationFast
from scraping.gsa_scraping_automation import GSAScrapingAutomation
from export_to_excel import export_to_excel
from database.models import GSALink, GSAScrapedData
from database.db import get_engine
from settings import ALLOWED_ORIGINS, EXCEL_FILE_PATH, MFR_MAPPING_FILE_PATH
from sqlmodel import Session, select

# Define the FastAPI application
app = FastAPI(
    title="GSA Scraper Automation API",
    description="API to run and track the GSA Advantage link generation, scraping, and export processes.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
state_lock = threading.Lock()
is_link_generation_running = False
is_scraping_running = False
active_link_automation = None
active_scraping_automation = None

# API Models
class LinkGenerationRequest(BaseModel):
    mode: str = "test"  # "test", "full", "custom"
    item_limit: int = 5
    start_row: int = 1
    end_row: int = 100
    
class ScrapingRequest(BaseModel):
    mode: str = "test"  # "test", "full", "missing", "custom"
    item_limit: int = 3
    start_row: int = 1
    end_row: int = 100

# Background task functions
def task_run_link_generation(req: LinkGenerationRequest):
    global is_link_generation_running, active_link_automation
    try:
        automation = GSALinkAutomationFast(EXCEL_FILE_PATH)
        active_link_automation = automation

        if req.mode == "test":
            automation.run_automation_fast_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_automation_fast()
        elif req.mode == "custom":
            automation.run_automation_fast_custom_range(req.start_row, req.end_row)

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Link generation background task error: {e}")
    finally:
        with state_lock:
            is_link_generation_running = False
            active_link_automation = None


def task_run_scraping(req: ScrapingRequest):
    global is_scraping_running, active_scraping_automation
    try:
        automation = GSAScrapingAutomation(EXCEL_FILE_PATH, MFR_MAPPING_FILE_PATH)
        active_scraping_automation = automation

        if req.mode == "test":
            automation.run_scraping_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_scraping_full()
        elif req.mode == "missing":
            automation.run_scraping_missing_only()
        elif req.mode == "custom":
            automation.run_scraping_custom_range(req.start_row, req.end_row)

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Scraping background task error: {e}")
    finally:
        with state_lock:
            is_scraping_running = False
            active_scraping_automation = None

# API Routes
@app.get("/")
def read_root():
    return {"message": "Welcome to the GSA Scraper Automation API. Go to /docs to view your available endpoints!"}

VALID_LINK_MODES = {"test", "full", "custom"}
VALID_SCRAPE_MODES = {"test", "full", "missing", "custom"}


def _validate_range(start_row: int, end_row: int) -> None:
    if start_row < 1:
        raise HTTPException(status_code=422, detail="start_row must be >= 1.")
    if end_row < start_row:
        raise HTTPException(status_code=422, detail="end_row must be >= start_row.")
    if end_row - start_row > 50_000:
        raise HTTPException(status_code=422, detail="Range cannot exceed 50,000 rows.")


@app.post("/api/links/generate")
async def generate_links(req: LinkGenerationRequest, background_tasks: BackgroundTasks):
    global is_link_generation_running

    if req.mode not in VALID_LINK_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{req.mode}'. Choose from: {VALID_LINK_MODES}")
    if req.mode == "custom":
        _validate_range(req.start_row, req.end_row)
    if req.item_limit < 1:
        raise HTTPException(status_code=422, detail="item_limit must be >= 1.")

    with state_lock:
        if is_link_generation_running:
            raise HTTPException(status_code=400, detail="Link generation is already actively running.")
        is_link_generation_running = True

    background_tasks.add_task(task_run_link_generation, req)
    return {"status": "started", "message": f"Link generation mode '{req.mode}' has been queued."}


@app.post("/api/scrape/start")
async def start_scraping(req: ScrapingRequest, background_tasks: BackgroundTasks):
    global is_scraping_running

    if req.mode not in VALID_SCRAPE_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode '{req.mode}'. Choose from: {VALID_SCRAPE_MODES}")
    if req.mode == "custom":
        _validate_range(req.start_row, req.end_row)
    if req.item_limit < 1:
        raise HTTPException(status_code=422, detail="item_limit must be >= 1.")

    with state_lock:
        if is_scraping_running:
            raise HTTPException(status_code=400, detail="Scraping process is already actively running.")
        is_scraping_running = True

    background_tasks.add_task(task_run_scraping, req)
    return {"status": "started", "message": f"Scraping mode '{req.mode}' has been queued."}

@app.post("/api/links/stop")
async def stop_links():
    global active_link_automation
    if active_link_automation:
        active_link_automation.stop()
        return {"status": "stopping", "message": "Link generation stop signal sent."}
    return {"status": "idle", "message": "Link generation is not running."}

@app.post("/api/scrape/stop")
async def stop_scrape():
    global active_scraping_automation
    if active_scraping_automation:
        active_scraping_automation.stop()
        return {"status": "stopping", "message": "Scraping stop signal sent."}
    return {"status": "idle", "message": "Scraping is not running."}

@app.get("/api/status")
async def get_status():
    engine = get_engine()
    
    try:
        with Session(engine) as session:
            # Query counts
            total_generated_links_count = session.query(GSALink).count()
            total_successfully_scraped_links_count = session.query(GSALink).filter(GSALink.is_scraped == True).count()
            total_scraped_db_records = session.query(GSAScrapedData).count()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"DB Error: {str(e)}"})

    return {
        "is_link_generation_running": is_link_generation_running,
        "is_scraping_running": is_scraping_running,
        "database": {
            "total_generated_links_count": total_generated_links_count,
            "total_successfully_scraped_links_count": total_successfully_scraped_links_count,
            "total_scraped_data_records": total_scraped_db_records
        }
    }

@app.get("/api/export")
async def download_export():
    """Generates the final Excel file dynamically from Postgres data and downloads it."""
    
    # Run the export function synchronously and get in-memory buffer + dynamic filename
    result = export_to_excel()
    
    if not result:
        raise HTTPException(status_code=500, detail="The export compilation process failed.")
        
    output_buffer, filename = result
        
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
        
    return StreamingResponse(
        iter([output_buffer.getvalue()]), 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
