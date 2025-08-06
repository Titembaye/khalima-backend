"""
Tests for the annotations API.
"""

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from .models import Language, TextDataset, TextAnnotation, UserProfile


class AnnotationAPITestCase(APITestCase):
    """Test case for annotation API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        
        # Create languages
        self.french = Language.objects.create(code='french', name='French')
        self.saar = Language.objects.create(code='saar', name='Saar')
        
        # Create test dataset
        self.dataset = TextDataset.objects.create(
            text='Bonjour',
            language=self.french,
            tags=['greeting']
        )
    
    def authenticate(self):
        """Authenticate the test client."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
    
    def test_create_text_annotation(self):
        """Test creating a text annotation."""
        self.authenticate()
        
        data = {
            'dataset': self.dataset.id,
            'target_text': 'Hallo',
            'source_language': self.french.id,
            'target_language': self.saar.id,
            'status': 'draft'
        }
        
        response = self.client.post('/api/annotations/text/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TextAnnotation.objects.count(), 1)
        
        annotation = TextAnnotation.objects.first()
        self.assertEqual(annotation.target_text, 'Hallo')
        self.assertEqual(annotation.annotator, self.user)
    
    def test_get_random_dataset(self):
        """Test getting random dataset."""
        self.authenticate()
        
        response = self.client.get('/api/dataset/random/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['text'], 'Bonjour')
    
    def test_validation_requires_permission(self):
        """Test that validation requires proper permissions."""
        self.authenticate()
        
        # Create annotation
        annotation = TextAnnotation.objects.create(
            dataset=self.dataset,
            target_text='Hallo',
            source_language=self.french,
            target_language=self.saar,
            annotator=self.user
        )
        
        # Try to validate without proper role
        data = {'status': 'validated', 'comment': 'Good translation'}
        response = self.client.post(f'/api/validation/{annotation.id}/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Set user as reviewer
        profile = UserProfile.objects.get(user=self.user)
        profile.role = 'reviewer'
        profile.save()
        
        # Now validation should work
        response = self.client.post(f'/api/validation/{annotation.id}/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        annotation.refresh_from_db()
        self.assertEqual(annotation.status, 'validated')
    
    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are denied."""
        response = self.client.get('/api/annotations/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_login_endpoint(self):
        """Test user login endpoint."""
        data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertIn('user', response.data)


class ModelTestCase(TestCase):
    """Test case for model functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.french = Language.objects.create(code='french', name='French')
        self.saar = Language.objects.create(code='saar', name='Saar')
    
    def test_language_str(self):
        """Test Language string representation."""
        self.assertEqual(str(self.french), 'French')
    
    def test_text_dataset_creation(self):
        """Test TextDataset creation."""
        dataset = TextDataset.objects.create(
            text='Bonjour le monde',
            language=self.french,
            tags=['greeting', 'common']
        )
        
        self.assertEqual(dataset.text, 'Bonjour le monde')
        self.assertEqual(dataset.language, self.french)
        self.assertEqual(dataset.tags, ['greeting', 'common'])
    
    def test_user_profile_creation(self):
        """Test UserProfile is created automatically."""
        # UserProfile should be created by signal
        self.assertTrue(hasattr(self.user, 'userprofile'))
        self.assertEqual(self.user.userprofile.role, 'annotator')