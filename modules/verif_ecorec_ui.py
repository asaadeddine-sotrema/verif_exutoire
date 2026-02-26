import streamlit as st
import pandas as pd
from io import BytesIO

def show_verif_ecorec_ui():
    """
    Interface utilisateur Streamlit pour l'outil de vérification Ecorec.
    Permet d'uploader les fichiers Ecorec et Contrôlé, de lancer l'analyse,
    et de visualiser / exporter les résultats.
    """
    st.title("♻️ Vérification Ecorec")
    st.markdown("Cet outil permet de comparer les tonnages exportés depuis Ecorec avec ceux du fichier corrigé par l'exploitation.")
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Fichier Ecorec")
        st.caption("Fichier contenant les données Ecorec brutes (.xls)")
        f_ecorec = st.file_uploader("Upload Ecorec", type=['xls', 'xlsx'], key="eco_u")
        
    with c2:
        st.subheader("Fichier Contrôlé (Exploitation)")
        st.caption("Fichier mensuel contenant les tonnages contrôlés (.xlsx)")
        f_controle = st.file_uploader("Upload Contrôlé", type=['xls', 'xlsx'], key="ctrl_u")

    if st.button("🚀 Lancer la Vérification", type="primary", use_container_width=True):
        if not f_ecorec or not f_controle:
            st.error("Veuillez importer les deux fichiers avant de lancer l'analyse.")
        else:
            with st.spinner("Analyse et croisement des données en cours..."):
                try:
                    # Import the logic dynamically to avoid circular issues
                    from modules.verif_ecorec import process_ecorec
                    
                    # Run processing
                    df_result = process_ecorec(f_ecorec, f_controle)
                    
                    if df_result.empty:
                        st.warning("Aucune donnée trouvée ou erreur de format. Vérifiez vos fichiers.")
                        st.session_state['df_ecorec_result'] = None
                    elif "Erreur" in df_result.columns:
                        st.error(f"Erreur lors du traitement: {df_result['Erreur'].iloc[0]}")
                        st.session_state['df_ecorec_result'] = None
                    else:
                        st.session_state['df_ecorec_result'] = df_result
                        st.success("Analyse terminée !")
                except Exception as e:
                    st.error(f"Une erreur inattendue s'est produite: {str(e)}")

    # Affichage des résultats s'ils existent en session
    if 'df_ecorec_result' in st.session_state and st.session_state['df_ecorec_result'] is not None:
        st.divider()
        df = st.session_state['df_ecorec_result']
        
        st.subheader("📊 Résultats de la comparaison")
        
        # KPIs
        nb_total = len(df)
        nb_ok = len(df[df['Statut'] == 'OK'])
        nb_anomalies = len(df[df['Statut'] != 'OK'])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Lignes Rapprochées", nb_total)
        col2.metric("Lignes OK", nb_ok)
        col3.metric("Anomalies (Écarts / Manquants)", nb_anomalies, delta=-nb_anomalies, delta_color="inverse")
        
        # Filtre optionnel
        filter_status = st.radio("Filtrer l'affichage :", ["Tout afficher", "Anomalies Uniquement"], horizontal=True)
        
        df_view = df.copy()
        if filter_status == "Anomalies Uniquement":
            df_view = df_view[df_view['Statut'] != 'OK']
            
        def color_status(val):
            color = 'green' if val == 'OK' else 'red'
            return f'color: {color}'
            
        if not df_view.empty:
            st.dataframe(
                df_view.style.map(color_status, subset=['Statut']), 
                use_container_width=True,
                height=500
            )
            
            # Export vers Excel
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Verification_Ecorec')
                # Auto-ajustement des colonnes
                worksheet = writer.sheets['Verification_Ecorec']
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
                    
            st.download_button(
                label="📥 Télécharger le rapport Excel",
                data=buffer.getvalue(),
                file_name="Anomalies_Ecorec.xlsx",
                mime="application/vnd.ms-excel",
                type="primary"
            )
        else:
            st.info("Aucune donnée à afficher pour ce filtre.")
