from datetime import datetime
from sqlmodel import Session, select
from database.models import GSALink, GSAScrapedData, ImportedPart


def get_link_by_part_number(engine, part_number):
    """Return the GSALink record for the given part number, or None."""
    with Session(engine) as session:
        return session.exec(
            select(GSALink).where(GSALink.part_number == str(part_number))
        ).first()


def mark_link_scraped(engine, part_number):
    """Set is_scraped=True on the GSALink record for part_number."""
    with Session(engine) as session:
        rec = session.exec(
            select(GSALink).where(GSALink.part_number == str(part_number))
        ).first()
        if rec:
            rec.is_scraped = True
            session.add(rec)
            session.commit()


def upsert_link(engine, part_number, gsa_url):
    """Insert or update a GSALink record."""
    with Session(engine) as session:
        rec = session.exec(
            select(GSALink).where(GSALink.part_number == str(part_number))
        ).first()
        if rec:
            rec.gsa_link = gsa_url
            rec.created_at = datetime.utcnow()
        else:
            rec = GSALink(part_number=str(part_number), gsa_link=gsa_url)
            session.add(rec)
        session.commit()
    return True


def upsert_scraped_data(engine, part_number, products_data):
    """Insert or update a GSAScrapedData record from a list of up to 2 product dicts."""
    val_1 = products_data[0] if len(products_data) > 0 else {}
    val_2 = products_data[1] if len(products_data) > 1 else {}

    with Session(engine) as session:
        rec = session.exec(
            select(GSAScrapedData).where(GSAScrapedData.part_number == str(part_number))
        ).first()
        if rec:
            rec.gsa_low_price_1 = val_1.get('price')
            rec.unit_1 = val_1.get('unit')
            rec.contractor_1 = val_1.get('contractor')
            rec.gsa_low_price_2 = val_2.get('price')
            rec.unit_2 = val_2.get('unit')
            rec.contractor_2 = val_2.get('contractor')
            rec.created_at = datetime.utcnow()
        else:
            rec = GSAScrapedData(
                part_number=str(part_number),
                gsa_low_price_1=val_1.get('price'),
                unit_1=val_1.get('unit'),
                contractor_1=val_1.get('contractor'),
                gsa_low_price_2=val_2.get('price'),
                unit_2=val_2.get('unit'),
                contractor_2=val_2.get('contractor'),
            )
            session.add(rec)
        session.commit()
    return True


# ── Imported parts ─────────────────────────────────────────────

def clear_imported_parts(engine):
    """Delete all rows from imported_parts (preparing for a fresh import)."""
    with Session(engine) as session:
        records = session.exec(select(ImportedPart)).all()
        for rec in records:
            session.delete(rec)
        session.commit()


def bulk_insert_imported_parts(engine, parts: list[dict]) -> int:
    """Insert a list of {'part_number': ..., 'manufacturer': ...} dicts. Returns count."""
    with Session(engine) as session:
        for p in parts:
            session.add(ImportedPart(
                part_number=p["part_number"],
                manufacturer=p.get("manufacturer", ""),
            ))
        session.commit()
    return len(parts)


def get_imported_parts_count(engine) -> int:
    """Return how many rows are in imported_parts."""
    with Session(engine) as session:
        return len(session.exec(select(ImportedPart)).all())


def get_all_imported_parts(engine) -> list[ImportedPart]:
    """Return all imported part records."""
    with Session(engine) as session:
        return session.exec(select(ImportedPart).order_by(ImportedPart.id)).all()


def clear_gsa_links(engine):
    """Delete all rows from gsa_links."""
    with Session(engine) as session:
        records = session.exec(select(GSALink)).all()
        for rec in records:
            session.delete(rec)
        session.commit()


def clear_gsa_scraped_data(engine):
    """Delete all rows from gsa_scraped_data."""
    with Session(engine) as session:
        records = session.exec(select(GSAScrapedData)).all()
        for rec in records:
            session.delete(rec)
        session.commit()
