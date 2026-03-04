import sys
import pandas as pd
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from app import get_db_engine

engine = get_db_engine()
try:
    with engine.connect() as conn:
        res = pd.read_sql("SELECT id, \"Date\", \"Num Ticket\", \"Num Bon\", \"isActive\" FROM verif_tonnage_historique WHERE \"Exutoire\" = 'PICHETA VALOSEINE DECH TRIEL' AND \"isActive\" = TRUE", conn)
        print(f"Total active Picheta Valoseine rows: {len(res)}")
        null_dates = res[res['Date'].isna()]
        print(f"Active rows with NULL Date: {len(null_dates)}")
        if len(null_dates) > 0:
            print("Null date rows samples:")
            print(null_dates.head())
        print("Valid date rows samples:")
        print(res[~res['Date'].isna()].head())
except Exception as e:
    import traceback
    traceback.print_exc()
