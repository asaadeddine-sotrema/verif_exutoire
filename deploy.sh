#!/bin/bash
echo "=== Mise à jour et déploiement de Verif Exutoire ==="
docker-compose down
docker-compose build
docker-compose up -d
echo "L'application a été mise à jour et relancée sur le port 8501."
