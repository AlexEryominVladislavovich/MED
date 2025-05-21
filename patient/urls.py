"""
Конфигурация URL для приложения patient.

Этот модуль определяет все URL-маршруты, связанные с функциональностью пациента:
- Регистрация пациентов
- Просмотр записей на приём
- Управление профилем пациента
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegistrationViewSet, 
    PatientAppointmentViewSet,
    PatientAppointmentListView
)

# Инициализация маршрутизатора DRF
router = DefaultRouter()

# Регистрация ViewSet'ов в маршрутизаторе
router.register(
    'register',  # URL-префикс для регистрации
    RegistrationViewSet,  # ViewSet для обработки регистрации
    basename='register'  # Базовое имя для генерации URL
)

router.register(
    'appointments-new',  # Новый URL-префикс для записей
    PatientAppointmentViewSet,  # Современный ViewSet для записей
    basename='appointments-new'  # Базовое имя для URL
)

# Определение URL-паттернов
urlpatterns = [
    # Подключение всех URL из маршрутизатора
    path('', include(router.urls)),
    
    # Поддержка старого URL для обратной совместимости
    # TODO: Пометить как устаревший в следующей версии API
    path(
        'appointments/',  # Старый URL для просмотра записей
        PatientAppointmentListView.as_view(),  # Класс-обработчик
        name='patient-appointments'  # Имя URL для обратной совместимости
    ),
]