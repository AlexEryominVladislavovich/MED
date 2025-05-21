from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DoctorViewSet, ScheduleViewSet, SpecializationViewSet

router = DefaultRouter()
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'specializations', SpecializationViewSet, basename='specialization')

urlpatterns = [
    path('', include(router.urls)),
]