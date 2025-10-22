# Khalima Backend API

Khalima est une initiative de Data4Chad visant à créer un système d'annotation bilingue pour faciliter la traduction et la préservation des langues tchadiennes, en commençant par le Saar.

## À Propos

Cette API REST Django constitue le backend du projet Khalima. Elle permet de :
- Gérer les annotations bilingues de textes
- Supporter plusieurs langues (Saar, Français, Arabe, Anglais)
- Stocker et organiser les traductions
- Faciliter la collaboration entre traducteurs

### Objectifs
- Préserver les langues tchadiennes par la numérisation
- Créer une base de données de traductions
- Faciliter l'apprentissage des langues locales
- Promouvoir la diversité linguistique

### Technologies
- Django REST Framework pour l'API
- PostgreSQL pour le stockage
- Redis & Celery pour les tâches asynchrones
- Documentation OpenAPI/Swagger

## Prérequis

- Python 3.11+
- PostgreSQL
- Redis (pour Celery)

## Installation

1. **Créer l'environnement virtuel**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

2. **Installer les dépendances**
```powershell
pip install -r requirements.txt
```

3. **Configuration**

Créer un fichier `.env` à la racine :
```env
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://user:password@localhost:5432/khalima
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

4. **Migrations**
```powershell
python manage.py migrate
```

5. **Données initiales**
```powershell
python manage.py setup_languages
```

## Documentation API

La documentation API utilise drf-spectacular avec 3 interfaces :

- Swagger UI : `/api/docs/` - Interface interactive
- ReDoc : `/api/redoc/` - Documentation statique
- Schema OpenAPI : `/api/schema/` - Schéma brut

### Configuration Swagger

```python
SPECTACULAR_SETTINGS = {
    'TITLE': 'Khalima API',
    'DESCRIPTION': 'API for managing annotations and translations',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
```

### Endpoints Principaux

- `/api/annotations/` - CRUD des annotations
- `/api/languages/` - Liste des langues supportées
- `/api/auth/` - Authentification

## Développement

1. **Lancer le serveur**
```powershell
python manage.py runserver
```

2. **Lancer Celery**
```powershell
celery -A khalima worker -l info
```

3. **Tests**
```powershell
python manage.py test
```

## Configuration Avancée

### Sécurité et Authentification
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}
```

### Gestion des Fichiers
- Taille max upload : 10MB
- Support des fichiers media et statiques
- Stockage sécurisé dans `media/` et `staticfiles/`

### Logging
Configuration dans `logs/`:
- `django.log` - Erreurs et événements importants
- Console - Informations de développement
- Format détaillé avec timestamp et niveau de log

### Internationalisation
```python
LANGUAGE_CODE = 'fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
```

## Structure du Projet
```
khalima-backend/
├── annotations/           # App principale
├── media/                # Fichiers uploadés
├── staticfiles/          # Fichiers statiques
├── logs/                 # Logs d'application
├── manage.py            
├── requirements.txt      # Dépendances
└── .env                 # Configuration locale
```

## Contribution

1. Forker le projet
2. Créer une branche (`git checkout -b feature/nouvelle_fonctionnalite`)
3. Commit (`git commit -m 'Ajout nouvelle fonctionnalité'`)
4. Push (`git push origin feature/nouvelle_fonctionnalite`)
5. Pull Request

## Contact & Communauté

Ce projet est maintenu par la communauté Data4Chad.

- **Discord**: [Rejoindre le serveur Khalima](lien_discord)
- **Email**: data4chad@gmail.org
- **GitHub Discussions**: Pour les questions techniques et suggestions
- **Issues**: Pour signaler des bugs ou proposer des fonctionnalités

Pour rejoindre notre communauté, merci de nous contacter via Discord ou email.

### Code de Conduite

Nous nous engageons à maintenir une communauté bienveillante et inclusive. Tous les contributeurs doivent respecter notre code de conduite.