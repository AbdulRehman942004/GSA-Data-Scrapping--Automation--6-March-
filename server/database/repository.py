from datetime import datetime
from sqlmodel import Session, select
from database.models import GSALink, GSAScrapedData


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
