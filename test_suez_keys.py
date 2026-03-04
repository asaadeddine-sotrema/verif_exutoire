import sys
import pandas as pd
import traceback
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_suez import process_suez, charger_suez_terrain

f_ctc = "/home/amine/projects/Contrôle CTC du 01 AU 28-02-2026.xls"
f_dech = "/home/amine/projects/Contrôle DECHETTERIE du 01 au 28-02-2026.xlsx"
f_fac = "/home/amine/projects/Listing GPSEO du 01 au 28-02-26.xlsx"

df_ctc = charger_suez_terrain(f_ctc, "CTC")
df_dech = charger_suez_terrain(f_dech, "DECH")

df_ter = pd.concat([df_ctc, df_dech]) if not df_ctc.empty or not df_dech.empty else pd.DataFrame()

df_ref_raw = pd.read_excel(f_fac, header=0, dtype=str)
cols_ref = [str(c).lower().strip() for c in df_ref_raw.columns]

print("Terrain Ticket head:")
print(df_ter['Num Ticket'].head(5) if 'Num Ticket' in df_ter.columns else 'No Num Ticket in Ter')
print("Terrain Bon head:")
print(df_ter['Num Bon'].head(5) if 'Num Bon' in df_ter.columns else 'No Num Bon in Ter')

print("Facture raw cols:")
print(cols_ref)
