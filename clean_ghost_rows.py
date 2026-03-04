import sys
import pandas as pd
from sqlalchemy import text
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from app import get_db_engine

engine = get_db_engine()

with engine.connect() as conn:
    # Find active rows with Date IS NULL for PICHETA VALOSEINE
    sql_find_nulls = """
        SELECT id, "Num Ticket" 
        FROM verif_tonnage_historique 
        WHERE "Exutoire" = 'PICHETA VALOSEINE DECH TRIEL' 
        AND "Date" IS NULL 
        AND "isActive" = TRUE
    """
    null_rows = pd.read_sql(sql_find_nulls, conn)
    
    if len(null_rows) == 0:
        print("No ghost rows found.")
    else:
        print(f"Found {len(null_rows)} ghost rows with NULL dates.")
        
        # Check if they have a counterpart with a valid date and same Ticket
        # We'll just archive all NULL date rows for PICHETA VALOSEINE DECH TRIEL for now, 
        # since we know the script today generates proper dates for all of them.
        
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

