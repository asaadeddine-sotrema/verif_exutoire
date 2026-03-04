import sys
import pandas as pd
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_valene import process_valoseine

f_ter = "/home/amine/projects/C63CFD05_BA0B_D9C1_9A4F_C6AD08912B1A_20260303-1419.xls"
f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"

try:
    with open(f_ter, 'rb') as t, open(f_fac, 'rb') as f:
        df = process_valoseine(t, f)
        
    print("Orphans F:")
    orph_f = df[df['Verif_Exutoire'] == 'Pb.Ext']
    print("Number of Pb.Ext rows:", len(orph_f))
    print(orph_f[['Date', 'Num Ticket', 'Num Bon', 'Poids_Facture']].head(10))

except Exception as e:
    import traceback
    traceback.print_exc()
