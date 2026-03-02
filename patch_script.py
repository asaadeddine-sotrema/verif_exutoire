import re

file_path = "/home/amine/projects/verif_exutoire/modules/verif_heures_ui.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: Add datetime support to parse_tps_travail
old_parse = """def parse_tps_travail(val):
                                    if pd.isna(val) or val == "": return 0.0
                                    if isinstance(val, (int, float)): return float(val)
                                    if isinstance(val, time): return val.hour + val.minute / 60.0"""
new_parse = """def parse_tps_travail(val):
                                    if pd.isna(val) or val == "": return 0.0
                                    if isinstance(val, (int, float)): return float(val)
                                    if isinstance(val, datetime): return val.hour + val.minute / 60.0
                                    if isinstance(val, time): return val.hour + val.minute / 60.0"""
content = content.replace(old_parse, new_parse)

# Fix 2: Remove the "tab_presences" tabs assignment
old_tabs = """tab_anomalies, tab_presences = st.tabs(["⚠️ Anomalies Planning", "🔍 Recherche Présents"])

        with tab_anomalies:"""
new_tabs = """# ⚠️ Anomalies Planning
        if True:"""
content = content.replace(old_tabs, new_tabs)

# Fix 3: Remove the entire 'with tab_presences:' block up to 'elif mode == "📈 Statistiques":'
content = re.sub(r'        with tab_presences:.*?elif mode == "📈 Statistiques":', '        elif mode == "📈 Statistiques":', content, flags=re.DOTALL)

# Fix 4: Directly show details in Statistiques if search_term is set
old_click = """                    if search_term:
                        df_display_stats = df_display_stats[df_display_stats['Employé'] == search_term]
                    
                    event = st.dataframe(
                        df_display_stats.style.format({
                            'Moyenne_Hebdo': '{:.1f}', 
                            'Ecart_Type_Quotidien': '{:.2f}',
                            'Total_Heures_Comptabilisées': '{:.1f}',
                            'Dont_Heures_Travaillées': '{:.1f}',
                            'Jours_Présence_Actifs': '{:.0f}'
                        })
                        .background_gradient(subset=['Moyenne_Hebdo'], cmap='RdYlGn', vmin=30, vmax=40),
                        use_container_width=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    # GESTION DU CLIC
                    if event and event.selection and event.selection.rows:
                        selected_index = event.selection.rows[0]
                        # Attention, st.dataframe trie peut-être différemment.
                        # Mais df_stats est notre source. Si le user a trié dans l'UI, ça peut décaler.
                        # Heureusement st.dataframe retourne l'index du DF d'origine si on ne fait pas gaffe ? 
                        # Non, selection.rows donne l'index de ligne affichée.
                        # Le plus sûr est de récupérer l'employé via iloc sur le DF passé au st.dataframe
                        # MAIS st.dataframe peut avoir été trié par l'utilisateur...
                        # Limitation Streamlit : selection.rows retourne les indices de ligne DU DATAFRAME ORIGINAL
                        
                        selected_row = df_display_stats.iloc[selected_index]
                        nom_employe = selected_row['Employé']
                        
                        st.markdown(f"##### 🔎 Détail pour : **{nom_employe}**")"""

new_click = """                    nom_employe = None
                    if search_term:
                        df_display_stats = df_display_stats[df_display_stats['Employé'] == search_term]
                        nom_employe = search_term
                    
                    event = st.dataframe(
                        df_display_stats.style.format({
                            'Moyenne_Hebdo': '{:.1f}', 
                            'Ecart_Type_Quotidien': '{:.2f}',
                            'Total_Heures_Comptabilisées': '{:.1f}',
                            'Dont_Heures_Travaillées': '{:.1f}',
                            'Jours_Présence_Actifs': '{:.0f}'
                        })
                        .background_gradient(subset=['Moyenne_Hebdo'], cmap='RdYlGn', vmin=30, vmax=40),
                        use_container_width=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    # GESTION DU CLIC OU RECHERCHE DIRECTE
                    if not nom_employe and event and event.selection and event.selection.rows:
                        selected_index = event.selection.rows[0]
                        selected_row = df_display_stats.iloc[selected_index]
                        nom_employe = selected_row['Employé']
                        
                    if nom_employe:
                        st.markdown(f"##### 🔎 Détail pour : **{nom_employe}**")"""

content = content.replace(old_click, new_click)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("done")
