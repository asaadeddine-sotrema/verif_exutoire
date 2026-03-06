import pandas as pd
from modules.verif_valene import charger_valoseine

data = {
    'Num TP manuel': ['123', '456'],
    'Date': ['12/02/2024', '13/02/2024'],
    'Tonnages': [1.2, 2.3]
}
df = pd.DataFrame(data)
df.to_excel('test_val.xlsx', index=False)

f = open('test_val.xlsx', 'rb')
df_loaded = charger_valoseine(f)
print("DF loaded:", len(df_loaded))
