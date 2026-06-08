import json
import csv
import io
import logging
import hashlib
from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Q
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
        PERIODS = {'1d': 1, '3d': 3, '7d': 7, '30d': 30}
        period_key = request.query_params.get('period', 'all')
        since = None
        if period_key in PERIODS:
            since = timezone.now() - timedelta(days=PERIODS[period_key])

        def base_qs(model):
            qs = model.objects.all()
            if since:
                qs = qs.filter(created_at__gte=since)
            return qs

        def counts(qs):
            return qs.aggregate(
                total=Count('id'),
                draft=Count('id', filter=Q(status='draft')),
                pending=Count('id', filter=Q(status='pending')),
                validated=Count('id', filter=Q(status='validated')),
                rejected=Count('id', filter=Q(status='rejected')),
            )

        text = counts(base_qs(TextAnnotation))
        image = counts(base_qs(ImageAnnotation))

        response = {'text': text, 'image': image, 'total': (text['total'] or 0) + (image['total'] or 0)}

        profile = getattr(request.user, 'userprofile', None)
        if profile and profile.role in ('admin', 'reviewer'):
            text_by_user = (
                base_qs(TextAnnotation)
                .values('annotator__username', 'annotator__first_name', 'annotator__last_name')
                .annotate(
                    total=Count('id'),
                    draft=Count('id', filter=Q(status='draft')),
                    pending=Count('id', filter=Q(status='pending')),
                    validated=Count('id', filter=Q(status='validated')),
                    rejected=Count('id', filter=Q(status='rejected')),
                )
                .order_by('-total')
            )
            image_by_user = (
                base_qs(ImageAnnotation)
                .values('annotator__username', 'annotator__first_name', 'annotator__last_name')
                .annotate(
                    total=Count('id'),
                    draft=Count('id', filter=Q(status='draft')),
                    pending=Count('id', filter=Q(status='pending')),
                    validated=Count('id', filter=Q(status='validated')),
                    rejected=Count('id', filter=Q(status='rejected')),
                )
                .order_by('-total')
            )

            users_map = {}
            for row in text_by_user:
                uname = row['annotator__username'] or 'inconnu'
                users_map.setdefault(uname, {
                    'username': uname,
                    'first_name': row['annotator__first_name'] or '',
                    'last_name': row['annotator__last_name'] or '',
                    'text': {'total': 0, 'draft': 0, 'pending': 0, 'validated': 0, 'rejected': 0},
                    'image': {'total': 0, 'draft': 0, 'pending': 0, 'validated': 0, 'rejected': 0},
                })
                users_map[uname]['text'] = {k: row[k] for k in ('total', 'draft', 'pending', 'validated', 'rejected')}

            for row in image_by_user:
                uname = row['annotator__username'] or 'inconnu'
                users_map.setdefault(uname, {
                    'username': uname,
                    'first_name': row['annotator__first_name'] or '',
                    'last_name': row['annotator__last_name'] or '',
                    'text': {'total': 0, 'draft': 0, 'pending': 0, 'validated': 0, 'rejected': 0},
                    'image': {'total': 0, 'draft': 0, 'pending': 0, 'validated': 0, 'rejected': 0},
                })
                users_map[uname]['image'] = {k: row[k] for k in ('total', 'draft', 'pending', 'validated', 'rejected')}

            by_user = sorted(
                [
                    {**u, 'total': u['text']['total'] + u['image']['total']}
                    for u in users_map.values()
                ],
                key=lambda x: -x['total'],
            )
            response['by_user'] = by_user

        return Response(response)


class RandomTextDatasetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        granularity = request.query_params.get('granularity', 'sentence')
        source_lang = request.query_params.get('source_language', 'french')

        try:
            language = Language.objects.get(code=source_lang)
        except Language.DoesNotExist:
            return Response({'error': f"Langue '{source_lang}' introuvable."}, status=status.HTTP_404_NOT_FOUND)

        annotated_ids = TextAnnotation.objects.filter(
            annotator=request.user
        ).values_list('dataset_id', flat=True)

        available = TextDataset.objects.filter(
            language=language,
            granularity=granularity,
        ).exclude(id__in=annotated_ids)

        if not available.exists():
            return Response(
                {'message': 'Aucun texte disponible pour cette combinaison.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TextDatasetSerializer(available.order_by('?').first()).data)


def _text_hash(text):
    return hashlib.md5(text.strip().lower().encode('utf-8')).hexdigest()


class DatasetImportView(APIView):
    """Import CSV/JSON with duplicate detection. Admin only."""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        name = file.name.lower()
        if name.endswith('.csv'):
            file_format = 'csv'
        elif name.endswith('.json'):
            file_format = 'json'
        else:
            return Response({'error': 'Format non supporté. Utilisez CSV ou JSON.'}, status=status.HTTP_400_BAD_REQUEST)

        skip_duplicates = request.data.get('skip_duplicates', 'true') != 'false'

        # Précharger toutes les langues pour éviter N+1 queries
        lang_cache = {l.code: l for l in Language.objects.all()}

        # Langue par défaut si la colonne source_language est absente
        default_lang_code = request.data.get('language_code', 'french')
        if default_lang_code not in lang_cache:
            return Response(
                {'error': f"Langue '{default_lang_code}' introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                if file_format == 'csv':
                    result = self._import_csv(file, lang_cache, default_lang_code, skip_duplicates)
                else:
                    result = self._import_json(file, lang_cache[default_lang_code], skip_duplicates)
        except Exception as e:
            logger.error(f"Dataset import failed: {e}")
            return Response({'error': 'Failed to import dataset.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        msg = f'{result["imported_count"]} textes importés.'
        if result['duplicate_count']:
            msg += f' {result["duplicate_count"]} doublons ignorés.'
        logger.info(f"Dataset import: {result['imported_count']} texts by {request.user.username}")
        return Response({**result, 'imported': result['imported_count'], 'message': msg}, status=status.HTTP_201_CREATED)

    def _existing_hashes(self):
        return {_text_hash(t) for t in TextDataset.objects.values_list('text', flat=True)}

    def _import_csv(self, file, lang_cache, default_lang_code, skip_duplicates):
        import csv as csv_mod
        imported_count = duplicate_count = 0
        errors = []
        existing = self._existing_hashes() if skip_duplicates else set()
        seen = set()

        content = file.read().decode('utf-8-sig')
        reader = csv_mod.DictReader(content.splitlines())

        if 'text' not in (reader.fieldnames or []):
            raise ValueError("Le CSV doit contenir une colonne 'text'.")

        has_source_lang = 'source_language' in (reader.fieldnames or [])
        has_granularity = 'granularity' in (reader.fieldnames or [])
        has_context = 'context' in (reader.fieldnames or [])
        has_source = 'source' in (reader.fieldnames or [])

        objects = []
        for i, row in enumerate(reader):
            text = (row.get('text') or '').strip()
            if not text or len(text) < 2:
                errors.append(f"Ligne {i + 2}: texte vide ou trop court")
                continue
            if len(text) > 5000:
                errors.append(f"Ligne {i + 2}: texte trop long (max 5000)")
                continue

            h = _text_hash(text)
            if skip_duplicates and (h in existing or h in seen):
                duplicate_count += 1
                continue
            seen.add(h)

            lang_code = (row.get('source_language') or '').strip() if has_source_lang else default_lang_code
            language = lang_cache.get(lang_code) or lang_cache.get(default_lang_code)
            if not language:
                errors.append(f"Ligne {i + 2}: langue '{lang_code}' inconnue")
                continue

            granularity = (row.get('granularity') or 'sentence').strip()
            if granularity not in ('sentence', 'word'):
                granularity = 'sentence'

            context = (row.get('context') or '').strip() if has_context else ''
            source_tag = (row.get('source') or '').strip() if has_source else ''
            tags = [f'source:{source_tag}'] if source_tag else []

            objects.append(TextDataset(
                text=text,
                language=language,
                granularity=granularity,
                context=context,
                tags=tags,
            ))

        TextDataset.objects.bulk_create(objects, batch_size=500)
        imported_count = len(objects)
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
    """Preview first 10 rows of a CSV/JSON file before importing. Admin only."""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 10 * 1024 * 1024:
            return Response({'error': 'Fichier trop volumineux (max 10 Mo).'}, status=status.HTTP_400_BAD_REQUEST)

        name = file.name.lower()
        try:
            if name.endswith('.csv'):
                import csv as csv_mod
                content = file.read().decode('utf-8-sig')
                lines = content.splitlines()
                reader = csv_mod.DictReader(lines)
                all_rows = list(reader)
                columns = reader.fieldnames or []
                rows = [{k: (str(v) if v is not None else '') for k, v in row.items()} for row in all_rows[:10]]
                return Response({'columns': list(columns), 'rows': rows, 'total_rows': len(all_rows)})
            elif name.endswith('.json'):
                data = json.load(file)
                if not isinstance(data, list):
                    return Response({'error': 'Le JSON doit contenir un tableau d\'objets.'}, status=status.HTTP_400_BAD_REQUEST)
                if not data:
                    return Response({'error': 'Fichier JSON vide.'}, status=status.HTTP_400_BAD_REQUEST)
                columns = list(data[0].keys()) if isinstance(data[0], dict) else ['value']
                rows = [{k: str(v) for k, v in item.items()} for item in data[:10] if isinstance(item, dict)]
                return Response({'columns': columns, 'rows': rows, 'total_rows': len(data)})
            else:
                return Response({'error': 'Format non supporté. Utilisez CSV ou JSON.'}, status=status.HTTP_400_BAD_REQUEST)
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
