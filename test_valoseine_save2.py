import sys
import pandas as pd
import numpy as np

sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_valene import process_valoseine
from app import save_to_db, get_db_engine

engine = get_db_engine()

f_ter = "/home/amine/projects/C63CFD05_BA0B_D9C1_9A4F_C6AD08912B1A_20260303-1419.xls"
f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"

try:
    with open(f_ter, 'rb') as t, open(f_fac, 'rb') as f:
        df = process_valoseine(t, f)
        
    print("Process returned Date head:")
    print(df['Date'].head(3))
    print("Saving to DB locally...")

    import builtins
    import streamlit as st
    st.warning = lambda x: print("[WARN]", x)
    st.info = lambda x: print("[INFO]", x)
    st.success = lambda x: print("[SUCCESS]", x)
    st.error = lambda x: print("[ERROR]", x)

    save_to_db(df.head(5), engine)

    res = pd.read_sql("SELECT \"Date\", \"Num Ticket\" FROM verif_tonnage_historique WHERE \"Num Ticket\" = '01261785'", engine)
    print("Data in DB after insert for top row:")
    print(res)

    with engine.connect() as conn:
        conn.execute(pd.io.sql.text("DELETE FROM verif_tonnage_historique WHERE \"Num Ticket\" IN ('01261785','01261786','01261787','01261788','01261809')"))
        conn.commit()

except Exception as e:
    import traceback
    traceback.print_exc()
