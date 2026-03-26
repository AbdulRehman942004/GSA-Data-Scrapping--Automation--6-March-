from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import ALLOWED_ORIGINS
from routes import imports, links, scraping, status

app = FastAPI(
    title="GSA Scraper Automation API",
    description="API to run and track the GSA Advantage link generation, scraping, and export processes.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports.router)
app.include_router(links.router)
app.include_router(scraping.router)
app.include_router(status.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
