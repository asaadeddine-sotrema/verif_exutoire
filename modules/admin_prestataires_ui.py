import pandas as pd
import streamlit as st
import json
from modules.models_prestataires import get_prestataires_dynamiques, save_prestataire_dynamique, delete_prestataire_dynamique

def show_admin_prestataires_ui(engine):
    st.header("⚙️ Configuration des Prestataires")
    st.info("Ajoutez ou modifiez vos propres prestataires. Ils apparaîtront ensuite dans la liste du module 'Vérification Tonnages'.")
    
    # 1. Liste des existants
    prestataires = get_prestataires_dynamiques(engine)
    
    if prestataires:
        st.subheader("Prestataires configurés")
        for p in prestataires:
            col_name, col_action = st.columns([4, 1])
            with col_name:
                st.write(f"**{p['nom']}** (Header Ligne: {p['header_row']})")
                with st.expander("Voir Mapping"):
                    st.json(p['mapping'])
            with col_action:
                if st.button("🗑️ Supprimer", key=f"del_{p['id']}"):
                    if delete_prestataire_dynamique(engine, p['id']):
                        st.success(f"Prestataire {p['nom']} supprimé.")
                        st.rerun()
                        
    st.divider()
    
    # 2. Formulaire d'ajout
    st.subheader("➕ Ajouter un nouveau prestataire")
    
    with st.form("form_nouveau_presta"):
        nom_presta = st.text_input("Nom du prestataire/exutoire")
        col_h, _ = st.columns([1, 1])
        with col_h:
            header_row = st.number_input("Ligne d'en-tête (Header) de la facture (ex: 0 pour la 1ère ligne)", min_value=0, value=0)
            
        with st.expander("⚙️ Configuration du Mapping (Technique)", expanded=False):
            st.caption("Entrez le NOM EXACT de la colonne telle qu'elle apparait dans le fichier Excel du prestataire.")
            
            c1, c2 = st.columns(2)
            with c1:
                col_ticket = st.text_input("Colonne: Num Ticket Facture", placeholder="Ex: N° Ticket")
                col_bon = st.text_input("Colonne: Num Bon", placeholder="Ex: Ref Bon")
                col_date = st.text_input("Colonne: Date", placeholder="Ex: Date Pesée")
                col_poids = st.text_input("Colonne: Poids", placeholder="Ex: Poids Net")
                
            with c2:
                col_client = st.text_input("Colonne: Client", placeholder="Ex: Code Client")
                col_matiere = st.text_input("Colonne: Matière", placeholder="Ex: Produit")
                col_immat = st.text_input("Colonne: Immatriculation", placeholder="Ex: Immat")
                date_format = st.selectbox("Format de Date de la Facture", ["DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"])
            
        st.markdown("#### Configuration Avancée")
        c_multi_poids = st.checkbox("Le poids facturé est exprimé en Kilos (L'application le divisera par 1000)")
        
        submitted = st.form_submit_button("💾 Sauvegarder ce modèle", type="primary")
        
        if submitted:
            if nom_presta and col_ticket and col_date and col_poids and col_client and col_matiere:
                # Built configuration dictionary
                mapping_config = {
                    "mapping": {
                        "Ticket": str(col_ticket).strip(),
                        "Bon": str(col_bon).strip(),
                        "Date": str(col_date).strip(),
                        "Poids": str(col_poids).strip(),
                        "Client": str(col_client).strip(),
                        "Matiere": str(col_matiere).strip(),
                        "Immatriculation": str(col_immat).strip()
                    },
                    "options": {
                        "date_format": date_format,
                        "poids_en_kilos": c_multi_poids
                    }
                }
                
                if save_prestataire_dynamique(engine, nom_presta.strip().upper(), header_row, mapping_config):
                    st.success(f"Modèle {nom_presta} sauvegardé avec succès !")
                    st.rerun()
                else:
                    st.error("Erreur lors de la sauvegarde (Le nom existe peut-être déjà ?).")
            else:
                st.warning("Veuillez remplir tous les champs obligatoires (Ticket, Date, Poids, Client, Matiere).")

