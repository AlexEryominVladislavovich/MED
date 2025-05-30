from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Doctor, Schedule, Specialization, TimeSlot
from .serializers import (
    DoctorSerializer,
    ScheduleSerializer,
    SpecializationSerializer,
    DoctorDetailSerializer,
    DoctorPhotoSerializer,
    TimeSlotSerializer,
    DoctorListSerializer
)
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated

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
        parser_classes: Классы парсеров для обработки файлов
    """
    serializer_class = DoctorListSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [AllowAny]  # Временно разрешаем доступ всем

    def get_serializer_class(self):
        if self.action == 'list':
            return DoctorListSerializer
        return DoctorSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        print(f"Number of doctors found: {queryset.count()}")
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]

    def get_queryset(self):
        """
        Получение списка активных врачей с возможностью фильтрации по специализации.
        """
        queryset = Doctor.objects.filter(is_active=True).select_related('user').prefetch_related('specialization')
        print(f"Base queryset count: {queryset.count()}")
        
        specialization = self.request.query_params.get('specialization', None)
        if specialization:
            queryset = queryset.filter(specialization__name_specialization=specialization)
            print(f"Filtered by specialization count: {queryset.count()}")
        
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

@api_view(['GET'])
def doctor_detail(request, doctor_id):
    """
    Получение детальной информации о враче
    """
    doctor = get_object_or_404(
        Doctor.objects.prefetch_related('photos').select_related('user'),
        id=doctor_id,
        is_active=True
    )
    serializer = DoctorDetailSerializer(doctor, context={'request': request})
    print("Doctor photos:", doctor.photos.all())  # Добавляем отладочный вывод
    return Response(serializer.data)

@api_view(['GET'])
def doctor_photos(request, doctor_id):
    """
    Получение всех фотографий врача
    """
    doctor = get_object_or_404(Doctor, id=doctor_id, is_active=True)
    serializer = DoctorPhotoSerializer(doctor)
    return Response(serializer.data)

@api_view(['GET'])
def doctor_available_slots(request, doctor_id):
    """
    Получение доступных слотов для записи к врачу
    """
    doctor = get_object_or_404(Doctor, id=doctor_id, is_active=True)
    
    # Получаем параметры запроса
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    
    # Получаем начало и конец периода
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()
    
    # Ограничиваем период 30 днями от текущей даты
    max_date = datetime.now().date() + timedelta(days=30)
    if end_date > max_date:
        end_date = max_date
    
    # Получаем доступные слоты
    slots = TimeSlot.objects.filter(
        doctor=doctor,
        date__gte=start_date,
        date__lt=end_date,
        is_available=True
    ).order_by('date', 'start_time')
    
    serializer = TimeSlotSerializer(slots, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def doctor_schedule(request, doctor_id):
    """
    Получение расписания врача
    """
    doctor = get_object_or_404(Doctor, id=doctor_id, is_active=True)
    schedules = doctor.schedules.all()
    serializer = ScheduleSerializer(schedules, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_appointment(request, doctor_id):
    """
    Создание записи на прием к врачу
    """
    doctor = get_object_or_404(Doctor, id=doctor_id, is_active=True)
    
    # Получаем слот для записи
    slot_id = request.data.get('slot_id')
    if not slot_id:
        return Response(
            {'error': 'Необходимо указать временной слот'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    slot = get_object_or_404(TimeSlot, id=slot_id, doctor=doctor, is_available=True)
    
    # Проверяем, не прошло ли время слота
    if slot.date < datetime.now().date():
        return Response(
            {'error': 'Нельзя записаться на прошедшую дату'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Помечаем слот как занятый
    slot.is_available = False
    slot.save()
    
    return Response(
        {'success': True, 'message': 'Запись создана успешно'},
        status=status.HTTP_201_CREATED
    )
