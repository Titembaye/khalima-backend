from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'first_name', 'last_name', 'role']
        read_only_fields = ['username', 'email', 'first_name', 'last_name']


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'min_length': 'Le mot de passe doit contenir au moins 8 caractères.',
            'required': 'Le mot de passe est requis.',
            'blank': 'Le mot de passe ne peut pas être vide.',
        },
    )
    password_confirm = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'La confirmation du mot de passe est requise.',
            'blank': 'La confirmation du mot de passe ne peut pas être vide.',
        },
    )
    role = serializers.ChoiceField(choices=UserProfile.ROLE_CHOICES, default='annotator')
    username = serializers.CharField(
        error_messages={
            'required': "Le nom d'utilisateur est requis.",
            'blank': "Le nom d'utilisateur ne peut pas être vide.",
        }
    )
    email = serializers.EmailField(
        error_messages={
            'required': "L'adresse email est requise.",
            'invalid': 'Veuillez saisir une adresse email valide.',
        }
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm', 'role']

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Un utilisateur avec ce nom d'utilisateur existe déjà.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cette adresse email existe déjà.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Les mots de passe ne correspondent pas.")
        return attrs

    def create(self, validated_data):
        role = validated_data.pop('role', 'annotator')
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        # Signal creates profile with default role — update if different
        user.userprofile.role = role
        user.userprofile.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        error_messages={
            'required': "Le nom d'utilisateur est requis.",
            'blank': "Le nom d'utilisateur ne peut pas être vide.",
        }
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'Le mot de passe est requis.',
            'blank': 'Le mot de passe ne peut pas être vide.',
        },
    )

    def validate(self, attrs):
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
