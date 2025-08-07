"""
API views for the bilingual annotation system.
Implements all required endpoints with proper error handling and security.
"""

import json
import csv
import io
import logging
from django.db import transaction
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters
import pandas as pd

from .models import (
    Language, TextDataset, TextAnnotation,
    Image, ImageAnnotation, UserProfile
)
from .serializers import (
    LanguageSerializer, TextDatasetSerializer, TextAnnotationSerializer,
    ImageSerializer, ImageAnnotationSerializer, UserProfileSerializer,
    UserRegistrationSerializer, LoginSerializer, ValidationSerializer,
    DatasetImportSerializer
)

# Configure logging
logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    """Custom pagination class with configurable page size."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AnnotationFilter(filters.FilterSet):
    """Filter class for annotations with multiple criteria."""
    
    annotation_type = filters.ChoiceFilter(
        choices=[('text', 'Text'), ('image', 'Image')],
        method='filter_by_type'
    )
    language = filters.CharFilter(method='filter_by_language')
    status = filters.ChoiceFilter(choices=[
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('rejected', 'Rejected')
    ])
    created_after = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    def filter_by_type(self, queryset, name, value):
        """Filter by annotation type (text or image)."""
        # This will be handled in the view since we're combining two models
        return queryset
    
    def filter_by_language(self, queryset, name, value):
        """Filter by language code."""
        # This will be handled in the view since language fields differ
        return queryset


class TextAnnotationViewSet(viewsets.ModelViewSet):
    """ViewSet for text annotations with CRUD operations."""
    
    serializer_class = TextAnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'source_language', 'target_language']
    
    def get_queryset(self):
        """Get queryset with optimized queries."""
        return TextAnnotation.objects.select_related(
            'dataset', 'source_language', 'target_language', 'annotator'
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Set the annotator to the current user."""
        try:
            serializer.save(annotator=self.request.user)
            logger.info(f"Text annotation created by user {self.request.user.username}")
        except Exception as e:
            logger.error(f"Error creating text annotation: {str(e)}")
            raise
    
    def create(self, request, *args, **kwargs):
        """Create text annotation with error handling."""
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Text annotation creation failed: {str(e)}")
            return Response(
                {'error': 'Failed to create annotation. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImageAnnotationViewSet(viewsets.ModelViewSet):
    """ViewSet for image annotations with CRUD operations."""
    
    serializer_class = ImageAnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'language']
    
    def get_queryset(self):
        """Get queryset with optimized queries."""
        return ImageAnnotation.objects.select_related(
            'image', 'language', 'annotator'
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Set the annotator to the current user."""
        try:
            serializer.save(annotator=self.request.user)
            logger.info(f"Image annotation created by user {self.request.user.username}")
        except Exception as e:
            logger.error(f"Error creating image annotation: {str(e)}")
            raise
    
    def create(self, request, *args, **kwargs):
        """Create image annotation with error handling."""
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Image annotation creation failed: {str(e)}")
            return Response(
                {'error': 'Failed to create annotation. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AnnotationListView(ListAPIView):
    """Combined view for listing all annotations (text and image)."""
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get(self, request, *args, **kwargs):
        """Get combined list of text and image annotations."""
        try:
            # Get filter parameters
            annotation_type = request.query_params.get('type')
            language_code = request.query_params.get('language')
            status_filter = request.query_params.get('status')
            
            annotations = []
            
            # Get text annotations
            if not annotation_type or annotation_type == 'text':
                text_annotations = TextAnnotation.objects.select_related(
                    'dataset', 'source_language', 'target_language', 'annotator'
                )
                
                # Apply filters
                if language_code:
                    text_annotations = text_annotations.filter(
                        target_language__code=language_code
                    )
                if status_filter:
                    text_annotations = text_annotations.filter(status=status_filter)
                
                for annotation in text_annotations:
                    annotations.append({
                        'id': annotation.id,
                        'type': 'text',
                        'source_text': annotation.dataset.text,
                        'target_text': annotation.target_text,
                        'language': annotation.target_language.name,
                        'status': annotation.status,
                        'quality_score': annotation.quality_score,
                        'annotator': annotation.annotator.username if annotation.annotator else None,
                        'created_at': annotation.created_at,
                        'updated_at': annotation.updated_at
                    })
            
            # Get image annotations
            if not annotation_type or annotation_type == 'image':
                image_annotations = ImageAnnotation.objects.select_related(
                    'image', 'language', 'annotator'
                )
                
                # Apply filters
                if language_code:
                    image_annotations = image_annotations.filter(
                        language__code=language_code
                    )
                if status_filter:
                    image_annotations = image_annotations.filter(status=status_filter)
                
                for annotation in image_annotations:
                    annotations.append({
                        'id': annotation.id,
                        'type': 'image',
                        'image_url': annotation.image.image_url,
                        'description': annotation.description,
                        'language': annotation.language.name,
                        'status': annotation.status,
                        'quality_score': annotation.quality_score,
                        'annotator': annotation.annotator.username if annotation.annotator else None,
                        'created_at': annotation.created_at,
                        'updated_at': annotation.updated_at
                    })
            
            # Sort by creation date (newest first)
            annotations.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Apply pagination
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(annotations, request)
            
            return paginator.get_paginated_response(page)
            
        except Exception as e:
            logger.error(f"Error fetching annotations: {str(e)}")
            return Response(
                {'error': 'Failed to fetch annotations. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RandomTextDatasetView(APIView):
    """View to get random French text for annotation."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get a random French text that hasn't been annotated yet."""
        try:
            # Get French language
            try:
                french_language = Language.objects.get(code='french')
            except Language.DoesNotExist:
                return Response(
                    {'error': 'French language not configured in the system.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get unannotated French texts
            annotated_dataset_ids = TextAnnotation.objects.values_list('dataset_id', flat=True)
            available_texts = TextDataset.objects.filter(
                language=french_language
            ).exclude(id__in=annotated_dataset_ids)
            
            if not available_texts.exists():
                return Response(
                    {'message': 'No unannotated French texts available.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get random text
            random_text = available_texts.order_by('?').first()
            serializer = TextDatasetSerializer(random_text)
            
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error fetching random text: {str(e)}")
            return Response(
                {'error': 'Failed to fetch random text. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DatasetImportView(APIView):
    """View to import French dataset from CSV or JSON."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Import dataset from uploaded file."""
        serializer = DatasetImportSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file = serializer.validated_data['file']
            language_code = serializer.validated_data['language_code']
            file_format = serializer.validated_data['file_format']
            
            # Get language object
            language = Language.objects.get(code=language_code)
            
            imported_count = 0
            errors = []
            
            with transaction.atomic():
                if file_format == 'csv':
                    imported_count, errors = self._import_csv(file, language)
                elif file_format == 'json':
                    imported_count, errors = self._import_json(file, language)
            
            response_data = {
                'imported_count': imported_count,
                'message': f'Successfully imported {imported_count} texts.'
            }
            
            if errors:
                response_data['errors'] = errors
                response_data['message'] += f' {len(errors)} errors occurred.'
            
            logger.info(f"Dataset import completed: {imported_count} texts imported by {request.user.username}")
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Dataset import failed: {str(e)}")
            return Response(
                {'error': 'Failed to import dataset. Please check file format and try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _import_csv(self, file, language):
        """Import data from CSV file."""
        imported_count = 0
        errors = []
        
        try:
            # Read CSV file
            df = pd.read_csv(file)
            
            # Validate required columns
            if 'text' not in df.columns:
                raise ValueError("CSV must contain 'text' column")
            
            for index, row in df.iterrows():
                try:
                    text = str(row['text']).strip()
                    if not text:
                        errors.append(f"Row {index + 1}: Empty text")
                        continue
                    
                    # Get tags if available
                    tags = []
                    if 'tags' in df.columns and pd.notna(row['tags']):
                        tags = [tag.strip() for tag in str(row['tags']).split(',')]
                    
                    # Create TextDataset
                    TextDataset.objects.create(
                        text=text,
                        language=language,
                        tags=tags
                    )
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {index + 1}: {str(e)}")
                    
        except Exception as e:
            raise ValueError(f"CSV processing error: {str(e)}")
        
        return imported_count, errors
    
    def _import_json(self, file, language):
        """Import data from JSON file."""
        imported_count = 0
        errors = []
        
        try:
            # Read JSON file
            data = json.load(file)
            
            if not isinstance(data, list):
                raise ValueError("JSON must contain an array of objects")
            
            for index, item in enumerate(data):
                try:
                    if not isinstance(item, dict):
                        errors.append(f"Item {index + 1}: Must be an object")
                        continue
                    
                    text = item.get('text', '').strip()
                    if not text:
                        errors.append(f"Item {index + 1}: Missing or empty text")
                        continue
                    
                    tags = item.get('tags', [])
                    if not isinstance(tags, list):
                        tags = []
                    
                    # Create TextDataset
                    TextDataset.objects.create(
                        text=text,
                        language=language,
                        tags=tags
                    )
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Item {index + 1}: {str(e)}")
                    
        except Exception as e:
            raise ValueError(f"JSON processing error: {str(e)}")
        
        return imported_count, errors


class DatasetExportView(APIView):
    """View to export annotations in JSON or CSV format."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Export annotations based on query parameters."""
        try:
            export_format = request.query_params.get('format', 'json')
            annotation_type = request.query_params.get('type', 'all')
            language_code = request.query_params.get('language')
            status_filter = request.query_params.get('status')
            
            data = []
            
            # Export text annotations
            if annotation_type in ['all', 'text']:
                text_annotations = TextAnnotation.objects.select_related(
                    'dataset', 'source_language', 'target_language', 'annotator'
                )
                
                if language_code:
                    text_annotations = text_annotations.filter(target_language__code=language_code)
                if status_filter:
                    text_annotations = text_annotations.filter(status=status_filter)
                
                for annotation in text_annotations:
                    data.append({
                        'id': str(annotation.id),
                        'type': 'text',
                        'source_text': annotation.dataset.text,
                        'target_text': annotation.target_text,
                        'source_language': annotation.source_language.code,
                        'target_language': annotation.target_language.code,
                        'status': annotation.status,
                        'quality_score': annotation.quality_score,
                        'annotator': annotation.annotator.username if annotation.annotator else None,
                        'created_at': annotation.created_at.isoformat(),
                        'updated_at': annotation.updated_at.isoformat(),
                        'tags': annotation.tags
                    })
            
            # Export image annotations
            if annotation_type in ['all', 'image']:
                image_annotations = ImageAnnotation.objects.select_related(
                    'image', 'language', 'annotator'
                )
                
                if language_code:
                    image_annotations = image_annotations.filter(language__code=language_code)
                if status_filter:
                    image_annotations = image_annotations.filter(status=status_filter)
                
                for annotation in image_annotations:
                    data.append({
                        'id': str(annotation.id),
                        'type': 'image',
                        'image_url': annotation.image.image_url,
                        'description': annotation.description,
                        'language': annotation.language.code,
                        'status': annotation.status,
                        'quality_score': annotation.quality_score,
                        'annotator': annotation.annotator.username if annotation.annotator else None,
                        'created_at': annotation.created_at.isoformat(),
                        'updated_at': annotation.updated_at.isoformat(),
                        'tags': annotation.tags
                    })
            
            # Generate response based on format
            if export_format == 'csv':
                return self._export_csv(data)
            else:
                return self._export_json(data)
                
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return Response(
                {'error': 'Failed to export data. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _export_json(self, data):
        """Export data as JSON."""
        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="annotations_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
        return response
    
    def _export_csv(self, data):
        """Export data as CSV."""
        if not data:
            return Response({'message': 'No data to export'}, status=status.HTTP_404_NOT_FOUND)
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="annotations_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        return response


class ValidationView(APIView):
    """View to validate annotations."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, annotation_id):
        """Validate an annotation (text or image)."""
        serializer = ValidationSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            validated_data = serializer.validated_data
            validation_status = validated_data['status']
            comment = validated_data.get('comment', '')
            quality_score = validated_data.get('quality_score')
            
            # Try to find text annotation first
            annotation = None
            annotation_type = None
            
            try:
                annotation = TextAnnotation.objects.get(id=annotation_id)
                annotation_type = 'text'
            except TextAnnotation.DoesNotExist:
                try:
                    annotation = ImageAnnotation.objects.get(id=annotation_id)
                    annotation_type = 'image'
                except ImageAnnotation.DoesNotExist:
                    return Response(
                        {'error': 'Annotation not found.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Check permissions (only reviewers and admins can validate)
            user_profile = getattr(request.user, 'userprofile', None)
            if not user_profile or user_profile.role not in ['reviewer', 'admin']:
                return Response(
                    {'error': 'You do not have permission to validate annotations.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Update annotation
            with transaction.atomic():
                annotation.status = validation_status
                if quality_score is not None:
                    annotation.quality_score = quality_score
                
                # Add to validation history
                validation_entry = {
                    'user_id': request.user.id,
                    'username': request.user.username,
                    'status': validation_status,
                    'comment': comment,
                    'timestamp': timezone.now().isoformat()
                }
                
                if not annotation.validation_history:
                    annotation.validation_history = []
                annotation.validation_history.append(validation_entry)
                
                annotation.save()
            
            logger.info(f"Annotation {annotation_id} validated as {validation_status} by {request.user.username}")
            
            return Response({
                'message': f'Annotation {validation_status} successfully.',
                'annotation_id': str(annotation_id),
                'status': validation_status,
                'type': annotation_type
            })
            
        except Exception as e:
            logger.error(f"Validation failed for annotation {annotation_id}: {str(e)}")
            return Response(
                {'error': 'Failed to validate annotation. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LoginView(APIView):
    """View for user authentication."""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Authenticate user and return token."""
        serializer = LoginSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            login(request, user)
            
            # Get or create token
            token, created = Token.objects.get_or_create(user=user)
            
            # Get user profile
            try:
                profile = UserProfile.objects.get(user=user)
                role = profile.role
            except UserProfile.DoesNotExist:
                role = 'annotator'
            
            return Response({
                'token': token.key,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': role
                }
            })
        
        # Format errors for frontend
        error_messages = []
        for field, errors in serializer.errors.items():
            if isinstance(errors, list):
                for error in errors:
                    if field == 'non_field_errors':
                        error_messages.append(str(error))
                    else:
                        error_messages.append(str(error))
            else:
                error_messages.append(str(errors))
        
        error_message = '. '.join(error_messages)
        return Response(
            {'error': error_message},
            status=status.HTTP_400_BAD_REQUEST
        )


class LogoutView(APIView):
    """View for user logout."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Logout user and delete token."""
        try:
            # Delete the user's token
            Token.objects.filter(user=request.user).delete()
            logout(request)
            return Response({'message': 'Successfully logged out.'})
        except Exception as e:
            logger.error(f"Logout failed: {str(e)}")
            return Response(
                {'error': 'Logout failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegisterView(APIView):
    """View for user registration."""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Register new user."""
        serializer = UserRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                
                # Create token
                token = Token.objects.create(user=user)
                
                logger.info(f"New user registered: {user.username}")
                
                return Response({
                    'message': 'User registered successfully.',
                    'token': token.key,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'role': user.userprofile.role
                    }
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                logger.error(f"User registration failed: {str(e)}")
                return Response(
                    {'error': 'Registration failed. Please try again.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Format errors for frontend
        error_messages = []
        for field, errors in serializer.errors.items():
            if isinstance(errors, list):
                for error in errors:
                    if field == 'non_field_errors':
                        error_messages.append(str(error))
                    else:
                        error_messages.append(f"{field}: {str(error)}")
            else:
                error_messages.append(f"{field}: {str(errors)}")
        
        error_message = '. '.join(error_messages)
        return Response(
            {'error': error_message},
            status=status.HTTP_400_BAD_REQUEST
        )


class UserProfileView(APIView):
    """View for user profile management."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current user profile."""
        try:
            profile, created = UserProfile.objects.get_or_create(
                user=request.user,
                defaults={'role': 'annotator'}
            )
            serializer = UserProfileSerializer(profile)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Profile fetch failed: {str(e)}")
            return Response(
                {'error': 'Failed to fetch profile. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LanguageListView(ListAPIView):
    """View to list all available languages."""
    
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [permissions.IsAuthenticated]