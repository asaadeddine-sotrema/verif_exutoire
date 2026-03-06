import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

# We'll make T1 match between lb and fac
df_lb = pd.DataFrame({
    'Num Ticket': ['T1', '88499'],
    'Tournée modèle': ['TM_1', 'TM_OM'],
    'Poids_Terrain': [10.0, 20.0],
    'Date_Ref': ['2026-02-01', '2026-02-02']
})
df_fac = pd.DataFrame({
    'Num Ticket': ['T1', 'F3'],
    'lib_zone': ['C1_FAC', 'C3_FAC'], # Will be renamed to EXT Client
    'Poids_Facture': [10.0, 30.0],
    'Date_Ref': ['2026-02-01', '2026-02-03'],
    'lib_transporteur': ['SOTREMA', 'SOTREMA'] # To pass the filter
})

df_lb.to_excel('test_lb.xlsx', index=False)
df_fac.to_excel('test_fac.xlsx', index=False)

try:
    with open('test_lb.xlsx', 'rb') as f_lb, open('test_fac.xlsx', 'rb') as f_fac:
        final = process_dupille(f_lb, f_fac)
    print("Matching result (T1):")
    print(final[final['Num Ticket'] == 'T1'][['Num Ticket', 'INT Client', 'EXT Client', '_merge']])
    print("\nNon-matching result (88499):")
    print(final[final['Num Ticket'] == '88499'][['Num Ticket', 'INT Client', 'EXT Client', '_merge']])
except Exception as e:
    import traceback
    traceback.print_exc()
