import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

df_lb = pd.DataFrame({
    'Num Ticket': ['T1'],
    'INT Client': [''], # Empty string instead of actual data
    'Tournée modèle': ['FALLBACK_TM'],
    'Poids_Terrain': [10.5],
    'Date_Ref': ['2026-02-01']
})
df_fac = pd.DataFrame({
    'Num Ticket': ['T1'],
    'EXT Client': ['C1_FAC'],
    'Poids_Facture': [10.5],
    'Date_Ref': ['2026-02-01'],
    'lib_transporteur': ['SOTREMA']
})

df_lb.to_excel('test_lb.xlsx', index=False)
df_fac.to_excel('test_fac.xlsx', index=False)

try:
    with open('test_lb.xlsx', 'rb') as f_lb, open('test_fac.xlsx', 'rb') as f_fac:
        final = process_dupille(f_lb, f_fac)
    print("Matching result (T1) with empty INT Client:")
    cols = ['Num Ticket', 'INT Client', 'EXT Client', '_merge']
    print(final[cols])
except Exception as e:
    import traceback
    traceback.print_exc()
