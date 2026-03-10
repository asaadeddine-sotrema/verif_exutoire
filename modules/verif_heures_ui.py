import streamlit as st
import pandas as pd
import numpy as np
import io
from io import BytesIO
import matplotlib.pyplot as plt
from datetime import timedelta, datetime, time
from sqlalchemy import text, MetaData, Table, Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
import scipy.stats as stats
TABLE_HEURES_HEBDO = "suivi_activite_hebdo"
TABLE_PRESENCES_DAILY = "suivi_presences_quotidien"
TABLE_ANOMALIES_PLANNING = "suivi_anomalies_planning"
TABLE_ROLES = "referentiel_employes"

def style_zebra(styler):
    """Applique une alternance de couleurs (Zebra Striping) sur un objet Styler."""
    return styler.apply(lambda x: ['background-color: rgba(128, 128, 128, 0.1)' if i % 2 != 0 else '' for i in range(len(x))], axis=0)

def save_daily_results(df_daily, engine):
    """Sauvegarde les détails quotidiens pour la gestion de flotte."""
    if df_daily.empty:
        return
    
    try:
        # [NEW] SCHEMA MIGRATION : ADD COLUMNS IF MISSING
        # On utilise une inspection basique pour voir si les colonnes existent
        from sqlalchemy import inspect
        try:
            inspector = inspect(engine)
            # Attention: get_columns peut échouer si la table n'existe pas encore.
            if inspector.has_table(TABLE_PRESENCES_DAILY):
                existing_cols = [c['name'] for c in inspector.get_columns(TABLE_PRESENCES_DAILY)]
                with engine.begin() as conn:
                    if 'Heure_Debut' not in existing_cols:
                        conn.execute(text(f'ALTER TABLE {TABLE_PRESENCES_DAILY} ADD COLUMN "Heure_Debut" TEXT'))
                    if 'Heure_Fin' not in existing_cols:
                        conn.execute(text(f'ALTER TABLE {TABLE_PRESENCES_DAILY} ADD COLUMN "Heure_Fin" TEXT'))
                    if 'Pause' not in existing_cols:
                         conn.execute(text(f'ALTER TABLE {TABLE_PRESENCES_DAILY} ADD COLUMN "Pause" TEXT'))
                    # [NEW] Pauses start/end
                    if 'Heure_Debut_Pause' not in existing_cols:
                        conn.execute(text(f'ALTER TABLE {TABLE_PRESENCES_DAILY} ADD COLUMN "Heure_Debut_Pause" TEXT'))
                    if 'Heure_Fin_Pause' not in existing_cols:
                        conn.execute(text(f'ALTER TABLE {TABLE_PRESENCES_DAILY} ADD COLUMN "Heure_Fin_Pause" TEXT'))
                        
        except Exception as e_mig:
            print(f"Migration error (ignored if table creates next): {e_mig}")

        metadata = MetaData()
        table_daily = Table(
            TABLE_PRESENCES_DAILY,
            metadata,
            Column('id', Integer, primary_key=True),
            Column('Date', DateTime),
            Column('Employé', String),
            Column('Code', String),
            Column('Heures', Float),
            Column('Semaine', String),
            Column('Heure_Debut', String),
            Column('Heure_Fin', String),
            Column('Pause', String),
            Column('Heure_Debut_Pause', String),
            Column('Heure_Fin_Pause', String),
            Column('Date_Import', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            UniqueConstraint('Date', 'Employé', name='uk_date_employe')
        )
        metadata.create_all(engine)
        
        # Mapping des colonnes
        records = []
        for _, r in df_daily.iterrows():
            # Extraction sécurisée des temps
            def format_time_val(val):
                if pd.isna(val) or val == "": return ""
                s = str(val)
                # Si c'est un timedelta (ex: "0 days 09:00:00")
                if "days" in s:
                     # On essaie de split pour garder juste l'heure
                     parts = s.split('days')
                     if len(parts) > 1:
                         return parts[-1].strip()
                
                # Si c'est un datetime complet (avec la date 1900-01-01 souvent), on ne garde que l'heure
                try:
                    # Essayer de parser comme datetime
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.notna(dt):
                        return dt.strftime('%H:%M:%S')
                except:
                    pass
                # Sinon on renvoie tel quel (ou on clean manuellement si format bizarre)
                return s
            
            # Recherche flexible des colonnes de pause
            h_debut_pause = ""
            for col in ['HeureDebutPause', 'DebutPause', 'Heure_Debut_Pause']:
                if col in r:
                    h_debut_pause = format_time_val(r[col])
                    break
            
            h_fin_pause = ""
            for col in ['HeureFinPause', 'FinPause', 'Heure_Fin_Pause']:
                if col in r:
                    h_fin_pause = format_time_val(r[col])
                    break

            records.append({
                "Date": r['Date'],
                "Employé": f"{r['Nom Personnel']} {r['prenom']}",
                "Code": str(r['CodeTravail']).strip().upper(),
                "Heures": round(float(r['Duree']), 2),
                "Semaine": str(r['Semaine']),
                "Heure_Debut": format_time_val(r.get('HeureDebut')),
                "Heure_Fin": format_time_val(r.get('HeureFin')),
                "Pause": format_time_val(r.get('Pause')),
                "Heure_Debut_Pause": h_debut_pause,
                "Heure_Fin_Pause": h_fin_pause
            })
            
        with engine.begin() as conn:
            stmt = insert(table_daily).values(records)
            update_dict = {
                "Code": stmt.excluded.Code,
                "Heures": stmt.excluded.Heures,
                "Semaine": stmt.excluded.Semaine,
                "Heure_Debut": stmt.excluded.Heure_Debut,
                "Heure_Fin": stmt.excluded.Heure_Fin,
                "Pause": stmt.excluded.Pause,
                "Heure_Debut_Pause": stmt.excluded.Heure_Debut_Pause,
                "Heure_Fin_Pause": stmt.excluded.Heure_Fin_Pause,
                "Date_Import": text("CURRENT_TIMESTAMP")
            }
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['Date', 'Employé'],
                set_=update_dict
            )
            conn.execute(upsert_stmt)
            
    except Exception as e:
        st.error(f"Erreur sauvegarde quotidienne : {e}")

def save_planning_anomalies(df_anomalies, engine):
    """Sauvegarde les anomalies planning (absents du relevé d'heures)."""
    if df_anomalies.empty:
        return

    try:
        metadata = MetaData()
        table_anom = Table(
            TABLE_ANOMALIES_PLANNING,
            metadata,
            Column('id', Integer, primary_key=True),
            Column('Date', DateTime),
            Column('Employé', String),
            Column('Qualification', String),
            Column('Affectation', String),
            Column('Statut', String),
            Column('Date_Import', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            UniqueConstraint('Date', 'Employé', name='uk_anom_date_employe')
        )
        metadata.create_all(engine)

        records = []
        for _, r in df_anomalies.iterrows():
            # Conversion date format dd/mm/yyyy -> datetime object
            d_obj = pd.to_datetime(r['Date'], format='%d/%m/%Y', errors='coerce')
            if pd.isna(d_obj): continue

            records.append({
                "Date": d_obj,
                "Employé": str(r['Nom (Planning)']).strip().upper(),
                "Qualification": str(r.get('Qualification', '')),
                "Affectation": str(r.get('Affectation', '')),
                "Statut": str(r.get('Statut', 'Absent'))
            })

        if not records: return

        with engine.begin() as conn:
            # [FIX] Delete existing anomalies for the dates in the new dataset to avoid stale data
            # Get Min/Max dates from the new data
            dates = [rec["Date"] for rec in records]
            if dates:
                min_date = min(dates)
                max_date = max(dates)
                delete_stmt = text(f'DELETE FROM {TABLE_ANOMALIES_PLANNING} WHERE "Date" >= :min_d AND "Date" <= :max_d')
                conn.execute(delete_stmt, {"min_d": min_date, "max_d": max_date})

            stmt = insert(table_anom).values(records)
            update_dict = {
                "Qualification": stmt.excluded.Qualification,
                "Affectation": stmt.excluded.Affectation,
                "Statut": stmt.excluded.Statut,
                "Date_Import": text("CURRENT_TIMESTAMP")
            }
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['Date', 'Employé'],
                set_=update_dict
            )
            conn.execute(upsert_stmt)

    except Exception as e:
        st.error(f"Erreur sauvegarde anomalies planning : {e}")

def load_planning_anomalies(engine, start_date, end_date):
    """Charge les anomalies planning sur une période donnée."""
    try:
        with engine.connect() as conn:
            res = conn.execute(text(f"SELECT to_regclass('public.{TABLE_ANOMALIES_PLANNING}')"))
            if res.scalar() is None:
                return pd.DataFrame() # Table not created yet
        
        query = f"""
            SELECT "Date", "Employé", "Qualification", "Affectation", "Statut"
            FROM {TABLE_ANOMALIES_PLANNING}
            WHERE "Date" >= :start AND "Date" <= :end
            ORDER BY "Date" ASC
        """
        return pd.read_sql(text(query), engine, params={"start": start_date, "end": end_date})
    except Exception as e:
        # Silent fail if table doesn't exist or other error, return empty
        return pd.DataFrame()

def save_week_results(df_f, engine):
    """Sauvegarde les agrégats hebdomadaires."""
    if df_f.empty:
        st.warning("Rien à sauvegarder.")
        return
    
    try:
        metadata = MetaData()
        table_heures = Table(
            TABLE_HEURES_HEBDO,
            metadata,
            Column('id', Integer, primary_key=True),
            Column('Semaine', String),
            Column('Employé', String),
            Column('Jours_Travaillés', Integer),
            Column('Heures_Travaillees', Float),
            Column('Objectif_Heures', Float),
            Column('Ecart', Float),
            Column('Statut', String),
            Column('Date_Import', DateTime, server_default=text('CURRENT_TIMESTAMP')),
            UniqueConstraint('Employé', 'Semaine', name='uk_employe_semaine')
        )
        
        # Create table if not exists (handled by SQLAlchemy)
        metadata.create_all(engine)
        
        records = df_f.to_dict(orient='records')
        clean_records = []
        for r in records:
            clean_records.append({
                "Semaine": r.get('Semaine'),
                "Employé": r.get('Employé'),
                "Jours_Travaillés": r.get('Jours Travaillés'),
                "Heures_Travaillees": r.get('Heures Travaillées'),
                "Objectif_Heures": r.get('Objectif (h)'),
                "Ecart": r.get('Écart'),
                "Statut": "OK" if r.get('Écart', 0) >= -0.1 else "KO"
            })
            
        with engine.begin() as conn: # connection + transaction
            stmt = insert(table_heures).values(clean_records)
            
            # Upsert: Update values if conflict on (Employé, Semaine)
            update_dict = {
                "Jours_Travaillés": stmt.excluded.Jours_Travaillés,
                "Heures_Travaillees": stmt.excluded.Heures_Travaillees,
                "Objectif_Heures": stmt.excluded.Objectif_Heures,
                "Ecart": stmt.excluded.Ecart,
                "Statut": stmt.excluded.Statut,
                "Date_Import": text("CURRENT_TIMESTAMP")
            }
            
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['Employé', 'Semaine'], # Safer than constraint name if created manually before
                set_=update_dict
            )
            
            res = conn.execute(upsert_stmt)
            st.success(f"{res.rowcount} lignes sauvegardées/mises à jour en base.")
            
    except Exception as e:
        st.error(f"Erreur sauvegarde : {e}")

def load_history_data(engine):
    try:
        # Check if table exists first
        with engine.connect() as conn:
            res = conn.execute(text(f"SELECT to_regclass('public.{TABLE_HEURES_HEBDO}')"))
            if res.scalar() is None:
                return pd.DataFrame() # Table doesn't exist yet
        
        query = f'SELECT * FROM {TABLE_HEURES_HEBDO} ORDER BY "id" DESC'
        return pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"Erreur chargement historique hebdomadaire : {e}")
        return pd.DataFrame()

def load_daily_data(engine, start_date, end_date):
    try:
        with engine.connect() as conn:
            res = conn.execute(text(f"SELECT to_regclass('public.{TABLE_PRESENCES_DAILY}')"))
            if res.scalar() is None:
                return pd.DataFrame()
        
        query = f"""
            SELECT * FROM {TABLE_PRESENCES_DAILY} 
            WHERE "Date" >= :start AND "Date" <= :end
        """
        return pd.read_sql(text(query), engine, params={"start": start_date, "end": end_date})
    except Exception as e:
        st.error(f"Erreur chargement historique quotidien : {e}")
        return pd.DataFrame()

def get_date_extremums(engine):
    """Récupère les dates min et max présentes dans la base de données."""
    try:
        # Check if table exists first
        with engine.connect() as conn:
            res_exists = conn.execute(text(f"SELECT to_regclass('public.{TABLE_PRESENCES_DAILY}')"))
            if res_exists.scalar() is None:
                return None, None
            
            res = conn.execute(text(f'SELECT MIN("Date"), MAX("Date") FROM {TABLE_PRESENCES_DAILY}'))
            row = res.fetchone()
            if row and row[0] and row[1]:
                # On s'assure que ce sont des objets date Python
                d_min = row[0].date() if hasattr(row[0], 'date') else pd.to_datetime(row[0]).date()
                d_max = row[1].date() if hasattr(row[1], 'date') else pd.to_datetime(row[1]).date()
                return d_min, d_max
    except Exception:
        pass
    return None, None

def save_employee_roles(df_plan, engine):
    """Sauvegarde les qualifications détectées dans le planning."""
    if df_plan.empty: return

    try:
        metadata = MetaData()
        table_roles = Table(
            TABLE_ROLES,
            metadata,
            Column('Employé', String, primary_key=True),
            Column('Qualification', String),
            Column('Last_Updated', DateTime, server_default=text('CURRENT_TIMESTAMP'))
        )
        metadata.create_all(engine)

        # Extraction des couples uniques (Nom, Qualification)
        # On suppose que df_plan a déjà été nettoyé/filtré en amont ou on le refait ici
        records = []
        # On itère pour trouver les qualifications
        # On s'attend à ce que df_plan ait 'Chauffeur' et 'Qualification' (colonnes du fichier Excel)
        
        # Mapping si nécessaire, mais ici on va scanner le DF brut ou semi-traité
        # Dans le code existant, on a 'Chauffeur' et 'Qualification'
        if 'Chauffeur' in df_plan.columns and 'Qualification' in df_plan.columns:
            # On nettoie et on dédoublonne
            subset = df_plan[['Chauffeur', 'Qualification']].drop_duplicates()
            for _, row in subset.iterrows():
                nom = str(row['Chauffeur']).strip().upper()
                qualif = str(row['Qualification']).strip().upper()
                
                if nom and qualif and nom != 'NAN' and qualif != 'NAN':
                     records.append({
                        "Employé": nom,
                        "Qualification": qualif
                    })
        
        if not records: return

        with engine.begin() as conn:
            stmt = insert(table_roles).values(records)
            update_dict = {
                "Qualification": stmt.excluded.Qualification,
                "Last_Updated": text("CURRENT_TIMESTAMP")
            }
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['Employé'],
                set_=update_dict
            )
            conn.execute(upsert_stmt)
            
    except Exception as e:
        print(f"Erreur sauvegarde rôles : {e}")

def load_employee_roles(engine):
    """Charge le dictionnaire {Employé: Qualification}."""
    try:
        with engine.connect() as conn:
             res = conn.execute(text(f"SELECT to_regclass('public.{TABLE_ROLES}')"))
             if res.scalar() is None: return {}
             
             query = f"SELECT * FROM {TABLE_ROLES}"
             df = pd.read_sql(text(query), conn)
             if df.empty: return {}
             
             # Retourne un dict pour lookup rapide
             return dict(zip(df['Employé'], df['Qualification']))
    except Exception:
        return {}


def show_verif_heures_ui(engine=None, mode="Import des fichiers"):
    st.title("👥 Gestion de l'Activité")
    
    # [NEW] Récupération des limites de dates pour le calendrier
    d_min, d_max = get_date_extremums(engine) if engine else (None, None)
    
    st.markdown("---")
    
    if mode == "📥 Import des fichiers":
        st.subheader("📥 Import des fichiers")
        with st.expander("❓ Besoin d'aide ?", expanded=False):
            st.markdown("""
            **Chemin ECOREC :**  
            `(RH / Outil Activité)`
            """)
        st.info("Validation de la cohérence des flux et calcul des écarts.")
    
        def clear_results():
            if 'verif_heures_results' in st.session_state:
                del st.session_state['verif_heures_results']

        uploaded_file = st.file_uploader("Charger le fichier Excel des heures", type=["xlsx", "xls"], key="uploader_heures", on_change=clear_results)
        uploaded_planning = st.file_uploader("Charger le fichier Planning (Optionnel)", type=["xlsx", "xls"], key="uploader_planning", on_change=clear_results)
        
        if uploaded_file:
            if st.button("Lancer la vérification", type="primary"):
                try:
                    # 1. On charge les données
                    df_f = pd.read_excel(uploaded_file, header=2)
                    df_f.columns = df_f.columns.str.strip()
                    
                    # Vérif des colonnes
                    colonnes_obligatoires = ['Date', 'Nom Personnel', 'prenom', 'CodeTravail']
                    colonnes_manquantes = [col for col in colonnes_obligatoires if col not in df_f.columns]
                    
                    if colonnes_manquantes:
                        st.error(f"Erreur : Il manque des colonnes importantes : {', '.join(colonnes_manquantes)}")
                    else:
                        # Conversion des dates
                        df_f['Date'] = pd.to_datetime(df_f['Date'], errors='coerce')
                        df_f = df_f.dropna(subset=['Date'])
                        
                        if df_f.empty:
                            st.warning("Attention, je ne trouve aucune date valide.")
                        else:
                            if True:
                                liste_erreurs = []
                                jours_fr = {0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi', 4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'}
                                
                                # --- Préparation des données pour l'analyse des jours (Semaines) ---
                                map_semaine_dates = {}
                                if 'Semaine' in df_f.columns:
                                    df_f['Semaine'] = df_f['Semaine'].astype(str)
                                    semaines_uniques = df_f['Semaine'].unique()
                                    for s in semaines_uniques:
                                        dates_semaine = df_f[df_f['Semaine'] == s]['Date']
                                        if not dates_semaine.empty:
                                            min_date = dates_semaine.min()
                                            start_week = min_date - timedelta(days=min_date.weekday())
                                            end_week = start_week + timedelta(days=6)
                                            map_semaine_dates[s] = f"Du {start_week.strftime('%d/%m')} au {end_week.strftime('%d/%m')}"
                                        else:
                                            map_semaine_dates[s] = f"Semaine {s}"
                                
                                compte_hebdo = df_f.groupby(['Nom Personnel', 'prenom', 'Semaine'])['Date'].nunique().reset_index()
                                compte_hebdo.columns = ['Nom Personnel', 'prenom', 'Semaine', 'NombreJours']
                                jours_details = df_f.groupby(['Nom Personnel', 'prenom', 'Semaine'])['Date'].unique().reset_index()

                                # --- ANALYSE CROISÉE PLANNING (Si fichier fourni) ---
                                anomalies_planning = []
                                if uploaded_planning:
                                    try:
                                        df_plan = pd.read_excel(uploaded_planning, header=2)
                                        df_plan.columns = df_plan.columns.str.strip()
                                        
                                        valid_qualifs = ['CHAUFFEUR', 'CHAUFFEUR 26T', 'CHAUFFEUR GRUE', 'EQUIPIER DE COLLECTE', 'CHAUFFEUR SPL', 'Apprenti']
                                        
                                        if 'Qualification' in df_plan.columns and 'Affectation' in df_plan.columns and 'Date' in df_plan.columns:
                                            df_plan['Date'] = pd.to_datetime(df_plan['Date'], errors='coerce')
                                            df_plan['Qualification'] = df_plan['Qualification'].astype(str).str.strip().str.upper()
                                            df_plan['Affectation'] = df_plan['Affectation'].astype(str).str.strip().str.upper()

                                            # [UPDATED] Filtres demandés
                                            # Affectation : CHAUFFEUR ou EQUIPIER
                                            # Qualification : Contient CHAUFFEUR, EQUIPIER DE COLLECTE, ou APPRENTI
                                            
                                            def check_qualification(val):
                                                val = str(val).upper()
                                                keywords = ['CHAUFFEUR', 'EQUIPIER DE COLLECTE', 'APPRENTI']
                                                return any(k in val for k in keywords)

                                            mask = (
                                                df_plan['Affectation'].isin(['CHAUFFEUR', 'EQUIPIER']) &
                                                df_plan['Qualification'].apply(check_qualification) &
                                                df_plan['Date'].notna()
                                            )
                                            df_plan_filtered = df_plan[mask].copy()
                                            
                                            if df_plan_filtered.empty:
                                                st.warning("Aucune ligne valide trouvée dans le planning (Vérifiez Qualifications ET Affectations).")
                                            else:
                                                for idx, row_p in df_plan_filtered.iterrows():
                                                    date_p = row_p['Date']
                                                    nom_p = row_p['Chauffeur']
                                                    qualif_p = row_p.get('Qualification', 'N/A')
                                                    
                                                    nom_p_clean = str(nom_p).strip().upper()
                                                    if nom_p_clean.startswith('-'): nom_p_clean = nom_p_clean[1:]
                                                    
                                                    df_day_hours = df_f[df_f['Date'] == date_p]
                                                    found = False
                                                    if not df_day_hours.empty:
                                                        noms_hours = df_day_hours['Nom Personnel'].astype(str).str.strip().unique()
                                                        for n_h in noms_hours:
                                                            n_h_upper = n_h.upper()
                                                            if not n_h_upper: continue # [FIX] Skip empty strings to prevent false positives ("" in "Name" is True)
                                                            
                                                            if nom_p_clean == n_h_upper: # Direct match first
                                                                found = True
                                                                break
                                                            if len(n_h_upper) > 2 and (nom_p_clean in n_h_upper or n_h_upper in nom_p_clean): # Partial match only if length sufficient
                                                                found = True
                                                                break
                                                    
                                                    if not found:
                                                        anomalies_planning.append({
                                                            "Date": date_p.strftime('%d/%m/%Y'),
                                                            "Nom (Planning)": nom_p,
                                                            "Qualification": qualif_p,
                                                            "Affectation": row_p['Affectation'],
                                                            "Statut": "Absent du fichier Heures"
                                                        })
                                        else:
                                            st.warning("Format Planning invalide: Colonnes 'Date', 'Affectation', 'Qualification', 'Chauffeur' requises.")
                                    except Exception as e_plan:
                                        st.warning(f"Impossible de traiter le planning : {e_plan}")
                                    
                                    # [NEW] Sauvegarde des Rôles pour le futur
                                    if engine and not df_plan.empty:
                                         save_employee_roles(df_plan, engine)

                                def get_jours_travailles_str(nom, prenom, semaine):
                                    if jours_details is None or jours_details.empty:
                                        return ""
                                    try:
                                        dates = jours_details[
                                            (jours_details['Nom Personnel'] == nom) & 
                                            (jours_details['prenom'] == prenom) & 
                                            (jours_details['Semaine'] == semaine)
                                        ]['Date'].values
                                        
                                        if len(dates) > 0:
                                            dates_list = pd.to_datetime(dates[0])
                                            if isinstance(dates_list, pd.Timestamp): dates_list = [dates_list]
                                            dates_list = sorted(list(dates_list))
                                            noms_jours = [jours_fr[d.weekday()] for d in dates_list]
                                            return ", ".join(list(dict.fromkeys(noms_jours)))
                                    except Exception:
                                        return ""
                                    return ""
                                    
                                def get_periode_str(semaine):
                                    return map_semaine_dates.get(semaine, f"Semaine {semaine}")
                                
                                # --- Contrôle 2 : Infos Manquantes ---
                                lignes_infos_manquantes = []
                                codes_absence = ['AT', 'CP', 'R', 'Férié', 'MAL', 'CSS', 'RTT', 'ABS', 'RH', 'CAnc', 'RC', 'JNFTP', 'F','FOR']
                                
                                for index, row in df_f.iterrows():
                                    problemes = []
                                    code_travail = str(row['CodeTravail']).strip() if pd.notna(row['CodeTravail']) else ""
                                    heure_debut = row['HeureDebut']
                                    heure_fin = row['HeureFin']
                                    
                                    if not code_travail:
                                        problemes.append("Code Travail oublié")
                                    if code_travail.upper() == 'P':
                                        if pd.isna(heure_debut) or str(heure_debut).strip() == '':
                                            problemes.append("Il manque l'Heure de Début (Code P)")
                                        if pd.isna(heure_fin) or str(heure_fin).strip() == '':
                                            problemes.append("Il manque l'Heure de Fin (Code P)")
                                    
                                    est_absence = any(code in code_travail.upper() for code in codes_absence)
                                    if code_travail.upper() != 'P' and not est_absence and code_travail != "":
                                         if pd.isna(heure_debut): problemes.append("Heure Début manquante")
                                         if pd.isna(heure_fin): problemes.append("Heure Fin manquante")
                                    
                                    if problemes:
                                        date_str = row['Date'].strftime('%d/%m/%Y')
                                        raw_semaine = str(row['Semaine']) if 'Semaine' in df_f.columns else ""
                                        periode = get_periode_str(raw_semaine)
                                        liste_jours = get_jours_travailles_str(row['Nom Personnel'], row['prenom'], raw_semaine)
                                        details = ', '.join(problemes)
            
                                        lignes_infos_manquantes.append({
                                            "Ligne Excel": index + 4,
                                            "Employé": f"{row['Nom Personnel']} {row['prenom']}",
                                            "Date": date_str,
                                            "Code": code_travail,
                                            "Problèmes": details
                                        })
                                        liste_erreurs.append({
                                            "Type Erreur": "Info Manquante",
                                            "Employé": f"{row['Nom Personnel']} {row['prenom']}",
                                            "Semaine": periode,
                                            "Jours Travaillés": liste_jours,
                                            "Détails": f"{date_str} | {details}"
                                        })
            
                                # --- Synthèse 35h ---
                                def parse_tps_travail(val):
                                    if pd.isna(val) or val == "": return 0.0
                                    if isinstance(val, (int, float)): return float(val)
                                    if hasattr(val, 'components'): # pd.Timedelta
                                        return val.components.hours + val.components.minutes / 60.0 + (val.components.days * 24.0)
                                    if isinstance(val, datetime): return val.hour + val.minute / 60.0
                                    if isinstance(val, time): return val.hour + val.minute / 60.0
                                    if isinstance(val, str):
                                        val_str = val.strip().replace(',', '.')
                                        try:
                                            return float(val_str)
                                        except ValueError:
                                            pass
                                        try:
                                            t = datetime.strptime(val.strip(), "%H:%M:%S").time()
                                            return t.hour + t.minute / 60.0
                                        except ValueError:
                                            try:
                                                t = datetime.strptime(val.strip(), "%H:%M").time()
                                                return t.hour + t.minute / 60.0
                                            except ValueError:
                                                pass
                                    return 0.0
            
                                col_tps = None
                                for col in df_f.columns:
                                    if str(col).lower().replace(" ", "").replace("_", "") == "tpstravail":
                                        col_tps = col
                                        break
                                        
                                if col_tps:
                                    df_f['Duree'] = df_f[col_tps].apply(parse_tps_travail)
                                else:
                                    st.error("❌ Colonne 'TpsTravail' introuvable.")
                                    df_f['Duree'] = 0.0
            
                                synthese_35h = []
                                synthese_ok = []
                                
                                if 'Semaine' in df_f.columns:
                                    grouped = df_f.groupby(['Nom Personnel', 'prenom', 'Semaine'])
                                    for (nom, prenom, semaine), group in grouped:
                                        total_heures = 0.0
                                        target_heures = 0.0
                                        
                                        jours_groupe = group.groupby('Date')
                                        jours_travail_p_only = []
                                        
                                        for date, day_group in jours_groupe:
                                            codes_jour = day_group['CodeTravail'].dropna().astype(str).str.strip().str.upper().unique()
                                            if 'P' in codes_jour:
                                                # Si l'employé est marqué en 'P', on considère le jour comme travaillé.
                                                target_heures += 7.0
                                                jours_travail_p_only.append(date)
                                                total_heures += day_group['Duree'].sum()
                                            # If it's not Code P (Absence, RTT, etc.), we don't add to jours_travail_p_only
                                        
                                        jours_travailles_count = len(jours_travail_p_only)
                                        periode = get_periode_str(semaine)
                                        liste_jours_str = get_jours_travailles_str(nom, prenom, semaine)
            
                                        entry_data = {
                                            "Employé": f"{nom} {prenom}",
                                            "Semaine": periode,
                                            "Jours Travaillés": jours_travailles_count,
                                            "Heures Travaillées": round(total_heures, 2),
                                            "Objectif (h)": target_heures,
                                            "Écart": round(total_heures - target_heures, 2),
                                            "Détails Jours": liste_jours_str
                                        }
            
                                        if total_heures < (target_heures - 0.1):
                                            synthese_35h.append(entry_data)
                                            liste_erreurs.append({
                                                "Type Erreur": "Moins de 35h",
                                                "Employé": f"{nom} {prenom}",
                                                "Semaine": periode,
                                                "Jours Travaillés": liste_jours_str,
                                                "Détails": f"{round(total_heures, 2)}h vs {target_heures}h (-{abs(round(total_heures - target_heures, 2))}h)"
                                            })
                                        else:
                                            synthese_ok.append(entry_data)
 
                                # Store in Session State
                                st.session_state['verif_heures_results'] = {
                                    "compte_hebdo": compte_hebdo,
                                    "liste_erreurs": liste_erreurs,
                                    "lignes_infos_manquantes": lignes_infos_manquantes,
                                    "synthese_35h": synthese_35h,
                                    "synthese_ok": synthese_ok,
                                    "map_semaine_dates": map_semaine_dates,
                                    "jours_details": jours_details,
                                    "raw_df": df_f, # Added for daily save
                                    "anomalies_planning": anomalies_planning,
                                    "analyzed": True
                                }

                except Exception as e:
                    st.error(f"Oups, une erreur s'est produite : {e}")
 
            # --- DISPLAY RESULTS (Persistant) ---
            if 'verif_heures_results' in st.session_state and st.session_state['verif_heures_results'].get("analyzed"):
                results = st.session_state['verif_heures_results']
                st.success("✅ Fichier analysé. Résultats disponibles en mémoire.")

                # --- RESULTATS PLANNING (Visible immédiatement) ---
                anomalies_plan = results.get("anomalies_planning")

                # --- Sauvegarde en Base ---
                st.markdown("---")
                st.subheader("📦 Archivage des Données")
                
                col_save, col_info = st.columns([1, 2])
                with col_save:
                    if st.button("💾 Enregistrer les données", type="primary", key="save_btn_import"):
                        try:
                            # 1. Save Aggregates
                            all_results = results["synthese_35h"] + results["synthese_ok"]
                            df_save = pd.DataFrame(all_results)
                            save_week_results(df_save, engine)
                            
                            # 2. Save Daily Details
                            if "raw_df" in results:
                                save_daily_results(results["raw_df"], engine)

                            # 3. [NEW] Save Planning Anomalies
                            if results.get("anomalies_planning"):
                                df_anoms_save = pd.DataFrame(results["anomalies_planning"])
                                save_planning_anomalies(df_anoms_save, engine)
                            
                            st.success("Données archivées avec succès dans la base.")
                        except Exception as e_save:
                            st.error(f"Erreur d'enregistrement : {e_save}")
                            
                with col_info:
                    st.info("Cliquez pour valider et archiver ces heures dans la base de données.")

    elif mode == "📅 Suivi de Présences":
        st.subheader("📅 Suivi de Présences")
        
        # 1. Sélecteur de date (Commun pour les anomalies et la recherche)
        # Par défaut : Date du jour - 7 jours
        def_start = datetime.now().date() - timedelta(days=7)
        def_end = datetime.now().date() + timedelta(days=30)
        
        # [SMART DEFAULT] Si un import existe, on cale les dates dessus pour voir les anomalies
        if 'verif_heures_results' in st.session_state and st.session_state['verif_heures_results'].get("analyzed"):
             results = st.session_state['verif_heures_results']
             raw_df = results.get("raw_df")
             plan_anomalies = results.get("anomalies_planning")

             # 1. Base : Fichier Heures (raw_df)
             if raw_df is not None and not raw_df.empty and 'Date' in raw_df.columns:
                 def_start = raw_df['Date'].min().date()
                 def_end = raw_df['Date'].max().date()
             
             # 2. Extension : Si anomalies (Planning futur ?), on étend la plage
             if plan_anomalies:
                 try:
                     df_anom_tmp = pd.DataFrame(plan_anomalies)
                     if 'Date' in df_anom_tmp.columns:
                        # Les dates sont en string 'dd/mm/YYYY'
                        dates_anom = pd.to_datetime(df_anom_tmp['Date'], format='%d/%m/%Y', errors='coerce').dt.date
                        if not dates_anom.empty:
                            min_anom = dates_anom.min()
                            max_anom = dates_anom.max()
                            
                            if min_anom < def_start: def_start = min_anom
                            if max_anom > def_end: def_end = max_anom
                 except:
                     pass # On garde les dates calculées avant

             # Marge de confort
        # Marge de confort
             def_end = def_end + timedelta(days=7)

        d_min, d_max = get_date_extremums(engine) if engine else (None, None)
        
        # Enforce bounds on defaults
        if d_min and d_max:
             if def_start < d_min: def_start = d_min
             if def_start > d_max: def_start = d_max
             if def_end > d_max: def_end = d_max
             if def_end < d_min: def_end = d_min

        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Date de début", value=def_start, min_value=d_min, max_value=d_max)
        with col2:
            date_end = st.date_input("Date de fin", value=def_end, min_value=d_min, max_value=d_max)

        st.markdown("---")

        st.markdown("---")
        
        # ⚠️ Anomalies Planning
        if True:
            # 2. Affichage des anomalies (HISTORIQUE + SESSION)
            st.markdown("### Absents du Relevé")
            
            # A. LOAD FROM DB
            df_anomalies_db = pd.DataFrame()
            if engine:
                 df_anomalies_db = load_planning_anomalies(engine, date_start, date_end)
            
            # B. SESSION (Si disponible)
            df_anomalies_session = pd.DataFrame()
            if 'verif_heures_results' in st.session_state and st.session_state['verif_heures_results'].get("analyzed"):
                results = st.session_state['verif_heures_results']
                plan_anomalies = results.get("anomalies_planning")
                
                if plan_anomalies:
                    df_temp = pd.DataFrame(plan_anomalies)
                    if 'Date' in df_temp.columns:
                        df_temp['Date_Obj'] = pd.to_datetime(df_temp['Date'], format='%d/%m/%Y', errors='coerce')
                        # Filter for display range logic (Optional, here we merge everything)
                        df_anomalies_session = df_temp.copy()
            
            # C. MERGE & DEDUP
            # On combine les deux sources
            df_all_anomalies = pd.DataFrame()
            
            # 1. Prepare DB
            if not df_anomalies_db.empty:
                df_db_clean = df_anomalies_db.copy()
                # Ensure Date is comparable (datetime or date object)
                df_db_clean['Date_Obj'] = pd.to_datetime(df_db_clean['Date'])
                df_all_anomalies = pd.concat([df_all_anomalies, df_db_clean], ignore_index=True)

            # 2. Prepare Session (ONLY if within range)
            if not df_anomalies_session.empty:
                 df_session_clean = df_anomalies_session.copy()
                 df_session_clean['Date_Obj'] = pd.to_datetime(df_session_clean['Date'], format='%d/%m/%Y', errors='coerce')
                 
                 # Filter Session Data to selected range
                 df_session_clean = df_session_clean[
                     (df_session_clean['Date_Obj'].dt.date >= date_start) & 
                     (df_session_clean['Date_Obj'].dt.date <= date_end)
                 ]
                 
                 if not df_session_clean.empty:
                     # Align columns (Session might have different cols, we keep common ones)
                     # Map 'Nom (Planning)' to 'Employé' if needed, but usually they are consistent in logic
                     if 'Nom (Planning)' in df_session_clean.columns and 'Employé' not in df_session_clean.columns:
                         df_session_clean['Employé'] = df_session_clean['Nom (Planning)']
                     
                     common_cols = ['Date', 'Employé', 'Qualification', 'Affectation', 'Date_Obj']
                     # Add missing cols with empty values
                     for c in common_cols:
                         if c not in df_session_clean.columns: df_session_clean[c] = ''
                         
                     df_all_anomalies = pd.concat([df_all_anomalies, df_session_clean], ignore_index=True)

            # 3. DEDUP
            if not df_all_anomalies.empty:
                # Dedup based on Date_Obj and Employé
                # We prefer DB records (usually cleaner), but here we just take the first one
                df_final_display = df_all_anomalies.drop_duplicates(subset=['Date_Obj', 'Employé']).copy()
                
                # Formattage Affichage
                st.info(f"Anomalies Planning : {len(df_final_display)}")
                
                df_display = df_final_display.copy()
                df_display['Date'] = df_display['Date_Obj'].dt.strftime('%d/%m/%Y')
                
                # [USER REQUEST] Hide Statut
                cols_to_drop = ['Date_Only', 'Date_Obj', 'Statut', 'Nom (Planning)']
                st.dataframe(style_zebra(df_display.drop(columns=cols_to_drop, errors='ignore').style), use_container_width=True)
                
            else:
                 st.success("✅ Aucune anomalie planning détectée sur cette période.")

    elif mode == "📈 Statistiques":
        if not engine:
            st.error("Base de donnée non connectée.")
            return

        df_history = load_history_data(engine)
    
        if df_history.empty:
            st.info("Aucun historique disponible. Enregistrez des analyses via l'onglet 'Vérification des Saisies'.")
        else:
            # Filtres
            # Filtres
            st.sidebar.markdown("### Filtres de Recherche")
        
        col_d1, col_d2 = st.sidebar.columns(2)
        with col_d1:
            # Fallback sur 30 jours
            def_start_stat = d_min if d_min else (datetime.now().date() - timedelta(days=30))
            date_start = st.date_input("Du", value=def_start_stat, min_value=d_min, max_value=d_max)
        with col_d2:
            def_end_stat = d_max if d_max else datetime.now().date()
            date_end = st.date_input("Au", value=def_end_stat, min_value=d_min, max_value=d_max)
            
        # Chargement des données quotidiennes
        df_daily = load_daily_data(engine, date_start, date_end)
        
        # Identification des semaines concernées pour l'historique hebdo
        semaines_concernees = []
        if not df_daily.empty:
            # On reconstruit les chaînes de caractères "Du ... au ..." pour matcher le format Hebdo
            def compute_period_string(d):
                try:
                    dt = pd.to_datetime(d)
                    start = dt - timedelta(days=dt.weekday())
                    end = start + timedelta(days=6)
                    return f"Du {start.strftime('%d/%m')} au {end.strftime('%d/%m')}"
                except:
                    return "Inconnu"
            
            semaines_concernees = df_daily['Date'].apply(compute_period_string).unique().tolist()
        
        employes_dispo = sorted(df_history['Employé'].unique().tolist()) if 'Employé' in df_history.columns else []
        selected_employes = st.sidebar.multiselect("Filtrer par employé", employes_dispo, placeholder="Filtrer...")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔍 Paramétrage de l'Analyse")
        noise_min_days = st.sidebar.slider("Seuil de Présence (Jours min.)", 1, 7, 2, help="Exclut les collaborateurs dont la base de données est insuffisante sur la période.")
        noise_hour_range = st.sidebar.slider("Amplitude Horaire Cible", 0, 80, (15, 60), help="Filtre les extrêmes pour se concentrer sur le cœur de l'effectif.")
        threshold_overtime = st.sidebar.slider("Seuil d'Alerte Quotidien (h)", 0.0, 24.0, 10.0, 0.5, help="Met en surbrillance rouge les jours dépassant ce volume horaire dans le détail.")
        
        # Apply Filters to Weekly History
        df_filtered = df_history.copy()
        if semaines_concernees:
            df_filtered = df_filtered[df_filtered['Semaine'].isin(semaines_concernees)]
        else:
            # Si pas de données quotidiennes sur la période, on n'affiche rien du hebdo par sécurité
            df_filtered = df_filtered.head(0)
        if selected_employes:
            df_filtered = df_filtered[df_filtered['Employé'].isin(selected_employes)]
            if not df_daily.empty:
                df_daily = df_daily[df_daily['Employé'].isin(selected_employes)]
        
            
        # KPIs Overview
        try:
            # KPIs Overview
            nb_entries = len(df_filtered)
            total_missing = df_filtered[df_filtered['Ecart'] < 0]['Ecart'].sum()
            avg_compliance = (len(df_filtered[df_filtered['Statut'] == 'OK']) / nb_entries * 100) if nb_entries > 0 else 0
            
            # --- TABLEAU DE BORD DÉCISIONNEL (PO VISION) ---
            if not df_daily.empty:
                # 1. IMPUTATION DES HEURES (Règle Métier : Non-P = 7h)
                df_calc = df_daily.copy()
                
                def imputer_heures(row):
                    code = str(row['Code']).upper().strip()
                    try:
                        # 0=Lundi, ..., 4=Vendredi, 5=Samedi, 6=Dimanche
                        is_weekend = pd.to_datetime(row['Date']).weekday() >= 5
                    except:
                        is_weekend = False

                    if code == 'P':
                        # Le travail réel (P) est toujours compté, même le weekend
                        return float(row['Heures']) if pd.notna(row['Heures']) else 0.0
                    elif code in ['RH', 'R']:
                        return 0.0
                    else:
                        # CP, MAL, RTT : Forfait 7h seulement du Lundi au Vendredi
                        if is_weekend: return 0.0
                        return 7.0
                
                df_calc['Heures_Corrigees'] = df_calc.apply(imputer_heures, axis=1)
                
                # 2. CALCUL PRO-RATA (Normalisation sur base 5 jours)
                def est_jour_comptable(row):
                    code = str(row['Code']).upper().strip()
                    try: is_weekend = pd.to_datetime(row['Date']).weekday() >= 5
                    except: is_weekend = False
                    
                    if code == 'P': return 1
                    if code in ['RH', 'R']: return 0
                    # CP/MAL le weekend ne comptent pas comme un jour de "présence" à normaliser
                    if is_weekend: return 0
                    return 1

                df_calc['Est_Jour_Travail'] = df_calc.apply(est_jour_comptable, axis=1)
                df_calc['Heures_P'] = df_calc.apply(lambda x: x['Heures'] if str(x['Code']).upper().strip() == 'P' else 0, axis=1)
                df_calc['Jours_Imputes'] = df_calc.apply(lambda x: 1 if str(x['Code']).upper().strip() not in ['P', 'RH', 'R'] else 0, axis=1)

                df_stats = df_calc.groupby('Employé').agg({
                    'Heures_Corrigees': ['sum', 'std'],
                    'Heures_P': 'sum',
                    'Jours_Imputes': 'sum',
                    'Est_Jour_Travail': 'sum',
                    'Code': lambda x: ', '.join(sorted(x.unique()))
                }).reset_index()
                
                # Flatten MultiIndex columns
                df_stats.columns = ['Employé', 'Total_Heures_Comptabilisées', 'Ecart_Type_Quotidien', 'Dont_Heures_Travaillées', 'Jours_Forfait_7h', 'Jours_Présence_Actifs', 'Codes_Présents']
                
                # Moyenne par jour travaillé * 5 (pour simuler une semaine de 5 jours)
                df_stats['Moyenne_Hebdo'] = (df_stats['Total_Heures_Comptabilisées'] / df_stats['Jours_Présence_Actifs'].replace(0, 1)) * 5
                
                # Réorganisation des colonnes
                cols_order = ['Employé', 'Moyenne_Hebdo', 'Ecart_Type_Quotidien', 'Jours_Présence_Actifs', 'Total_Heures_Comptabilisées', 'Dont_Heures_Travaillées', 'Jours_Forfait_7h', 'Codes_Présents']
                df_stats = df_stats[cols_order]

                # --- FILTRAGE DU BRUIT ---
                df_stats = df_stats[
                    (df_stats['Jours_Présence_Actifs'] >= noise_min_days) &
                    (df_stats['Moyenne_Hebdo'] >= noise_hour_range[0]) &
                    (df_stats['Moyenne_Hebdo'] <= noise_hour_range[1])
                ]

                import altair as alt

                st.markdown(f"### Revue de la Performance Horaire (Base 35h)")


                # --- GRAPHIQUE : MOYENNE HEBDO VS 35H ---
                st.markdown("**Moyenne d'Heures Hebdomadaire par Collaborateur**")
                
                # Tri
                df_chart = df_stats.sort_values('Moyenne_Hebdo', ascending=False)
                
                # Bar Chart
                bars = alt.Chart(df_chart).mark_bar().encode(
                    x=alt.X('Moyenne_Hebdo:Q', title='Moyenne Heures / Semaine', scale=alt.Scale(nice=True)),
                    y=alt.Y('Employé:N', sort='-x', title=''),
                    color=alt.condition(
                        alt.datum.Moyenne_Hebdo < 35,
                        alt.value('orange'),  # Moins de 35h
                        alt.value('#3b8ed0')   # 35h ou plus
                    ),
                    tooltip=['Employé', alt.Tooltip('Moyenne_Hebdo', format='.1f'), 'Total_Heures_Comptabilisées', 'Jours_Présence_Actifs', 'Jours_Forfait_7h']
                )
                
                # Règle des 35h
                rule_35 = alt.Chart(pd.DataFrame({'x': [35.0]})).mark_rule(color='red', strokeDash=[5,5]).encode(x='x')
                
                # On ajuste la hauteur pour que chaque nom ait assez d'espace
                chart_height = max(400, len(df_chart) * 30)
                
                st.altair_chart(
                    (bars + rule_35).properties(height=chart_height).configure_axisY(labelFontSize=13, labelLimit=300).interactive(), 
                    use_container_width=True
                )

                # --- TOP / BOTTOM 10 ---
                st.markdown("---")
                col_top, col_bottom = st.columns(2)
                
                with col_top:
                    st.markdown("##### 🔝 Top 10 - Amplitudes Fortes")
                    top_10 = df_stats.nlargest(10, 'Moyenne_Hebdo')[['Employé', 'Moyenne_Hebdo', 'Jours_Présence_Actifs']]
                    st.dataframe(style_zebra(top_10.style.format({'Moyenne_Hebdo': '{:.1f}'})), use_container_width=True)
                
                with col_bottom:
                    st.markdown("##### ⬇️ Top 10 - Amplitudes Faibles")
                    bottom_10 = df_stats.nsmallest(10, 'Moyenne_Hebdo')[['Employé', 'Moyenne_Hebdo', 'Jours_Présence_Actifs']]
                    st.dataframe(style_zebra(bottom_10.style.format({'Moyenne_Hebdo': '{:.1f}'})), use_container_width=True)

                # --- SCATTER PLOT : VOLATILITÉ ---
                st.markdown("---")
                st.markdown("##### 📉 Analyse de la Régularité")
                st.caption("Ce graphique croise le volume horaire (Axe X) avec la stabilité quotidienne (Axe Y). Un indice d'instabilité élevé signale des irrégularités dans le planning ou les pointages.")
                
                scatter = alt.Chart(df_stats).mark_circle(size=150).encode(
                    x=alt.X('Moyenne_Hebdo:Q', title="Moyenne Hebdo (h)", scale=alt.Scale(zero=False, nice=True)),
                    y=alt.Y('Ecart_Type_Quotidien:Q', title="Instabilité (Écart-type)", scale=alt.Scale(domain=[0, 5])),
                    color=alt.condition(
                        alt.datum.Moyenne_Hebdo < 35,
                        alt.value('orange'),
                        alt.value('#3b8ed0')
                    ),
                    tooltip=['Employé', alt.Tooltip('Moyenne_Hebdo', format='.1f'), alt.Tooltip('Ecart_Type_Quotidien', format='.2f'), 'Jours_Présence_Actifs']
                ).properties(height=400).interactive()
                
                st.altair_chart(scatter, use_container_width=True)


                # --- TABLEAU DE DETAILS INTERACTIF ---
                st.markdown("#### 📋 Détail par Collaborateur")
                st.info("💡 Cliquez sur une ligne pour voir le détail des jours.")
                
                try:
                    # Préparation du DF pour affichage
                    df_display_stats = df_stats.copy()
                    
                    # [NEW] Recherche avec auto-complétion
                    search_list = sorted(df_display_stats['Employé'].unique().tolist())
                    
                    if "search_employe_key" not in st.session_state:
                         st.session_state["search_employe_key"] = ""

                    def clear_search():
                        st.session_state["search_employe_key"] = ""

                    c_search, c_clear = st.columns([5, 1])
                    with c_search:
                         search_term = st.selectbox("🔍 Rechercher un employé", [""] + search_list, key="search_employe_key", placeholder="Tapez un nom...")
                    with c_clear:
                         st.write("") # Spacer for alignment
                         st.write("") 
                         st.button("❌", on_click=clear_search, help="Effacer la recherche")
                    
                    nom_employe = None
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
                        st.markdown(f"##### 🔎 Détail pour : **{nom_employe}**")
                        
                        # Filtrage des données quotidiennes
                        if not df_daily.empty:
                            df_user_daily = df_daily[df_daily['Employé'] == nom_employe].copy()
                            if not df_user_daily.empty:
                                df_user_daily['Date'] = pd.to_datetime(df_user_daily['Date']).dt.date
                                
                                # [NEW] Formatage Date et Ajout Colonnes Temps
                                df_user_daily['Date_Obj'] = pd.to_datetime(df_user_daily['Date'])
                                df_user_daily = df_user_daily.sort_values('Date_Obj')
                                
                                jours_fr = {0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi', 4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'}
                                def format_jour(d):
                                    return f"{jours_fr.get(d.weekday(), '')} {d.strftime('%d/%m/%Y')}"
                                
                                df_user_daily['Jour'] = df_user_daily['Date_Obj'].apply(format_jour)
                                
                                # Gestion des colonnes manquantes (si vieilles données)
                                for c in ['Heure_Debut', 'Heure_Fin', 'Pause', 'Heure_Debut_Pause', 'Heure_Fin_Pause']:
                                    if c not in df_user_daily.columns:
                                        df_user_daily[c] = ""
                                    else:
                                        # [FIX] Nettoyage à l'affichage : On retire la date et le "0 days"
                                        def clean_time_display(val):
                                            s = str(val)
                                            if not s or s == "nan" or s == "NaT": return ""
                                            
                                            # Cas Timedelta "0 days 09:00:00"
                                            if "days" in s:
                                                parts = s.split('days')
                                                if len(parts) > 1:
                                                    s = parts[-1].strip()
                                            
                                            # Cas Datetime "1900-01-01 09:00:00"
                                            if ' ' in s:
                                                try:
                                                    # Si le split précédent n'a pas suffi (ex: date réelle)
                                                    return pd.to_datetime(s).strftime('%H:%M:%S')
                                                except:
                                                    pass
                                            return s
                                        
                                        df_user_daily[c] = df_user_daily[c].apply(clean_time_display)
                                
                                cols_to_show = ['Jour', 'Semaine', 'Code', 'Heure_Debut', 'Heure_Debut_Pause', 'Heure_Fin_Pause', 'Heure_Fin', 'Heures']
                                
                                # [NEW] Zebra Striping (1 ligne sur 2)
                                df_show = df_user_daily[cols_to_show].reset_index(drop=True)
                                
                                def highlight_rows(row):
                                    styles = []
                                    try:
                                        heures_val = float(row['Heures'])
                                        is_overtime = heures_val >= threshold_overtime
                                    except:
                                        is_overtime = False
                                        
                                    for _ in range(len(row)):
                                        if is_overtime:
                                            styles.append('background-color: rgba(255, 99, 71, 0.3); color: white;')
                                        else:
                                            styles.append('background-color: rgba(128, 128, 128, 0.1)' if row.name % 2 != 0 else '')
                                    return styles

                                st.dataframe(
                                    df_show.style
                                        .format({'Heures': '{:.2f}'})
                                        .apply(highlight_rows, axis=1),
                                    use_container_width=True
                                )
                            else:
                                st.warning("Pas de détails quotidiens trouvés.")
                        else:
                             st.warning("Données quotidiennes non chargées.")

                except Exception as e_inter:
                    st.error(f"Erreur affichage interactif : {e_inter}")
                    # Fallback old static view
                    st.dataframe(style_zebra(df_stats.style), use_container_width=True)

            # else:
            #     st.warning("Données journalières insuffisantes pour cette période.")
        except Exception as e_stats:
            st.error(f"Erreur durant le calcul des statistiques : {e_stats}")
            st.exception(e_stats) # Show full traceback for better debugging
