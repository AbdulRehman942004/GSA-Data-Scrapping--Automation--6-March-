from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlmodel import Session

import state
from database.models import GSALink, GSAScrapedData, ImportedPart
from database.db import get_engine
from services.export_service import export_to_excel, get_export_info

router = APIRouter(tags=["Status & Export"])


@router.get("/")
def read_root():
    return {"message": "Welcome to the GSA Scraper Automation API. Go to /docs to view your available endpoints!"}


@router.get("/api/status")
async def get_status():
    engine = get_engine()
    try:
        with Session(engine) as session:
            imported_count = session.query(ImportedPart).count()

            if imported_count == 0:
                # No import yet → everything is zero
                total_links = 0
                total_scraped_links = 0
                total_scraped_records = 0
            else:
                total_links = session.query(GSALink).count()
                total_scraped_links = session.query(GSALink).filter(GSALink.is_scraped == True).count()
                total_scraped_records = session.query(GSAScrapedData).count()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"DB Error: {str(e)}"})

    scraping_progress = None
    if state.parallel_orchestrator:
        scraping_progress = state.parallel_orchestrator.progress_snapshot()

    link_extraction_progress = None
    if state.parallel_link_extractor:
        link_extraction_progress = state.parallel_link_extractor.progress_snapshot()

    return {
        "is_link_generation_running": state.is_link_generation_running,
        "is_scraping_running": state.is_scraping_running,
        "is_link_extraction_running": state.is_link_extraction_running,
        "database": {
            "total_generated_links_count": total_links,
            "total_successfully_scraped_links_count": total_scraped_links,
            "total_scraped_data_records": total_scraped_records,
        },
        "scraping_progress": scraping_progress,
        "link_extraction_progress": link_extraction_progress,
    }


@router.get("/api/export/info")
async def export_info():
    """
    Return a lightweight JSON summary of what export data is currently available,
    without triggering the actual download. The frontend uses this to show the user
    a descriptive message before downloading.
    """
    return get_export_info()


@router.get("/api/export")
async def download_export():
    """
    Generate the final Excel file from Postgres data and stream it for download.
    Only the sheets for engines that have actually produced scraped data are included:
      - 'GSA Parts Data'   → present when gsa_scraped_data has records  (price extraction)
      - 'Links Scraped Data' → present when links_scraped_data has records (link extraction)
    """
    info = get_export_info()
    if info["active_engine"] == "none":
        raise HTTPException(
            status_code=400,
            detail=(
                "No scraped data found. "
                "Run 'Start Price Extraction' or 'Start Link Extraction' first."
            ),
        )

    result = export_to_excel()
    if not result:
        raise HTTPException(status_code=500, detail="The export compilation process failed.")

    output_buffer, filename = result
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([output_buffer.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
