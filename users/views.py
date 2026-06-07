import logging
from django.contrib.auth import login, logout
from rest_framework import status, permissions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .serializers import LoginSerializer, UserRegistrationSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            login(request, user)
            token, _ = Token.objects.get_or_create(user=user)
            try:
                role = user.userprofile.role
            except UserProfile.DoesNotExist:
                role = 'annotator'
            return Response({
                'token': token.key,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': role,
                },
            })
        error_messages = [
            str(e)
            for errors in serializer.errors.values()
            for e in (errors if isinstance(errors, list) else [errors])
        ]
        return Response({'error': '. '.join(error_messages)}, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response({'message': 'Successfully logged out.'})


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                token = Token.objects.create(user=user)
                logger.info(f"New user registered: {user.username}")
                return Response({
                    'message': 'User registered successfully.',
                    'token': token.key,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'role': user.userprofile.role,
                    },
                }, status=status.HTTP_201_CREATED)
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
