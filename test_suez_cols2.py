import pandas as pd

f_ctc = "/home/amine/projects/Contrôle CTC du 01 AU 28-02-2026.xls"
f_dech = "/home/amine/projects/Contrôle DECHETTERIE du 01 au 28-02-2026.xlsx"

try:
    df_ctc = pd.read_excel(f_ctc, header=None, nrows=10)
    print("CTC First 10 rows:")
    for i, row in df_ctc.iterrows():
        print(f"Row {i}:", row.tolist())
    
    df_dech = pd.read_excel(f_dech, header=None, nrows=10)
    print("\nDECH First 10 rows:")
    for i, row in df_dech.iterrows():
        print(f"Row {i}:", row.tolist())
except Exception as e:
    print(e)
