import sys
import pandas as pd
from sqlalchemy import text
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from app import get_db_engine

engine = get_db_engine()

with engine.connect() as conn:
    sql_archive = """
        UPDATE verif_tonnage_historique 
        SET "isActive" = FALSE, "Motif" = 'Ghost record with NULL date (Duplicate)'
        WHERE "Exutoire" = 'PICHETA VALOSEINE DECH TRIEL' 
        AND "Date" IS NULL 
        AND "isActive" = TRUE
    """
    res = conn.execute(text(sql_archive))
    conn.commit()
    print(f"Archived {res.rowcount} ghost rows.")

