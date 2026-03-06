import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

# Mocking data specifically to trace INT Client from start to finish
df_lb = pd.DataFrame({
    'Num Ticket': ['T1', 'T2'],
    'Client': ['C1_TER', 'C2_TER'],
    'Matiere_T': ['M1', 'M2'],
    'Poids_Terrain': [10.0, 20.0],
    'Date_Ref': ['2026-02-01', '2026-02-02']
})
df_fac = pd.DataFrame({
    'Num Ticket': ['T1', 'T3'],
    'Client': ['C1_FAC', 'C3_FAC'],
    'EXT_Matiere': ['M1', 'M3'],
    'Poids_Facture': [10.0, 30.0],
    'Date_Ref': ['2026-02-01', '2026-02-03']
})

df_lb.to_excel('test_lb.xlsx', index=False)
df_fac.to_excel('test_fac.xlsx', index=False)

f_lb = open('test_lb.xlsx', 'rb')
f_fac = open('test_fac.xlsx', 'rb')

try:
    final = process_dupille(f_lb, f_fac)
    print(final[['Num Ticket', 'INT Client', 'EXT Client', '_merge']].to_string())
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    f_lb.close()
    f_fac.close()
