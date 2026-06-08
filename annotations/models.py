from django.db import models
from django.contrib.auth.models import User
import uuid


class Language(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class TextDataset(models.Model):
    GRANULARITY_CHOICES = [('sentence', 'Phrase'), ('word', 'Mot')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField()
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.JSONField(default=list)
    granularity = models.CharField(max_length=10, choices=GRANULARITY_CHOICES, default='sentence')
    context = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.text} ({self.language.code}, {self.granularity})"


class TextAnnotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('rejected', 'Rejected'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(TextDataset, on_delete=models.CASCADE)
    target_text = models.TextField()
    source_language = models.ForeignKey(Language, related_name='source_annotations', on_delete=models.CASCADE)
    target_language = models.ForeignKey(Language, related_name='target_annotations', on_delete=models.CASCADE)
    annotator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    quality_score = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.JSONField(default=list)
    validation_history = models.JSONField(default=list)
    alternatives = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.dataset.text} -> {self.target_text}"


class Image(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image_url = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    tags = models.JSONField(default=list)

    def __str__(self):
        return self.image_url


class ImageAnnotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('rejected', 'Rejected'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    description = models.TextField()
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    annotator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    quality_score = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.JSONField(default=list)
    validation_history = models.JSONField(default=list)

    def __str__(self):
        return f"{self.image.image_url} ({self.language.code})"
