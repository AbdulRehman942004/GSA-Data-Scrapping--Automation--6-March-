from sqlmodel import SQLModel, Field
from datetime import datetime

class GSALink(SQLModel, table=True):
    __tablename__ = 'gsa_links'
    part_number: str = Field(primary_key=True)
    gsa_link: str = Field()
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_scraped: bool = Field(default=False)

class ImportedPart(SQLModel, table=True):
    __tablename__ = 'imported_parts'
    id: int = Field(default=None, primary_key=True)
    part_number: str = Field(index=True)
    manufacturer: str = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GSAScrapedData(SQLModel, table=True):
    __tablename__ = 'gsa_scraped_data'
    id: int = Field(default=None, primary_key=True)
    part_number: str = Field(index=True)
    gsa_low_price_1: float = Field(default=None)
    unit_1: str = Field(default=None)
    contractor_1: str = Field(default=None)
    gsa_low_price_2: float = Field(default=None)
    unit_2: str = Field(default=None)
    contractor_2: str = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
