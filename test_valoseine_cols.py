import sys
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
import pandas as pd

f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"

try:
    with open(f_fac, 'rb') as f:
        temp = pd.read_excel(f, header=None, nrows=20)
        idx_ref = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "document" in row_str and "date" in row_str: idx_ref = i; break
            if "n° bon" in row_str and "date" in row_str: idx_ref = i; break
                
        f.seek(0)
        df_ref = pd.read_excel(f, header=idx_ref, dtype=str)
        print("Header index found:", idx_ref)
        print("Raw Columns:", list(df_ref.columns))
        
        cols_ref = {}
        for c in df_ref.columns:
            cl = str(c).lower()
            if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
            if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
            if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
            if "date" in cl and "heure" not in cl: cols_ref[c] = "Date_Ref"
            if "immat" in cl: cols_ref[c] = "Immatriculation"
            if "libellé produit" in cl or "libelle produit" in cl: cols_ref[c] = "EXT_Matiere"
        
        print("Mapped Columns:", cols_ref)
except Exception as e:
    import traceback
    traceback.print_exc()
