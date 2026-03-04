import sys
import pandas as pd
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from app import save_to_db, get_db_engine

engine = get_db_engine()

df = pd.DataFrame([{
    'Date': pd.Timestamp('2026-03-03'),
    'Num Ticket': 'TEST_VALOSEINE',
    'Num Bon': '0000',
    'Exutoire': 'TEST_PROVIDER',
    'Client': 'TEST',
    'INT Client': 'TEST',
    'EXT Client': 'TEST'
}])

print("Inserting test row...")
print(df)
save_to_db(df, engine)

res = pd.read_sql("SELECT \"Date\", \"Num Ticket\" FROM verif_tonnage_historique WHERE \"Num Ticket\" = 'TEST_VALOSEINE'", engine)
print("Data in DB:")
print(res)

with engine.connect() as conn:
    conn.execute(pd.io.sql.text("DELETE FROM verif_tonnage_historique WHERE \"Num Ticket\" = 'TEST_VALOSEINE'"))
    conn.commit()

