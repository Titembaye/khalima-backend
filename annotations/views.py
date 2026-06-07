import json
import csv
import io
import logging
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


class DatasetImportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DatasetImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        language_code = serializer.validated_data['language_code']
        file_format = serializer.validated_data['file_format']
        language = Language.objects.get(code=language_code)
        imported_count, errors = 0, []
        try:
            with transaction.atomic():
                if file_format == 'csv':
                    imported_count, errors = self._import_csv(file, language)
                else:
                    imported_count, errors = self._import_json(file, language)
        except Exception as e:
            logger.error(f"Dataset import failed: {e}")
            return Response({'error': 'Failed to import dataset.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        resp = {'imported_count': imported_count, 'message': f'Successfully imported {imported_count} texts.'}
        if errors:
            resp['errors'] = errors
        logger.info(f"Dataset import: {imported_count} texts by {request.user.username}")
        return Response(resp, status=status.HTTP_201_CREATED)

    def _import_csv(self, file, language):
        import pandas as pd
        imported_count, errors = 0, []
        df = pd.read_csv(file)
        if 'text' not in df.columns:
            raise ValueError("CSV must contain 'text' column")
        for index, row in df.iterrows():
            text = str(row['text']).strip()
            if not text:
                errors.append(f"Row {index + 1}: Empty text")
                continue
            tags = [t.strip() for t in str(row['tags']).split(',')] if 'tags' in df.columns and pd.notna(row.get('tags')) else []
            TextDataset.objects.create(text=text, language=language, tags=tags)
            imported_count += 1
        return imported_count, errors

    def _import_json(self, file, language):
        imported_count, errors = 0, []
        data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("JSON must contain an array of objects")
        for index, item in enumerate(data):
            text = item.get('text', '').strip()
            if not text:
                errors.append(f"Item {index + 1}: Missing or empty text")
                continue
            tags = item.get('tags', []) if isinstance(item.get('tags'), list) else []
            TextDataset.objects.create(text=text, language=language, tags=tags)
            imported_count += 1
        return imported_count, errors


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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, annotation_id):
        serializer = ValidationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_profile = getattr(request.user, 'userprofile', None)
        if not user_profile or user_profile.role not in ('reviewer', 'admin'):
            return Response(
                {'error': 'You do not have permission to validate annotations.'},
                status=status.HTTP_403_FORBIDDEN,
            )

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
