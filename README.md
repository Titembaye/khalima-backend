# Backend API pour Application d'Annotation Bilingue

Ce backend Django REST Framework implémente une API complète pour l'annotation bilingue français-saar avec support d'images.

## Fonctionnalités

### Endpoints API Principaux

- **POST /api/annotations/text** : Créer une annotation textuelle (français → saar)
- **POST /api/annotations/image** : Créer une annotation pour une image
- **GET /api/annotations** : Lister les annotations avec filtres (type, langue, statut)
- **GET /api/dataset/random** : Récupérer un texte français aléatoire pour annotation
- **POST /api/dataset/import** : Importer un dataset français (CSV/JSON)
- **GET /api/dataset/export** : Exporter les annotations (JSON/CSV)
- **POST /api/validation/:id** : Valider une annotation

### Authentification et Autorisation

- **POST /api/auth/login** : Connexion utilisateur
- **POST /api/auth/logout** : Déconnexion utilisateur
- **POST /api/auth/register** : Inscription utilisateur
- **GET /api/auth/profile** : Profil utilisateur

### Gestion des Langues

- **GET /api/languages** : Liste des langues disponibles

## Installation

1. **Installer les dépendances** :
```bash
pip install -r requirements.txt
```

2. **Configuration** :
```bash
cp .env.example .env
# Éditer .env avec vos paramètres
```

3. **Migrations de base de données** :
```bash
python manage.py makemigrations
python manage.py migrate
```

4. **Créer les langues initiales** :
```bash
python manage.py setup_languages
```

5. **Créer un superutilisateur** :
```bash
python manage.py createsuperuser
```

6. **Lancer le serveur** :
```bash
python manage.py runserver
```

## Architecture

### Modèles de Données

- **Language** : Langues supportées (français, saar, etc.)
- **TextDataset** : Textes sources à annoter
- **TextAnnotation** : Annotations textuelles
- **Image** : Images à annoter
- **ImageAnnotation** : Annotations d'images
- **UserProfile** : Profils utilisateurs avec rôles

### Rôles Utilisateurs

- **annotator** : Peut créer des annotations
- **reviewer** : Peut valider/rejeter des annotations
- **admin** : Accès complet

### Sécurité

- Authentification par token
- Permissions basées sur les rôles
- Validation des données d'entrée
- Protection CORS
- Limitation du taux de requêtes

### Gestion des Erreurs

- Logging complet des erreurs
- Réponses d'erreur standardisées
- Gestion des connexions instables
- Transactions atomiques pour l'intégrité des données

## Utilisation

### Authentification

```bash
# Inscription
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123", "email": "user@example.com"}'

# Connexion
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123"}'
```

### Créer une Annotation Textuelle

```bash
curl -X POST http://localhost:8000/api/annotations/text/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": "dataset-uuid",
    "target_text": "Hallo",
    "source_language": 1,
    "target_language": 2,
    "status": "draft"
  }'
```

### Importer un Dataset

```bash
curl -X POST http://localhost:8000/api/dataset/import/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -F "file=@dataset.csv" \
  -F "language_code=french" \
  -F "file_format=csv"
```

### Exporter les Annotations

```bash
curl -X GET "http://localhost:8000/api/dataset/export/?format=json&type=text" \
  -H "Authorization: Token YOUR_TOKEN"
```

## Tests

```bash
python manage.py test
```

## Extensibilité

Le système est conçu pour être facilement extensible :

- **Nouvelles langues** : Ajouter via l'admin Django ou la commande `setup_languages`
- **Nouveaux types d'annotations** : Étendre les modèles existants
- **Intégrations externes** : Utiliser les webhooks et l'API REST
- **Traitement en arrière-plan** : Celery configuré pour les tâches lourdes

## Monitoring et Logs

- Logs détaillés dans `logs/django.log`
- Interface d'administration Django sur `/admin/`
- Métriques API via Django REST Framework

## Production

Pour le déploiement en production :

1. Configurer PostgreSQL
2. Utiliser Redis pour Celery
3. Configurer un serveur web (Nginx + Gunicorn)
4. Activer HTTPS
5. Configurer les variables d'environnement de production