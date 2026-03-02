import pandas as pd
from sqlalchemy import MetaData, Table, Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import insert
import json
import logging

logger = logging.getLogger(__name__)

TABLE_PRESTATAIRES = "config_prestataires"

def get_prestataires_dynamiques(engine):
    """Récupère la liste des prestataires configurés dynamiquement."""
    try:
        query = f'SELECT * FROM {TABLE_PRESTATAIRES} ORDER BY nom ASC'
        df = pd.read_sql(query, engine)
        
        # Parse JSON config
        configs = []
        for _, row in df.iterrows():
            try:
                mapping = json.loads(row['mapping_json'])
                configs.append({
                    "id": row['id'],
                    "nom": row['nom'],
                    "header_row": row['header_row'],
                    "mapping": mapping
                })
            except Exception as e:
                logger.error(f"Erreur parsing JSON pour le prestataire {row['nom']}: {e}")
                
        return configs
    except Exception as e:
        # Table might not exist yet
        logger.warning(f"Impossible de charger les prestataires dynamiques (table inexistante ?) : {e}")
        return []

def save_prestataire_dynamique(engine, nom, header_row, mapping_dict):
    """Sauvegarde ou met à jour la configuration d'un prestataire."""
    try:
        metadata = MetaData()
        table_presta = Table(
            TABLE_PRESTATAIRES,
            metadata,
            Column('id', Integer, primary_key=True),
            Column('nom', String, unique=True),
            Column('header_row', Integer),
            Column('mapping_json', Text)
        )
        metadata.create_all(engine)
        
        mapping_json = json.dumps(mapping_dict)
        
        with engine.begin() as conn:
            stmt = insert(table_presta).values(
                nom=nom,
                header_row=header_row,
                mapping_json=mapping_json
            )
            
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['nom'],
                set_=dict(
                    header_row=stmt.excluded.header_row,
                    mapping_json=stmt.excluded.mapping_json
                )
            )
            conn.execute(upsert_stmt)
            
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde prestataire {nom}: {e}")
        return False

def delete_prestataire_dynamique(engine, presta_id):
    """Supprime un prestataire dynamique."""
    try:
        query = f'DELETE FROM {TABLE_PRESTATAIRES} WHERE id = {presta_id}'
        with engine.begin() as conn:
            conn.execute(query)
        return True
    except Exception as e:
        logger.error(f"Erreur suppression prestataire {presta_id}: {e}")
        return False
