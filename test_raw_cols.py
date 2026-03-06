import pandas as pd
f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
df_raw = pd.read_excel(f_lb, header=None, nrows=20)
print("Raw rows (first 10):")
print(df_raw.head(10))

# Try to find header
idx = 0
for i, r in df_raw.iterrows():
    row_str = str(r.values).lower()
    if "num ticket" in row_str and "date" in row_str:
        idx = i
        break
print(f"Detected header index: {idx}")

df = pd.read_excel(f_lb, header=idx)
print("Actual columns in DataFrame:")
print(df.columns.tolist())
