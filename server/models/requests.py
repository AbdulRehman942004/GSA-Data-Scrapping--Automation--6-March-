from pydantic import BaseModel


class LinkGenerationRequest(BaseModel):
    mode: str = "test"       # "test" | "full" | "custom"
    item_limit: int = 5
    start_row: int = 1
    end_row: int = 100


class ScrapingRequest(BaseModel):
    mode: str = "test"       # "test" | "full" | "missing" | "custom"
    item_limit: int = 3
    start_row: int = 1
    end_row: int = 100
