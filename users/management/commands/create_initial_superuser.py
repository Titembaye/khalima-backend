import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create initial superuser from env vars if none exists'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Superuser already exists — skipping.')
            return

        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    'DJANGO_SUPERUSER_EMAIL or DJANGO_SUPERUSER_PASSWORD not set — skipping.'
                )
            )
            return

        User.objects.create_superuser(username=email, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f'Superuser created: {email}'))
