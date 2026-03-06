import pandas as pd
import sys

f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"
xls = pd.ExcelFile(f_fac)
print("Sheets in Détail_K:", xls.sheet_names)

for sheet in xls.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    df = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=15)
    print(df.head(15))
