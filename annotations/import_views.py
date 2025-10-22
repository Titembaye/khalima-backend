"""
Advanced import/export views with progress tracking and duplicate detection.
Enhanced functionality for professional annotation platform.
"""

import json
import csv
import io
import logging
import hashlib
import time
from typing import Dict, List, Tuple
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
import pandas as pd

from .models import Language, TextDataset
from .serializers import DatasetImportSerializer

logger = logging.getLogger(__name__)


class AdvancedDatasetImportView(APIView):
    """Advanced dataset import with duplicate detection and progress tracking."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Import dataset with advanced features."""
        serializer = DatasetImportSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file = serializer.validated_data['file']
            language_code = serializer.validated_data['language_code']
            file_format = serializer.validated_data['file_format']
            skip_duplicates = request.data.get('skip_duplicates', 'true').lower() == 'true'
            
            # Get language object
            try:
                language = Language.objects.get(code=language_code)
            except Language.DoesNotExist:
                return Response(
                    {'error': f'Language {language_code} not found. Please create it first.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Generate unique task ID for progress tracking
            task_id = f"import_{int(time.time())}_{request.user.id}"
            
            # Initialize progress tracking in cache
            progress_data = {
                'status': 'processing',
                'progress': 0,
                'imported_count': 0,
                'duplicate_count': 0,
                'error_count': 0,
                'errors': [],
                'started_at': timezone.now().isoformat(),
                'user_id': request.user.id
            }
            cache.set(f"import_progress_{task_id}", progress_data, timeout=3600)  # 1 hour
            
            # Process import
            result = self._process_import(file, language, file_format, skip_duplicates, task_id)
            
            # Update final progress
            final_progress = cache.get(f"import_progress_{task_id}", {})
            final_progress.update({
                'status': 'completed',
                'progress': 100,
                'completed_at': timezone.now().isoformat()
            })
            cache.set(f"import_progress_{task_id}", final_progress, timeout=3600)
            
            response_data = {
                'task_id': task_id,
                'imported_count': result['imported_count'],
                'duplicate_count': result['duplicate_count'],
                'error_count': result['error_count'],
                'message': f'Successfully imported {result["imported_count"]} texts.'
            }
            
            if result['duplicate_count'] > 0:
                response_data['message'] += f' {result["duplicate_count"]} duplicates skipped.'
            
            if result['errors']:
                response_data['errors'] = result['errors'][:10]  # Limit to first 10 errors
                response_data['message'] += f' {len(result["errors"])} errors occurred.'
            
            logger.info(f"Dataset import completed: {result['imported_count']} texts imported, "
                       f"{result['duplicate_count']} duplicates by {request.user.username}")
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # Update progress with error
            if 'task_id' in locals():
                error_progress = cache.get(f"import_progress_{task_id}", {})
                error_progress.update({
                    'status': 'failed',
                    'error': str(e),
                    'completed_at': timezone.now().isoformat()
                })
                cache.set(f"import_progress_{task_id}", error_progress, timeout=3600)
            
            logger.error(f"Dataset import failed: {str(e)}")
            return Response(
                {'error': 'Failed to import dataset. Please check file format and try again.',
                 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_import(self, file, language, file_format, skip_duplicates, task_id):
        """Process import with progress tracking and duplicate detection."""
        with transaction.atomic():
            if file_format == 'csv':
                result = self._import_csv_advanced(file, language, skip_duplicates, task_id)
            elif file_format == 'json':
                result = self._import_json_advanced(file, language, skip_duplicates, task_id)
            else:
                raise ValueError(f"Unsupported format: {file_format}")
            
            return result
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash for duplicate detection."""
        normalized_text = text.strip().lower()
        return hashlib.md5(normalized_text.encode('utf-8')).hexdigest()
    
    def _import_csv_advanced(self, file, language, skip_duplicates, task_id):
        """Import data from CSV file with advanced features."""
        imported_count = 0
        duplicate_count = 0
        errors = []
        
        try:
            # Read CSV file
            df = pd.read_csv(file)
            total_rows = len(df)
            
            # Validate required columns
            if 'text' not in df.columns:
                raise ValueError("CSV must contain 'text' column")
            
            # Get existing text hashes for duplicate detection
            existing_hashes = set()
            if skip_duplicates:
                existing_texts = TextDataset.objects.filter(language=language).values_list('text', flat=True)
                existing_hashes = {self._get_text_hash(text) for text in existing_texts}
            
            processed_hashes = set()  # Track hashes in current import
            
            for index, row in df.iterrows():
                try:
                    # Update progress every 10 items
                    if index % 10 == 0:
                        progress = int((index / total_rows) * 100)
                        progress_data = cache.get(f"import_progress_{task_id}", {})
                        progress_data.update({
                            'progress': progress,
                            'imported_count': imported_count,
                            'duplicate_count': duplicate_count,
                            'error_count': len(errors),
                            'current_row': index + 1,
                            'total_rows': total_rows
                        })
                        cache.set(f"import_progress_{task_id}", progress_data, timeout=3600)
                    
                    text = str(row['text']).strip()
                    if not text:
                        errors.append(f"Ligne {index + 1}: Texte vide")
                        continue
                    
                    # Validate text length
                    if len(text) < 2:
                        errors.append(f"Ligne {index + 1}: Texte trop court (minimum 2 caractères)")
                        continue
                    
                    if len(text) > 5000:
                        errors.append(f"Ligne {index + 1}: Texte trop long (maximum 5000 caractères)")
                        continue
                    
                    # Duplicate detection
                    text_hash = self._get_text_hash(text)
                    if skip_duplicates and (text_hash in existing_hashes or text_hash in processed_hashes):
                        duplicate_count += 1
                        continue
                    
                    processed_hashes.add(text_hash)
                    
                    # Get tags if available
                    tags = []
                    if 'tags' in df.columns and pd.notna(row['tags']):
                        tags_str = str(row['tags']).strip()
                        if tags_str:
                            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                    
                    # Get difficulty if available
                    if 'difficulty' in df.columns and pd.notna(row['difficulty']):
                        difficulty_val = str(row['difficulty']).strip().lower()
                        if difficulty_val in ['easy', 'medium', 'hard']:
                            difficulty_tag = f'difficulty:{difficulty_val}'
                            if difficulty_tag not in tags:
                                tags.append(difficulty_tag)
                    
                    # Get domain/category if available
                    if 'domain' in df.columns and pd.notna(row['domain']):
                        domain_val = str(row['domain']).strip()
                        if domain_val:
                            domain_tag = f'domain:{domain_val}'
                            if domain_tag not in tags:
                                tags.append(domain_tag)
                    
                    # Limit tags to 10
                    tags = tags[:10]
                    
                    # Create TextDataset
                    TextDataset.objects.create(
                        text=text,
                        language=language,
                        tags=tags
                    )
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Ligne {index + 1}: {str(e)}")
                    
        except Exception as e:
            raise ValueError(f"Erreur de traitement CSV: {str(e)}")
        
        return {
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'error_count': len(errors),
            'errors': errors
        }
    
    def _import_json_advanced(self, file, language, skip_duplicates, task_id):
        """Import data from JSON file with advanced features."""
        imported_count = 0
        duplicate_count = 0
        errors = []
        
        try:
            # Read JSON file
            data = json.load(file)
            
            if not isinstance(data, list):
                raise ValueError("JSON doit contenir un tableau d'objets")
            
            total_items = len(data)
            
            # Get existing text hashes for duplicate detection
            existing_hashes = set()
            if skip_duplicates:
                existing_texts = TextDataset.objects.filter(language=language).values_list('text', flat=True)
                existing_hashes = {self._get_text_hash(text) for text in existing_texts}
            
            processed_hashes = set()  # Track hashes in current import
            
            for index, item in enumerate(data):
                try:
                    # Update progress every 10 items
                    if index % 10 == 0:
                        progress = int((index / total_items) * 100)
                        progress_data = cache.get(f"import_progress_{task_id}", {})
                        progress_data.update({
                            'progress': progress,
                            'imported_count': imported_count,
                            'duplicate_count': duplicate_count,
                            'error_count': len(errors),
                            'current_item': index + 1,
                            'total_items': total_items
                        })
                        cache.set(f"import_progress_{task_id}", progress_data, timeout=3600)
                    
                    if not isinstance(item, dict):
                        errors.append(f"Élément {index + 1}: Doit être un objet")
                        continue
                    
                    if 'text' not in item:
                        errors.append(f"Élément {index + 1}: Champ 'text' manquant")
                        continue
                    
                    text = str(item['text']).strip()
                    if not text:
                        errors.append(f"Élément {index + 1}: Texte vide")
                        continue
                    
                    # Validate text length
                    if len(text) < 2:
                        errors.append(f"Élément {index + 1}: Texte trop court (minimum 2 caractères)")
                        continue
                    
                    if len(text) > 5000:
                        errors.append(f"Élément {index + 1}: Texte trop long (maximum 5000 caractères)")
                        continue
                    
                    # Duplicate detection
                    text_hash = self._get_text_hash(text)
                    if skip_duplicates and (text_hash in existing_hashes or text_hash in processed_hashes):
                        duplicate_count += 1
                        continue
                    
                    processed_hashes.add(text_hash)
                    
                    # Get tags if available
                    tags = item.get('tags', [])
                    if not isinstance(tags, list):
                        if isinstance(tags, str):
                            tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
                        else:
                            tags = []
                    
                    # Validate tags
                    tags = [tag for tag in tags if isinstance(tag, str) and tag.strip()][:10]  # Limit to 10 tags
                    
                    # Get difficulty from item
                    difficulty = item.get('difficulty')
                    if difficulty and str(difficulty).lower() in ['easy', 'medium', 'hard']:
                        difficulty_tag = f"difficulty:{difficulty.lower()}"
                        if difficulty_tag not in tags:
                            tags.append(difficulty_tag)
                    
                    # Get domain from item
                    domain = item.get('domain')
                    if domain and str(domain).strip():
                        domain_tag = f"domain:{str(domain).strip()}"
                        if domain_tag not in tags:
                            tags.append(domain_tag)
                    
                    # Create TextDataset
                    TextDataset.objects.create(
                        text=text,
                        language=language,
                        tags=tags
                    )
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Élément {index + 1}: {str(e)}")
                    
        except Exception as e:
            raise ValueError(f"Erreur de traitement JSON: {str(e)}")
        
        return {
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'error_count': len(errors),
            'errors': errors
        }


class DatasetImportProgressView(APIView):
    """View to check import progress."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, task_id):
        """Get import progress for a specific task."""
        progress_data = cache.get(f"import_progress_{task_id}")
        
        if not progress_data:
            return Response(
                {'error': 'Task not found or expired.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Security check: only allow user to see their own progress
        if progress_data.get('user_id') != request.user.id:
            return Response(
                {'error': 'Access denied.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response(progress_data)


class DatasetPreviewView(APIView):
    """Preview dataset before import."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Preview first few rows of uploaded dataset."""
        serializer = DatasetImportSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file = serializer.validated_data['file']
            file_format = serializer.validated_data['file_format']
            
            preview_data = []
            errors = []
            
            if file_format == 'csv':
                df = pd.read_csv(file)
                
                # Check required columns
                if 'text' not in df.columns:
                    errors.append("Missing required column 'text'")
                
                # Get preview (first 5 rows)
                preview_rows = df.head(5)
                for index, row in preview_rows.iterrows():
                    preview_data.append({
                        'row': index + 1,
                        'text': str(row.get('text', ''))[:200] + '...' if len(str(row.get('text', ''))) > 200 else str(row.get('text', '')),
                        'tags': str(row.get('tags', '')),
                        'difficulty': str(row.get('difficulty', '')),
                        'domain': str(row.get('domain', ''))
                    })
                
            elif file_format == 'json':
                data = json.load(file)
                
                if not isinstance(data, list):
                    errors.append("JSON must contain an array of objects")
                else:
                    # Get preview (first 5 items)
                    preview_items = data[:5]
                    for index, item in enumerate(preview_items):
                        if isinstance(item, dict):
                            preview_data.append({
                                'row': index + 1,
                                'text': str(item.get('text', ''))[:200] + '...' if len(str(item.get('text', ''))) > 200 else str(item.get('text', '')),
                                'tags': item.get('tags', []),
                                'difficulty': str(item.get('difficulty', '')),
                                'domain': str(item.get('domain', ''))
                            })
                        else:
                            errors.append(f"Item {index + 1} is not an object")
            
            # Estimate total items/duplicates
            total_items = len(df) if file_format == 'csv' else len(data) if file_format == 'json' else 0
            
            return Response({
                'preview': preview_data,
                'total_items': total_items,
                'errors': errors,
                'columns_found': list(df.columns) if file_format == 'csv' else None
            })
            
        except Exception as e:
            logger.error(f"Preview failed: {str(e)}")
            return Response(
                {'error': 'Failed to preview file. Please check file format.',
                 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )