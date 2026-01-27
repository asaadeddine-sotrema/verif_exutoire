import pandas as pd

f_path = "source/SUEZ/Listing GPSEO du 01 au 11-01-26.xlsx"
df = pd.read_excel(f_path, header=0)

col_target = None
for c in df.columns:
    if "nom recherche client" in str(c).lower(): 
        col_target = c
        break

if col_target:
    print(f"Column found: {col_target}")
    unique_vals = df[col_target].astype(str).unique()
    print("Unique values:")
    print(unique_vals)
    
    if "GPSEOAUB" in unique_vals:
        print("GPSEOAUB FOUND exactly.")
    else:
        print("GPSEOAUB NOT FOUND exactly.")
        # Check for partial
        matches = [v for v in unique_vals if "GPSEO" in v]
        print(f"Partial matches for GPSEO: {matches}")
else:
    print("Column 'Nom recherche client' not found.")
