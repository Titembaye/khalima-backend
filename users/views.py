import logging
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import UserProfile
from .permissions import IsAdmin
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


class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        profiles = UserProfile.objects.select_related('user').order_by('user__date_joined')
        return Response([
            {
                'id': p.user.id,
                'username': p.user.username,
                'email': p.user.email,
                'first_name': p.user.first_name,
                'last_name': p.user.last_name,
                'role': p.role,
                'date_joined': p.user.date_joined,
                'is_active': p.user.is_active,
            }
            for p in profiles
        ])

    def patch(self, request, user_id):
        try:
            profile = UserProfile.objects.select_related('user').get(user__id=user_id)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        new_role = request.data.get('role')
        if new_role not in dict(UserProfile.ROLE_CHOICES):
            return Response({'error': 'Rôle invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        profile.role = new_role
        profile.save()
        return Response({'id': profile.user.id, 'username': profile.user.username, 'role': profile.role})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email requis.'}, status=status.HTTP_400_BAD_REQUEST)

        # Always return success to avoid user enumeration
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'message': 'Si cet email existe, un lien de réinitialisation a été envoyé.'})

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        reset_link = f"{frontend_url}/reset-password/{uid}/{token}"

        try:
            send_mail(
                subject='Réinitialisation de votre mot de passe DATA4CHAD',
                message=(
                    f"Bonjour {user.first_name or user.username},\n\n"
                    f"Cliquez sur ce lien pour réinitialiser votre mot de passe :\n{reset_link}\n\n"
                    f"Ce lien est valable 24 heures.\n\n"
                    f"Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.\n\n"
                    f"— L'équipe DATA4CHAD"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"Password reset email sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send reset email to {email}: {e}")
            return Response({'error': 'Erreur lors de l\'envoi de l\'email. Contactez un administrateur.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'Si cet email existe, un lien de réinitialisation a été envoyé.'})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get('uid', '')
        token = request.data.get('token', '')
        new_password = request.data.get('new_password', '')

        if not uid or not token or not new_password:
            return Response({'error': 'Données incomplètes.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({'error': 'Le mot de passe doit contenir au moins 8 caractères.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Lien invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({'error': 'Lien expiré ou invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        logger.info(f"Password reset successful for {user.username}")
        return Response({'message': 'Mot de passe réinitialisé avec succès. Vous pouvez vous connecter.'})
