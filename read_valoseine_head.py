import pandas as pd
f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"
df = pd.read_excel(f_fac, header=None, nrows=15)
for i, r in df.iterrows():
    print(f"Row {i}:", [str(x) for x in r.values])
