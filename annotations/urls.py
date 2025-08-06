"""
URL patterns for the annotations API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'annotations/text', views.TextAnnotationViewSet, basename='text-annotation')
router.register(r'annotations/image', views.ImageAnnotationViewSet, basename='image-annotation')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Custom endpoints
    path('annotations/', views.AnnotationListView.as_view(), name='annotation-list'),
    path('dataset/random/', views.RandomTextDatasetView.as_view(), name='random-dataset'),
    path('dataset/import/', views.DatasetImportView.as_view(), name='dataset-import'),
    path('dataset/export/', views.DatasetExportView.as_view(), name='dataset-export'),
    path('validation/<uuid:annotation_id>/', views.ValidationView.as_view(), name='validate-annotation'),
    
    # Authentication endpoints
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/profile/', views.UserProfileView.as_view(), name='user-profile'),
    
    # Language management
    path('languages/', views.LanguageListView.as_view(), name='language-list'),
]