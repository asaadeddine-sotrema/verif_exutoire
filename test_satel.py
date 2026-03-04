import sys
import pandas as pd
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_satel import charger_satel_smirtom_enc, process_satel_smirtom_enc

f_ter = "/home/amine/projects/77AC61D9_0F9A_24C5_A822_3DA2F09E9D00_20260303-1512.xls"
f_fac = "/home/amine/projects/SATEL SMIRTOM JANVIER 2026.xls"

try:
    print("--- CHARGEMENT TERRAIN ---")
    with open(f_ter, 'rb') as t:
        df_ter = charger_satel_smirtom_enc(t)
    print(f"Lignes Terrain: {len(df_ter)}")
    if not df_ter.empty:
        print(df_ter[['Date_Ref', 'Num Ticket', 'Poids_Terrain', 'Client']].head(3))
        
    print("\n--- TRAITEMENT COMPLET ---")
    with open(f_ter, 'rb') as t, open(f_fac, 'rb') as f:
        df_final = process_satel_smirtom_enc(t, f)
    print(f"Lignes Finales: {len(df_final)}")
    if not df_final.empty:
        print(df_final[['Date_Ref', 'Num Ticket', '_merge']].head(10))
        print("Répartition _merge:")
        print(df_final['_merge'].value_counts())
    
except Exception as e:
    import traceback
    traceback.print_exc()

