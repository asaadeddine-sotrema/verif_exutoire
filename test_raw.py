import pandas as pd

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"

print("--- LB ---")
df_lb_raw = pd.read_excel(f_lb, header=None, nrows=10)
print(df_lb_raw.head(10))

print("\n--- FAC ---")
df_fac_raw = pd.read_excel(f_fac, header=None, nrows=10)
print(df_fac_raw.head(10))
