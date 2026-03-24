from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlmodel import Session

import state
from database.models import GSALink, GSAScrapedData
from database.db import get_engine
from export_to_excel import export_to_excel

router = APIRouter(tags=["Status & Export"])


@router.get("/")
def read_root():
    return {"message": "Welcome to the GSA Scraper Automation API. Go to /docs to view your available endpoints!"}


@router.get("/api/status")
async def get_status():
    engine = get_engine()
    try:
        with Session(engine) as session:
            total_links = session.query(GSALink).count()
            total_scraped_links = session.query(GSALink).filter(GSALink.is_scraped == True).count()
            total_scraped_records = session.query(GSAScrapedData).count()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"DB Error: {str(e)}"})

    return {
        "is_link_generation_running": state.is_link_generation_running,
        "is_scraping_running": state.is_scraping_running,
        "database": {
            "total_generated_links_count": total_links,
            "total_successfully_scraped_links_count": total_scraped_links,
            "total_scraped_data_records": total_scraped_records,
        },
    }


@router.get("/api/export")
async def download_export():
    """Generate the final Excel file from Postgres data and stream it for download."""
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
