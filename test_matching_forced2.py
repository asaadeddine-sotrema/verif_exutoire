import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

df_lb = pd.DataFrame({
    'Num Ticket': ['T1', '88499'],
    'Tournée modèle': ['TM_1', 'TM_OM'],
    'Poids_Terrain': [10.5, 20.0],
    'Date_Ref': ['2026-02-01', '2026-02-02']
})
df_fac = pd.DataFrame({
    'Num Ticket': ['T1', 'F3'],
    'lib_zone': ['C1_FAC', 'C3_FAC'],
    'Poids_Facture': [10.5, 30.0],
    'Date_Ref': ['2026-02-01', '2026-02-03'],
    'lib_transporteur': ['SOTREMA', 'SOTREMA']
})

df_lb.to_excel('test_lb.xlsx', index=False)
df_fac.to_excel('test_fac.xlsx', index=False)

try:
    with open('test_lb.xlsx', 'rb') as f_lb, open('test_fac.xlsx', 'rb') as f_fac:
        final = process_dupille(f_lb, f_fac)
    print("Matching result (T1):")
    cols = ['Num Ticket', 'INT Client', 'EXT Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart', 'Verif_Tonnes', 'Verif_Exutoire', '_merge']
    print(final[final['Num Ticket'] == 'T1'][cols])
except Exception as e:
    import traceback
    traceback.print_exc()
