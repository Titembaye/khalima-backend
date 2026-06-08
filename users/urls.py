from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('auth/password/', views.PasswordChangeView.as_view(), name='password-change'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/users/', views.UserListView.as_view(), name='user-list'),
    path('auth/users/<int:user_id>/', views.UserListView.as_view(), name='user-detail'),
    path('auth/password/reset/', views.PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password/reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
