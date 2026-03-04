import sys
import pandas as pd
from sqlalchemy import text
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from app import get_db_engine

engine = get_db_engine()
try:
    with engine.connect() as conn:
        res = pd.read_sql("SELECT id, \"Date\", \"Num Ticket\", \"Num Bon\", \"isActive\" FROM verif_tonnage_historique WHERE \"Exutoire\" = 'PICHETA VALOSEINE DECH TRIEL' ORDER BY id DESC LIMIT 10", conn)
        print("Data currently in DB for Valoseine:")
        print(res.to_string())
except Exception as e:
    import traceback
    traceback.print_exc()
