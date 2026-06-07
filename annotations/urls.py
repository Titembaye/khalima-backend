from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'annotations/text', views.TextAnnotationViewSet, basename='text-annotation')
router.register(r'annotations/image', views.ImageAnnotationViewSet, basename='image-annotation')

urlpatterns = [
    path('', include(router.urls)),
    path('annotations/', views.AnnotationListView.as_view(), name='annotation-list'),
    path('annotations/stats/', views.AnnotationStatsView.as_view(), name='annotation-stats'),
    path('dataset/random/', views.RandomTextDatasetView.as_view(), name='random-dataset'),
    path('dataset/import/', views.DatasetImportView.as_view(), name='dataset-import'),
    path('dataset/preview/', views.DatasetPreviewView.as_view(), name='dataset-preview'),
    path('dataset/export/', views.DatasetExportView.as_view(), name='dataset-export'),
    path('dataset/export/jsonl/', views.DatasetExportJsonlView.as_view(), name='dataset-export-jsonl'),
    path('validation/<uuid:annotation_id>/', views.ValidationView.as_view(), name='validate-annotation'),
    path('languages/', views.LanguageListView.as_view(), name='language-list'),
]
