from rest_framework import serializers
from .models import Language, TextDataset, TextAnnotation, Image, ImageAnnotation


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'code', 'name']


class TextDatasetSerializer(serializers.ModelSerializer):
    language_name = serializers.CharField(source='language.name', read_only=True)

    class Meta:
        model = TextDataset
        fields = ['id', 'text', 'language', 'language_name', 'created_at', 'tags', 'granularity', 'context']
        read_only_fields = ['id', 'created_at']


class TextAnnotationSerializer(serializers.ModelSerializer):
    dataset_text = serializers.CharField(source='dataset.text', read_only=True)
    source_language_name = serializers.CharField(source='source_language.name', read_only=True)
    target_language_name = serializers.CharField(source='target_language.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)

    class Meta:
        model = TextAnnotation
        fields = [
            'id', 'dataset', 'dataset_text', 'target_text', 'alternatives',
            'source_language', 'source_language_name',
            'target_language', 'target_language_name',
            'annotator', 'annotator_username', 'status',
            'quality_score', 'created_at', 'updated_at',
            'tags', 'validation_history',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'annotator']

    def validate_target_text(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Target text cannot be empty.")
        return value.strip()

    def validate_quality_score(self, value):
        if value is not None and (value < 0 or value > 5):
            raise serializers.ValidationError("Quality score must be between 0 and 5.")
        return value


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ['id', 'image_url', 'uploaded_at', 'tags']
        read_only_fields = ['id', 'uploaded_at']


class ImageAnnotationSerializer(serializers.ModelSerializer):
    image_url = serializers.CharField(source='image.image_url', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)

    class Meta:
        model = ImageAnnotation
        fields = [
            'id', 'image', 'image_url', 'description',
            'language', 'language_name', 'annotator',
            'annotator_username', 'status', 'quality_score',
            'created_at', 'updated_at', 'tags', 'validation_history',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'annotator']

    def validate_description(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Description cannot be empty.")
        return value.strip()


class ValidationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['validated', 'rejected'])
    comment = serializers.CharField(required=False, allow_blank=True)
    quality_score = serializers.IntegerField(min_value=0, max_value=5, required=False)

    def validate_comment(self, value):
        if self.initial_data.get('status') == 'rejected' and not value:
            raise serializers.ValidationError("Comment is required for rejected annotations.")
        return value


class DatasetImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    language_code = serializers.CharField(max_length=10)
    file_format = serializers.ChoiceField(choices=['csv', 'json'])

    def validate_file(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        file_format = self.initial_data.get('file_format')
        if file_format == 'csv' and not value.name.endswith('.csv'):
            raise serializers.ValidationError("File must have .csv extension for CSV format.")
        elif file_format == 'json' and not value.name.endswith('.json'):
            raise serializers.ValidationError("File must have .json extension for JSON format.")
        return value

    def validate_language_code(self, value):
        if not Language.objects.filter(code=value).exists():
            raise serializers.ValidationError(f"Language with code '{value}' does not exist.")
        return value
