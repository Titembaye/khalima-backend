from django.db import models
from django.contrib.auth.models import User
import uuid

class Language(models.Model):
    code = models.CharField(max_length=10, unique=True)  # e.g., 'french', 'saar', 'arabic'
    name = models.CharField(max_length=100)  # Human-readable name, e.g., 'French', 'Saar'

    def __str__(self):
        return self.name

class TextDataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField()  # Source text (e.g., French phrase)
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.JSONField(default=list)  # e.g., ["domain:greeting", "difficulty:easy"]

    def __str__(self):
        return f"{self.text} ({self.language.code})"

class TextAnnotation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(TextDataset, on_delete=models.CASCADE)  # Link to source text
    target_text = models.TextField()  # Translation (e.g., Saar)
    source_language = models.ForeignKey(Language, related_name='source_annotations', on_delete=models.CASCADE)
    target_language = models.ForeignKey(Language, related_name='target_annotations', on_delete=models.CASCADE)
    annotator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('rejected', 'Rejected')
    ], default='draft')
    quality_score = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.JSONField(default=list)  # e.g., ["domain:greeting", "difficulty:easy"]
    validation_history = models.JSONField(default=list)  # e.g., [{"user_id": 1, "status": "validated", "comment": "Good"}]

    def __str__(self):
        return f"{self.dataset.text} -> {self.target_text}"

class Image(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image_url = models.CharField(max_length=255)  # Path to image (e.g., stored in cloud or local)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    tags = models.JSONField(default=list)  # e.g., ["domain:culture", "difficulty:medium"]

    def __str__(self):
        return self.image_url

class ImageAnnotation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    description = models.TextField()  # Description in specified language
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    annotator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('rejected', 'Rejected')
    ], default='draft')
    quality_score = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.JSONField(default=list)  # e.g., ["domain:culture", "difficulty:medium"]
    validation_history = models.JSONField(default=list)  # e.g., [{"user_id": 1, "status": "validated", "comment": "Accurate"}]

    def __str__(self):
        return f"{self.image.image_url} ({self.language.code})"

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('annotator', 'Annotator'),
        ('reviewer', 'Reviewer'),
        ('admin', 'Administrator')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='annotator')

    def __str__(self):
        return f"{self.user.username} ({self.role})"