"""
Django admin configuration for the annotation models.
"""

from django.contrib import admin
from .models import Language, TextDataset, TextAnnotation, Image, ImageAnnotation, UserProfile


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin interface for Language model."""
    list_display = ['code', 'name']
    search_fields = ['code', 'name']
    ordering = ['name']


@admin.register(TextDataset)
class TextDatasetAdmin(admin.ModelAdmin):
    """Admin interface for TextDataset model."""
    list_display = ['text', 'language', 'created_at']
    list_filter = ['language', 'created_at']
    search_fields = ['text']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']


@admin.register(TextAnnotation)
class TextAnnotationAdmin(admin.ModelAdmin):
    """Admin interface for TextAnnotation model."""
    list_display = ['dataset', 'target_text', 'target_language', 'status', 'annotator', 'created_at']
    list_filter = ['status', 'target_language', 'source_language', 'created_at']
    search_fields = ['dataset__text', 'target_text']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    """Admin interface for Image model."""
    list_display = ['image_url', 'uploaded_at']
    search_fields = ['image_url']
    readonly_fields = ['id', 'uploaded_at']
    ordering = ['-uploaded_at']


@admin.register(ImageAnnotation)
class ImageAnnotationAdmin(admin.ModelAdmin):
    """Admin interface for ImageAnnotation model."""
    list_display = ['image', 'description', 'language', 'status', 'annotator', 'created_at']
    list_filter = ['status', 'language', 'created_at']
    search_fields = ['description', 'image__image_url']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model."""
    list_display = ['user', 'role']
    list_filter = ['role']
    search_fields = ['user__username', 'user__email']