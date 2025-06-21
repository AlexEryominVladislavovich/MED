from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.permissions import AllowAny
from rest_framework import routers
from .views import (
    DoctorViewSet, ScheduleViewSet, SpecializationViewSet,
    TimeSlotViewSet,
    doctor_photos, doctor_schedule, create_appointment
)

class PublicAPIRootView(routers.APIRootView):
    permission_classes = [AllowAny]

router = DefaultRouter()
router.APIRootView = PublicAPIRootView

# Регистрируем ViewSets
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'schedules', ScheduleViewSet)
router.register(r'specializations', SpecializationViewSet)
router.register(r'time-slots', TimeSlotViewSet, basename='time-slots')

app_name = 'doctor'

urlpatterns = [
    # Базовые API endpoints через router
    path('', include(router.urls)),
    
    # Дополнительные endpoints для врачей
    path('doctors/<int:doctor_id>/photos/', doctor_photos, name='doctor-photos'),
    path('doctors/<int:doctor_id>/schedule/', doctor_schedule, name='doctor-schedule'),
    path('doctors/<int:doctor_id>/create-appointment/', create_appointment, name='create-appointment'),
]