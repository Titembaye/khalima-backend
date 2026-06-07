import json
import csv
import io
import logging
import hashlib
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend

from .models import Language, TextDataset, TextAnnotation, Image, ImageAnnotation
from .serializers import (
    LanguageSerializer, TextDatasetSerializer, TextAnnotationSerializer,
    ImageSerializer, ImageAnnotationSerializer,
    ValidationSerializer, DatasetImportSerializer,
)
from .filters import TextAnnotationFilter, ImageAnnotationFilter
from users.permissions import IsAdmin, IsReviewer

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TextAnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = TextAnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = TextAnnotationFilter

    def get_queryset(self):
        return TextAnnotation.objects.select_related(
            'dataset', 'source_language', 'target_language', 'annotator'
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(annotator=self.request.user)


class ImageAnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = ImageAnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ImageAnnotationFilter

    def get_queryset(self):
        return ImageAnnotation.objects.select_related(
            'image', 'language', 'annotator'
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(annotator=self.request.user)


class AnnotationListView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get(self, request, *args, **kwargs):
        annotation_type = request.query_params.get('type')
        language_code = request.query_params.get('language')
        status_filter = request.query_params.get('status')
        annotations = []

        if not annotation_type or annotation_type == 'text':
            qs = TextAnnotation.objects.select_related(
                'dataset', 'source_language', 'target_language', 'annotator'
            )
            if language_code:
                qs = qs.filter(target_language__code=language_code)
            if status_filter:
                qs = qs.filter(status=status_filter)
            for a in qs:
                annotations.append({
                    'id': a.id, 'type': 'text',
                    'source_text': a.dataset.text, 'target_text': a.target_text,
                    'language': a.target_language.name, 'status': a.status,
                    'quality_score': a.quality_score,
                    'annotator': a.annotator.username if a.annotator else None,
                    'created_at': a.created_at, 'updated_at': a.updated_at,
                })

        if not annotation_type or annotation_type == 'image':
            qs = ImageAnnotation.objects.select_related('image', 'language', 'annotator')
            if language_code:
                qs = qs.filter(language__code=language_code)
            if status_filter:
                qs = qs.filter(status=status_filter)
            for a in qs:
                annotations.append({
                    'id': a.id, 'type': 'image',
                    'image_url': a.image.image_url, 'description': a.description,
                    'language': a.language.name, 'status': a.status,
                    'quality_score': a.quality_score,
                    'annotator': a.annotator.username if a.annotator else None,
                    'created_at': a.created_at, 'updated_at': a.updated_at,
                })

        annotations.sort(key=lambda x: x['created_at'], reverse=True)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(annotations, request)
        return paginator.get_paginated_response(page)


class AnnotationStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        def counts(model):
            return {
                'total': model.objects.count(),
                'draft': model.objects.filter(status='draft').count(),
                'pending': model.objects.filter(status='pending').count(),
                'validated': model.objects.filter(status='validated').count(),
                'rejected': model.objects.filter(status='rejected').count(),
            }
        text = counts(TextAnnotation)
        image = counts(ImageAnnotation)
        return Response({'text': text, 'image': image, 'total': text['total'] + image['total']})


class RandomTextDatasetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            french_language = Language.objects.get(code='french')
        except Language.DoesNotExist:
            return Response(
                {'error': 'French language not configured in the system.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        annotated_ids = TextAnnotation.objects.values_list('dataset_id', flat=True)
        available = TextDataset.objects.filter(language=french_language).exclude(id__in=annotated_ids)
        if not available.exists():
            return Response({'message': 'No unannotated French texts available.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TextDatasetSerializer(available.order_by('?').first()).data)


def _text_hash(text):
    return hashlib.md5(text.strip().lower().encode('utf-8')).hexdigest()


class DatasetImportView(APIView):
    """Import CSV/JSON with duplicate detection. Admin only."""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        serializer = DatasetImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        language_code = serializer.validated_data['language_code']
        file_format = serializer.validated_data['file_format']
        skip_duplicates = request.data.get('skip_duplicates', 'true').lower() == 'true'

        try:
            language = Language.objects.get(code=language_code)
        except Language.DoesNotExist:
            return Response(
                {'error': f"Language '{language_code}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                if file_format == 'csv':
                    result = self._import_csv(file, language, skip_duplicates)
                else:
                    result = self._import_json(file, language, skip_duplicates)
        except Exception as e:
            logger.error(f"Dataset import failed: {e}")
            return Response({'error': 'Failed to import dataset.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        msg = f'Successfully imported {result["imported_count"]} texts.'
        if result['duplicate_count']:
            msg += f' {result["duplicate_count"]} duplicates skipped.'
        logger.info(f"Dataset import: {result['imported_count']} texts by {request.user.username}")
        return Response({**result, 'message': msg}, status=status.HTTP_201_CREATED)

    def _existing_hashes(self, language):
        return {_text_hash(t) for t in TextDataset.objects.filter(language=language).values_list('text', flat=True)}

    def _import_csv(self, file, language, skip_duplicates):
        import pandas as pd
        imported_count = duplicate_count = 0
        errors = []
        df = pd.read_csv(file)
        if 'text' not in df.columns:
            raise ValueError("CSV must contain 'text' column")
        existing = self._existing_hashes(language) if skip_duplicates else set()
        seen = set()
        for index, row in df.iterrows():
            text = str(row['text']).strip()
            if not text or len(text) < 2:
                errors.append(f"Ligne {index + 1}: Texte vide ou trop court")
                continue
            if len(text) > 5000:
                errors.append(f"Ligne {index + 1}: Texte trop long (max 5000)")
                continue
            h = _text_hash(text)
            if skip_duplicates and (h in existing or h in seen):
                duplicate_count += 1
                continue
            seen.add(h)
            tags = []
            if 'tags' in df.columns and pd.notna(row.get('tags')):
                tags = [t.strip() for t in str(row['tags']).split(',') if t.strip()]
            for col, prefix in (('difficulty', 'difficulty'), ('domain', 'domain')):
                if col in df.columns and pd.notna(row.get(col)):
                    val = str(row[col]).strip().lower()
                    if val:
                        tags.append(f'{prefix}:{val}')
            TextDataset.objects.create(text=text, language=language, tags=tags[:10])
            imported_count += 1
        return {'imported_count': imported_count, 'duplicate_count': duplicate_count, 'errors': errors[:10]}

    def _import_json(self, file, language, skip_duplicates):
        imported_count = duplicate_count = 0
        errors = []
        data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("JSON must contain an array of objects")
        existing = self._existing_hashes(language) if skip_duplicates else set()
        seen = set()
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"Élément {index + 1}: Doit être un objet")
                continue
            text = str(item.get('text', '')).strip()
            if not text or len(text) < 2:
                errors.append(f"Élément {index + 1}: Texte vide ou trop court")
                continue
            if len(text) > 5000:
                errors.append(f"Élément {index + 1}: Texte trop long (max 5000)")
                continue
            h = _text_hash(text)
            if skip_duplicates and (h in existing or h in seen):
                duplicate_count += 1
                continue
            seen.add(h)
            tags = item.get('tags', [])
            if not isinstance(tags, list):
                tags = [t.strip() for t in str(tags).split(',') if t.strip()] if isinstance(tags, str) else []
            tags = [t for t in tags if isinstance(t, str) and t.strip()]
            for key, prefix in (('difficulty', 'difficulty'), ('domain', 'domain')):
                val = str(item.get(key, '')).strip().lower()
                if val:
                    tags.append(f'{prefix}:{val}')
            TextDataset.objects.create(text=text, language=language, tags=tags[:10])
            imported_count += 1
        return {'imported_count': imported_count, 'duplicate_count': duplicate_count, 'errors': errors[:10]}


class DatasetPreviewView(APIView):
    """Preview first 5 rows of a file before importing. Admin only."""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        serializer = DatasetImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        file_format = serializer.validated_data['file_format']
        preview, errors, total_items = [], [], 0

        try:
            if file_format == 'csv':
                import pandas as pd
                df = pd.read_csv(file)
                total_items = len(df)
                if 'text' not in df.columns:
                    errors.append("Missing required column 'text'")
                for i, row in df.head(5).iterrows():
                    text = str(row.get('text', ''))
                    preview.append({
                        'row': i + 1,
                        'text': text[:200] + ('...' if len(text) > 200 else ''),
                        'tags': str(row.get('tags', '')),
                        'difficulty': str(row.get('difficulty', '')),
                        'domain': str(row.get('domain', '')),
                    })
                return Response({'preview': preview, 'total_items': total_items,
                                 'errors': errors, 'columns': list(df.columns)})
            else:
                data = json.load(file)
                if not isinstance(data, list):
                    errors.append("JSON must contain an array of objects")
                else:
                    total_items = len(data)
                    for i, item in enumerate(data[:5]):
                        if isinstance(item, dict):
                            text = str(item.get('text', ''))
                            preview.append({
                                'row': i + 1,
                                'text': text[:200] + ('...' if len(text) > 200 else ''),
                                'tags': item.get('tags', []),
                                'difficulty': str(item.get('difficulty', '')),
                                'domain': str(item.get('domain', '')),
                            })
                return Response({'preview': preview, 'total_items': total_items, 'errors': errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DatasetExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        export_format = request.query_params.get('format', 'json')
        annotation_type = request.query_params.get('type', 'all')
        language_code = request.query_params.get('language')
        status_filter = request.query_params.get('status')
        data = []

        if annotation_type in ['all', 'text']:
            qs = TextAnnotation.objects.select_related('dataset', 'source_language', 'target_language', 'annotator')
            if language_code:
                qs = qs.filter(target_language__code=language_code)
            if status_filter:
                qs = qs.filter(status=status_filter)
            for a in qs:
                data.append({
                    'id': str(a.id), 'type': 'text',
                    'source_text': a.dataset.text, 'target_text': a.target_text,
                    'source_language': a.source_language.code,
                    'target_language': a.target_language.code,
                    'status': a.status, 'quality_score': a.quality_score,
                    'annotator': a.annotator.username if a.annotator else None,
                    'created_at': a.created_at.isoformat(), 'updated_at': a.updated_at.isoformat(),
                    'tags': a.tags,
                })

        if annotation_type in ['all', 'image']:
            qs = ImageAnnotation.objects.select_related('image', 'language', 'annotator')
            if language_code:
                qs = qs.filter(language__code=language_code)
            if status_filter:
                qs = qs.filter(status=status_filter)
            for a in qs:
                data.append({
                    'id': str(a.id), 'type': 'image',
                    'image_url': a.image.image_url, 'description': a.description,
                    'language': a.language.code, 'status': a.status,
                    'quality_score': a.quality_score,
                    'annotator': a.annotator.username if a.annotator else None,
                    'created_at': a.created_at.isoformat(), 'updated_at': a.updated_at.isoformat(),
                    'tags': a.tags,
                })

        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        if export_format == 'csv':
            if not data:
                return Response({'message': 'No data to export'}, status=status.HTTP_404_NOT_FOUND)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="annotations_{ts}.csv"'
            return response

        response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="annotations_{ts}.json"'
        return response


class DatasetExportJsonlView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        language_code = request.query_params.get('language')
        status_filter = request.query_params.get('status', 'validated')
        qs = TextAnnotation.objects.select_related(
            'dataset', 'source_language', 'target_language'
        ).filter(status=status_filter)
        if language_code:
            qs = qs.filter(target_language__code=language_code)
        lines = [
            json.dumps({
                'source': a.dataset.text, 'target': a.target_text,
                'source_language': a.source_language.code,
                'target_language': a.target_language.code,
            }, ensure_ascii=False)
            for a in qs
        ]
        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse('\n'.join(lines), content_type='application/jsonl')
        response['Content-Disposition'] = f'attachment; filename="annotations_{ts}.jsonl"'
        return response


class ValidationView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    def post(self, request, annotation_id):
        serializer = ValidationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
                return Response({'error': 'Annotation not found.'}, status=status.HTTP_404_NOT_FOUND)

        validated_data = serializer.validated_data
        with transaction.atomic():
            annotation.status = validated_data['status']
            if validated_data.get('quality_score') is not None:
                annotation.quality_score = validated_data['quality_score']
            annotation.validation_history = (annotation.validation_history or []) + [{
                'user_id': request.user.id,
                'username': request.user.username,
                'status': validated_data['status'],
                'comment': validated_data.get('comment', ''),
                'timestamp': timezone.now().isoformat(),
            }]
            annotation.save()

        return Response({
            'message': f'Annotation {validated_data["status"]} successfully.',
            'annotation_id': str(annotation_id),
            'status': validated_data['status'],
            'type': annotation_type,
        })


class LanguageListView(ListAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [permissions.IsAuthenticated]
