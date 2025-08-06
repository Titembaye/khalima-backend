"""
Management command to set up initial languages in the database.
"""

from django.core.management.base import BaseCommand
from annotations.models import Language


class Command(BaseCommand):
    """Command to create initial language entries."""
    
    help = 'Create initial language entries for French and Saar'
    
    def handle(self, *args, **options):
        """Execute the command."""
        languages = [
            {'code': 'french', 'name': 'French'},
            {'code': 'saar', 'name': 'Saar'},
            {'code': 'arabic', 'name': 'Arabic'},
            {'code': 'english', 'name': 'English'},
        ]
        
        created_count = 0
        for lang_data in languages:
            language, created = Language.objects.get_or_create(
                code=lang_data['code'],
                defaults={'name': lang_data['name']}
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created language: {language.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Language already exists: {language.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Setup complete. Created {created_count} new languages.')
        )