"""
Django app configuration for annotations.
"""

from django.apps import AppConfig


class AnnotationsConfig(AppConfig):
    """Configuration for the annotations app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'annotations'
    
    def ready(self):
        """Import signals when the app is ready."""
        import annotations.signals