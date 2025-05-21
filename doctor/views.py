from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Doctor, Schedule, Specialization
from .serializers import DoctorSerializer, ScheduleSerializer, SpecializationSerializer
from datetime import datetime
from django.core.exceptions import ValidationError

# Create your views here.

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Разрешение на изменение только для администраторов.
    Чтение доступно всем авторизованным пользователям.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

class DoctorViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления данными врачей.
    
    Attributes:
        serializer_class: Класс сериализатора
        permission_classes: Классы разрешений
        parser_classes: Классы парсеров для обработки файлов
    """
    serializer_class = DoctorSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        """
        Получение списка активных врачей с возможностью фильтрации по специализации.
        """
        queryset = Doctor.objects.filter(is_active=True)
        specialization = self.request.query_params.get('specialization', None)
        if specialization:
            queryset = queryset.filter(specialization__name_specialization=specialization)
        return queryset

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def upload_photo(self, request, pk=None):
        """
        Загрузка фотографии врача.
        Только для администраторов.
        """
        doctor = self.get_object()
        if 'photo' not in request.FILES:
            return Response(
                {'error': 'Необходимо предоставить файл фотографии'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        doctor.photo = request.FILES['photo']
        try:
            doctor.full_clean()  # Запускаем валидацию
            doctor.save()
            return Response(
                {'message': 'Фотография успешно загружена'},
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAdminUser])
    def remove_photo(self, request, pk=None):
        """
        Удаление фотографии врача.
        Только для администраторов.
        """
        doctor = self.get_object()
        if doctor.photo:
            doctor.photo.delete()
            doctor.save()
            return Response(
                {'message': 'Фотография успешно удалена'},
                status=status.HTTP_200_OK
            )
        return Response(
            {'error': 'У врача нет фотографии'},
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=True, methods=['get'])
    def available_slots(self, request, pk=None):
        doctor = self.get_object()
        date_str = request.query_params.get('date')
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response(
                {"error": "Неверный формат даты. Используйте YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        serializer = self.get_serializer(doctor, context={'date': date})
        return Response(serializer.data['available_slots'])

class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Schedule.objects.all()
        elif hasattr(user, 'doctor'):
            return Schedule.objects.filter(doctor=user.doctor)
        return Schedule.objects.none()

class SpecializationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Specialization.objects.all()
    serializer_class = SpecializationSerializer
    permission_classes = [permissions.IsAuthenticated]
