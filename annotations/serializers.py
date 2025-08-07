"""
Serializers for the bilingual annotation API.
Handles data validation and transformation between JSON and Django models.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import (
    Language, TextDataset, TextAnnotation, 
    Image, ImageAnnotation, UserProfile
)


class LanguageSerializer(serializers.ModelSerializer):
    """Serializer for Language model."""
    
    class Meta:
        model = Language
        fields = ['id', 'code', 'name']


class TextDatasetSerializer(serializers.ModelSerializer):
    """Serializer for TextDataset model."""
    
    language_name = serializers.CharField(source='language.name', read_only=True)
    
    class Meta:
        model = TextDataset
        fields = ['id', 'text', 'language', 'language_name', 'created_at', 'tags']
        read_only_fields = ['id', 'created_at']


class TextAnnotationSerializer(serializers.ModelSerializer):
    """Serializer for TextAnnotation model with validation."""
    
    dataset_text = serializers.CharField(source='dataset.text', read_only=True)
    source_language_name = serializers.CharField(source='source_language.name', read_only=True)
    target_language_name = serializers.CharField(source='target_language.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)
    
    class Meta:
        model = TextAnnotation
        fields = [
            'id', 'dataset', 'dataset_text', 'target_text',
            'source_language', 'source_language_name',
            'target_language', 'target_language_name',
            'annotator', 'annotator_username', 'status',
            'quality_score', 'created_at', 'updated_at',
            'tags', 'validation_history'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'annotator']
    
    def validate_target_text(self, value):
        """Validate that target text is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Target text cannot be empty.")
        return value.strip()
    
    def validate_quality_score(self, value):
        """Validate quality score range."""
        if value is not None and (value < 0 or value > 5):
            raise serializers.ValidationError("Quality score must be between 0 and 5.")
        return value


class ImageSerializer(serializers.ModelSerializer):
    """Serializer for Image model."""
    
    class Meta:
        model = Image
        fields = ['id', 'image_url', 'uploaded_at', 'tags']
        read_only_fields = ['id', 'uploaded_at']


class ImageAnnotationSerializer(serializers.ModelSerializer):
    """Serializer for ImageAnnotation model."""
    
    image_url = serializers.CharField(source='image.image_url', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)
    
    class Meta:
        model = ImageAnnotation
        fields = [
            'id', 'image', 'image_url', 'description',
            'language', 'language_name', 'annotator',
            'annotator_username', 'status', 'quality_score',
            'created_at', 'updated_at', 'tags', 'validation_history'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'annotator']
    
    def validate_description(self, value):
        """Validate that description is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Description cannot be empty.")
        return value.strip()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model."""
    
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'first_name', 'last_name', 'role']
        read_only_fields = ['username', 'email', 'first_name', 'last_name']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    
    password = serializers.CharField(
        write_only=True, 
        min_length=8,
        error_messages={
            'min_length': 'Le mot de passe doit contenir au moins 8 caractères.',
            'required': 'Le mot de passe est requis.',
            'blank': 'Le mot de passe ne peut pas être vide.'
        }
    )
    password_confirm = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'La confirmation du mot de passe est requise.',
            'blank': 'La confirmation du mot de passe ne peut pas être vide.'
        }
    )
    role = serializers.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        default='annotator'
    )
    username = serializers.CharField(
        error_messages={
            'required': "Le nom d'utilisateur est requis.",
            'blank': "Le nom d'utilisateur ne peut pas être vide.",
            'unique': "Un utilisateur avec ce nom d'utilisateur existe déjà."
        }
    )
    email = serializers.EmailField(
        error_messages={
            'required': 'L\'adresse email est requise.',
            'invalid': 'Veuillez saisir une adresse email valide.',
            'unique': 'Un utilisateur avec cette adresse email existe déjà.'
        }
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm', 'role']
    
    def validate_username(self, value):
        """Validate username uniqueness with French message."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Un utilisateur avec ce nom d'utilisateur existe déjà.")
        return value
    
    def validate_email(self, value):
        """Validate email uniqueness with French message."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cette adresse email existe déjà.")
        return value
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Les mots de passe ne correspondent pas.")
        return attrs
    
    def create(self, validated_data):
        """Create user with profile."""
        role = validated_data.pop('role', 'annotator')
        validated_data.pop('password_confirm')
        
        user = User.objects.create_user(**validated_data)
        UserProfile.objects.create(user=user, role=role)
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    
    username = serializers.CharField(
        error_messages={
            'required': "Le nom d'utilisateur est requis.",
            'blank': "Le nom d'utilisateur ne peut pas être vide."
        }
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'Le mot de passe est requis.',
            'blank': 'Le mot de passe ne peut pas être vide.'
        }
    )
    
    def validate(self, attrs):
        """Validate user credentials."""
        username = attrs.get('username')
        password = attrs.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("Nom d'utilisateur ou mot de passe incorrect.")
            if not user.is_active:
                raise serializers.ValidationError("Ce compte utilisateur est désactivé.")
            attrs['user'] = user
        else:
            raise serializers.ValidationError("Le nom d'utilisateur et le mot de passe sont requis.")
        
        return attrs


class ValidationSerializer(serializers.Serializer):
    """Serializer for annotation validation."""
    
    status = serializers.ChoiceField(choices=['validated', 'rejected'])
    comment = serializers.CharField(required=False, allow_blank=True)
    quality_score = serializers.IntegerField(min_value=0, max_value=5, required=False)
    
    def validate_comment(self, value):
        """Validate comment for rejected annotations."""
        status = self.initial_data.get('status')
        if status == 'rejected' and not value:
            raise serializers.ValidationError("Comment is required for rejected annotations.")
        return value


class DatasetImportSerializer(serializers.Serializer):
    """Serializer for dataset import."""
    
    file = serializers.FileField()
    language_code = serializers.CharField(max_length=10)
    file_format = serializers.ChoiceField(choices=['csv', 'json'])
    
    def validate_file(self, value):
        """Validate file size and type."""
        if value.size > 10 * 1024 * 1024:  # 10MB limit
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        
        file_format = self.initial_data.get('file_format')
        if file_format == 'csv' and not value.name.endswith('.csv'):
            raise serializers.ValidationError("File must have .csv extension for CSV format.")
        elif file_format == 'json' and not value.name.endswith('.json'):
            raise serializers.ValidationError("File must have .json extension for JSON format.")
        
        return value
    
    def validate_language_code(self, value):
        """Validate that language exists."""
        if not Language.objects.filter(code=value).exists():
            raise serializers.ValidationError(f"Language with code '{value}' does not exist.")
        return value