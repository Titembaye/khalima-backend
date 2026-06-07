import logging
from django.contrib.auth import login, logout
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import UserProfile
from .serializers import LoginSerializer, UserRegistrationSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


def _jwt_response(user):
    refresh = RefreshToken.for_user(user)
    try:
        role = user.userprofile.role
    except UserProfile.DoesNotExist:
        role = 'annotator'
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': role,
        },
    }


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            login(request, user)
            return Response(_jwt_response(user))
        error_messages = [
            str(e)
            for errors in serializer.errors.values()
            for e in (errors if isinstance(errors, list) else [errors])
        ]
        return Response({'error': '. '.join(error_messages)}, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
        logout(request)
        return Response({'message': 'Successfully logged out.'})


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                logger.info(f"New user registered: {user.username}")
                return Response(_jwt_response(user), status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"User registration failed: {e}")
                return Response(
                    {'error': 'Registration failed. Please try again.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        error_messages = [
            f"{field}: {e}" if field != 'non_field_errors' else str(e)
            for field, errors in serializer.errors.items()
            for e in (errors if isinstance(errors, list) else [errors])
        ]
        return Response({'error': '. '.join(error_messages)}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(
            user=request.user, defaults={'role': 'annotator'}
        )
        return Response(UserProfileSerializer(profile).data)

    def patch(self, request):
        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'annotator'})

        # Update user fields
        for field in ('first_name', 'last_name', 'email'):
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()

        # Only admins can change roles
        if 'role' in request.data:
            requester_profile = getattr(request.user, 'userprofile', None)
            if requester_profile and requester_profile.role == 'admin':
                new_role = request.data['role']
                if new_role in dict(UserProfile.ROLE_CHOICES):
                    profile.role = new_role
                    profile.save()

        return Response(UserProfileSerializer(profile).data)


class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')

        if not old_password or not new_password:
            return Response(
                {'error': 'Les deux mots de passe sont requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.user.check_password(old_password):
            return Response(
                {'error': 'Mot de passe actuel incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(new_password) < 8:
            return Response(
                {'error': 'Le nouveau mot de passe doit contenir au moins 8 caractères.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': 'Mot de passe modifié avec succès.'})
