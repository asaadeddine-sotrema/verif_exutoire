
import pandas as pd
import io

def charger_suez_terrain(f, type_fichier):
    print(f"--- Loading {type_fichier} ---")
    try:
        # Simulation of the logic in app.py
        if isinstance(f, str):
            temp = pd.read_excel(f, header=None, nrows=10)
        else:
             temp = pd.read_excel(f, header=None, nrows=10)
        
        idx = 3 
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num tp manuel" in row_str or "n°bon de vidage" in row_str: 
                idx = i
                print(f"Header found at index {idx}")
                break
        
        if isinstance(f, str):
             df = pd.read_excel(f, header=idx)
        else:
             f.seek(0)
             df = pd.read_excel(f, header=idx)

        print("Columns found:", df.columns.tolist())
        
        cols_map = {}
        col_client_candidate = None
        has_nchantier = False

        for c in df.columns:
            cl = str(c).lower().strip()
            # ... existing logic ...
            if "nchantier" in cl:
                col_client_candidate = c
                has_nchantier = True
        
        best_client_col = None
        for c in df.columns:
             cl = str(c).lower().strip()
             if "nchantier" in cl: best_client_col = c; break # Priority 1
        
        if not best_client_col:
             for c in df.columns:
                 cl = str(c).lower().strip()
                 if "exutoire" in cl: best_client_col = c; break # Priority 2

        print(f"Best Client Col identified: {best_client_col}")

        if best_client_col:
            cols_map[best_client_col] = "Client"

        df = df.rename(columns=cols_map)
        if "Client" in df.columns:
             print("Client column extracted successfully. First 5 values:")
             print(df["Client"].head())
        else:
             print("Client column NOT extracted.")
             
        return df
    except Exception as e: 
        print(f"Error: {e}")
        return pd.DataFrame()

# Test with the file
f_path = "source/SUEZ/SUEZ_DECH_S2S5_JAN2026.xlsx"
df = charger_suez_terrain(f_path, "DECH")
