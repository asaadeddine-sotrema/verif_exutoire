import pandas as pd

f_path = "source/SUEZ/Listing GPSEO du 01 au 11-01-26.xlsx"
df_ref = pd.read_excel(f_path, header=0)

print("Original Columns:")
print(df_ref.columns.tolist())

cols_ref = {}
col_ext_client_found = False

for c in df_ref.columns:
    cl = str(c).lower().strip()
    if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
    if "quantité nette" in cl: cols_ref[c] = "Poids_Facture"
    if "date du bon" in cl: cols_ref[c] = "Date_Ref"
    if "nom recherche client" in cl: cols_ref[c] = "Billing_Client"
    
    # 1. Cible principale : Nom de l'adresse de service (le Site)
    if "adresse de service" in cl and "nom" in cl:
            print(f"MATCH 'adresse de service': {c}")
            cols_ref[c] = "EXT Client"
            col_ext_client_found = True
            
    # 2. Cible secondaire : Nom Chantier / Producteur (si pas encore trouvé)
    elif ("chantier" in cl or "producteur" in cl) and "nom" in cl:
            if not col_ext_client_found:
                print(f"MATCH 'chantier/prod': {c}")
                cols_ref[c] = "EXT Client"
                col_ext_client_found = True
    
    if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
    if "immatriculation" in cl: cols_ref[c] = "Immatriculation"

# Fallback : Si on n'a trouvé ni site ni chantier, on prend le payeur (GPSEO)
if not col_ext_client_found:
    print("FALLBACK triggered")
    for c in df_ref.columns:
        if "nom recherche client" in str(c).lower():
            cols_ref[c] = "EXT Client"

print("\nMapping constructed:")
print(cols_ref)

df_ref = df_ref.rename(columns=cols_ref)
print("\nPost-Rename Columns:")
print(df_ref.columns.tolist())

if "EXT Client" in df_ref.columns:
    print("\nEXT Client Head:")
    print(df_ref["EXT Client"].head())
    print("\nEXT Client Unique:")
    print(df_ref["EXT Client"].unique())
else:
    print("\nEXT Client NOT FOUND in DataFrame columns")
