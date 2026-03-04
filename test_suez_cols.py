import pandas as pd

f_ctc = "/home/amine/projects/Contrôle CTC du 01 AU 28-02-2026.xls"
f_dech = "/home/amine/projects/Contrôle DECHETTERIE du 01 au 28-02-2026.xlsx"

try:
    df_ctc = pd.read_excel(f_ctc, header=0, nrows=2)
    print("Columns CTC:")
    print(df_ctc.columns.tolist())
    
    df_dech = pd.read_excel(f_dech, header=0, nrows=2)
    print("\nColumns DECH:")
    print(df_dech.columns.tolist())
except Exception as e:
    print(e)
