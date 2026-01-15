from django.urls import path
from django.contrib.auth import views as auth_views
from mental.views import (
    landing, login, signup,
    dashboard, logout, save_mood,
    chat, chat_api, get_chat_history, new_chat_session,
    questions, edit_profile, change_password,
    resources, privacy, settings,
    journal, save_chat_as_journal,
    mood_dashboard,
    subscribe, esewa_success, esewa_failure,
)

urlpatterns = [
    # Public
    path('', landing, name='landing'),
    path('login/', login, name='login'),
    path('signup/', signup, name='signup'),
    path('resources/', resources, name='resources'),
    path('privacy/', privacy, name='privacy'),

    # Auth'd — core
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', logout, name='logout'),
    path('questions/', questions, name='questions'),

    # Auth'd — profile & settings
    path('edit_profile/', edit_profile, name='edit_profile'),
    path('change-password/', change_password, name='change_password'),
    path('settings/', settings, name='settings'),

    # Auth'd — mood
    path('save-mood/', save_mood, name='save_mood'),
    path('mood_dashboard/', mood_dashboard, name='mood_dashboard'),

    # Auth'd — chat
    path('chat/', chat, name='chat'),
    path('chat-api/', chat_api, name='chat_api'),
    path('chat-history/', get_chat_history, name='chat_history'),
    path('new-chat/', new_chat_session, name='new_chat'),

    # Auth'd — journal & subscription
    path('journal/', journal, name='journal'),
    path('journal/save-chat/', save_chat_as_journal, name='save_chat_as_journal'),
    path('subscribe/', subscribe, name='subscribe'),
    path('esewa/success/', esewa_success, name='esewa_success'),
    path('esewa/failure/', esewa_failure, name='esewa_failure'),

    # Password reset
    path('forgot_password/', auth_views.PasswordResetView.as_view(
        template_name='mental/forgot_password.html',
        email_template_name='mental/password_reset_email.html',
        success_url='/password-reset-done/',
    ), name='password_reset'),
    path('password-reset-done/', auth_views.PasswordResetDoneView.as_view(
        template_name='mental/password_reset_done.html',
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='mental/password_reset_confirm.html',
        success_url='/reset-done/',
    ), name='password_reset_confirm'),
    path('reset-done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='mental/password_reset_complete.html',
    ), name='password_reset_complete'),
]
