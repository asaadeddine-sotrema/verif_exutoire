import pandas as pd

f_path = "source/SUEZ/Listing GPSEO du 01 au 11-01-26.xlsx"
df = pd.read_excel(f_path, header=0)

keywords = ["LIMAY", "MUREAUX", "CLOSEAUX", "VAUCOULEURS", "GARGENVILLE", "AUBERGENVILLE", "CARR. SOUS POISSY", "TRIEL"]

found_cols = {}

print("Scanning columns for keywords...")
for col in df.columns:
    try:
        # Check if any keyword appears in the unique values of the column
        unique_vals = df[col].astype(str).unique()
        matches = []
        for val in unique_vals:
            for k in keywords:
                if k in val.upper():
                    matches.append(val)
        
        if matches:
            found_cols[col] = list(set(matches))[:5] # Store first 5 distinctive matches
    except Exception as e:
        pass

print("\n--- RESULTS ---")
for col, vals in found_cols.items():
    print(f"Column: '{col}' contains: {vals}")

print("\n--- SAMPLE ROWS ---")
print(df.head(5).to_string())
