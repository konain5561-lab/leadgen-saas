"""
Insert sample leads for local testing (no Google Maps scrape required).

Usage (from backend/ with venv active):
    python seed_sample_leads.py
"""

from database import SessionLocal, engine
import models

SAMPLE_LEADS = [
    {
        "name": "Karachi Dental Care",
        "category": "Dentist",
        "rating": 3.2,
        "review_count": 8,
        "address": "Clifton Block 5, Karachi",
        "phone": "+92-21-1234567",
        "website": None,
    },
    {
        "name": "Smile Studio",
        "category": "Dentist",
        "rating": 4.8,
        "review_count": 412,
        "address": "DHA Phase 6, Karachi",
        "phone": "+92-21-7654321",
        "website": "https://smilestudio.example.com",
    },
    {
        "name": "City Orthodontics",
        "category": "Orthodontist",
        "rating": 3.9,
        "review_count": 23,
        "address": "Gulshan-e-Iqbal, Karachi",
        "phone": "+92-21-9988776",
        "website": "http://cityortho.example.com",
    },
    {
        "name": "Quick Fix Dental",
        "category": "Dentist",
        "rating": 2.8,
        "review_count": 4,
        "address": "Saddar, Karachi",
        "phone": None,
        "website": None,
    },
    {
        "name": "Premier Dental Group",
        "category": "Dental clinic",
        "rating": 4.5,
        "review_count": 156,
        "address": "Bahria Town, Karachi",
        "phone": "+92-21-5544332",
        "website": "https://premierdental.example.com",
    },
]


def main():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        added = 0
        for lead in SAMPLE_LEADS:
            exists = (
                db.query(models.Business)
                .filter_by(name=lead["name"], address=lead["address"])
                .first()
            )
            if exists:
                continue
            db.add(models.Business(**lead))
            added += 1
        db.commit()
        total = db.query(models.Business).count()
        print(f"Added {added} sample leads. Total leads in DB: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
