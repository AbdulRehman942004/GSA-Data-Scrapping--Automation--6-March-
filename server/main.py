from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
import threading

# Import project automation modules
from link_generation.gsa_link_automation_fast import GSALinkAutomationFast, GSALink
from scraping.gsa_scraping_automation import GSAScrapingAutomation, MFR_MAPPING_FILE, GSAScrapedData
from export_to_excel import export_to_excel

# Database imports
from sqlmodel import Session, select, create_engine
from database.models import GSALink, GSAScrapedData
from database.db import get_engine
from dotenv import load_dotenv

# Define the FastAPI application
app = FastAPI(
    title="GSA Scraper Automation API",
    description="API to run and track the GSA Advantage link generation, scraping, and export processes.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production, e.g., ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to track status
state_lock = threading.Lock()
is_link_generation_running = False
is_scraping_running = False

# Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(SCRIPT_DIR, "new_requirements", "GSA Advantage Low price.xlsx")

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
    global is_link_generation_running
    try:
        automation = GSALinkAutomationFast(EXCEL_FILE)
        
        if req.mode == "test":
            automation.run_automation_fast_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_automation_fast()
        elif req.mode == "custom":
            automation.run_automation_fast_custom_range(req.start_row, req.end_row)
            
    except Exception as e:
        print(f"Error in link generation background task: {e}")
    finally:
        with state_lock:
            is_link_generation_running = False

def task_run_scraping(req: ScrapingRequest):
    global is_scraping_running
    try:
        automation = GSAScrapingAutomation(EXCEL_FILE, MFR_MAPPING_FILE)
        
        if req.mode == "test":
            automation.run_scraping_test_mode(req.item_limit)
        elif req.mode == "full":
            automation.run_scraping_full()
        elif req.mode == "missing":
            automation.run_scraping_missing_only()
        elif req.mode == "custom":
            automation.run_scraping_custom_range(req.start_row, req.end_row)
            
    except Exception as e:
        print(f"Error in scraping background task: {e}")
    finally:
        with state_lock:
            is_scraping_running = False

# API Routes
@app.get("/")
def read_root():
    return {"message": "Welcome to the GSA Scraper Automation API. Go to /docs to view your available endpoints!"}

@app.post("/api/links/generate")
async def generate_links(req: LinkGenerationRequest, background_tasks: BackgroundTasks):
    global is_link_generation_running
    
    with state_lock:
        if is_link_generation_running:
            raise HTTPException(status_code=400, detail="Link generation is already actively running.")
        is_link_generation_running = True
        
    background_tasks.add_task(task_run_link_generation, req)
    return {"status": "started", "message": f"Link generation mode '{req.mode}' has been queued."}

@app.post("/api/scrape/start")
async def start_scraping(req: ScrapingRequest, background_tasks: BackgroundTasks):
    global is_scraping_running
    
    with state_lock:
        if is_scraping_running:
            raise HTTPException(status_code=400, detail="Scraping process is already actively running.")
        is_scraping_running = True
        
    background_tasks.add_task(task_run_scraping, req)
    return {"status": "started", "message": f"Scraping mode '{req.mode}' has been queued."}

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
    
    # Run the export function synchronously. Alternatively, if this gets 
    # extremely slow over time, it could happen in a background task too.
    # Right now, 20 seconds is perfectly acceptable.
    
    exported_file_path = export_to_excel()
    
    if not exported_file_path or not os.path.exists(exported_file_path):
        raise HTTPException(status_code=500, detail="The export processing failed.")
        
    return FileResponse(
        path=exported_file_path, 
        filename=os.path.basename(exported_file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
