from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.permissions import AllowAny
from rest_framework import routers
from .views import DoctorViewSet, ScheduleViewSet, SpecializationViewSet
from . import views

class PublicAPIRootView(routers.APIRootView):
    permission_classes = [AllowAny]

router = DefaultRouter()
router.APIRootView = PublicAPIRootView
router.register(r'', DoctorViewSet, basename='doctor')
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'specializations', SpecializationViewSet, basename='specialization')

app_name = 'doctor'

urlpatterns = [
    path('', include(router.urls)),
    
    # Детальная информация о враче
    path('<int:doctor_id>/detail/', views.doctor_detail, name='doctor_detail'),
    
    # Получение фотографий врача
    path('<int:doctor_id>/photos/', views.doctor_photos, name='doctor_photos'),
    
    # Получение доступных слотов врача
    path('<int:doctor_id>/available-slots/', views.doctor_available_slots, name='doctor_available_slots'),
    
    # Получение расписания врача
    path('<int:doctor_id>/schedule/', views.doctor_schedule, name='doctor_schedule'),
    
    # Создание записи на прием
    path('<int:doctor_id>/appointments/', views.create_appointment, name='create_appointment'),
]