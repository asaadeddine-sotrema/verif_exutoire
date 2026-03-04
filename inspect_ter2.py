import sys
import pandas as pd
f_ter = "/home/amine/projects/77AC61D9_0F9A_24C5_A822_3DA2F09E9D00_20260303-1512.xls"
df_ter = pd.read_excel(f_ter)
print("Columns:", df_ter.columns.tolist())
print(df_ter.head())
