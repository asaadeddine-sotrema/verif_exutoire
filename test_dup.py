import pandas as pd

# Create a sample DF with duplicated columns
df = pd.DataFrame({
    'Num Bon': ['123', '123'],
    'Num Ticket': ['A', 'B'],
    'Other': [1, 2]
})

# Make a duplicated column 'Other'
df = pd.concat([df, pd.Series([3, 4], name='Other')], axis=1)

print("Columns:", df.columns)

df['AGG_BON'] = df['Num Bon']

agg_rules = {
    'Num Ticket': 'first',
    'Other': 'first'
}

try:
    df_agg = df.groupby(['AGG_BON'], as_index=False).agg(agg_rules)
    print(df_agg)
except Exception as e:
    import traceback
    traceback.print_exc()
