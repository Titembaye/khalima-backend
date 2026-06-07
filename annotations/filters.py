import django_filters
from .models import TextAnnotation, ImageAnnotation

_STATUS = [('draft', 'Draft'), ('pending', 'Pending'), ('validated', 'Validated'), ('rejected', 'Rejected')]


class TextAnnotationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=_STATUS)
    source_language = django_filters.CharFilter(field_name='source_language__code', lookup_expr='iexact')
    target_language = django_filters.CharFilter(field_name='target_language__code', lookup_expr='iexact')
    annotator = django_filters.CharFilter(field_name='annotator__username', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = TextAnnotation
        fields = ['status', 'source_language', 'target_language', 'annotator']


class ImageAnnotationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=_STATUS)
    language = django_filters.CharFilter(field_name='language__code', lookup_expr='iexact')
    annotator = django_filters.CharFilter(field_name='annotator__username', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = ImageAnnotation
        fields = ['status', 'language', 'annotator']
