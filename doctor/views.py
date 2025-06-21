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
from django.utils import timezone
import logging
from django.views.decorators.cache import cache_control
from django.utils.decorators import method_decorator
from django.core.cache import cache
from django.conf import settings
import hashlib
import uuid
from patient.models import Profile, Appointment
import re
from django.db.utils import IntegrityError
from django.contrib.auth.models import User
from django.db import transaction

# Create your views here.

logger = logging.getLogger(__name__)

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Разрешение на изменение только для администраторов.
    Чтение доступно всем авторизованным пользователям.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

@method_decorator(cache_control(max_age=3600), name='dispatch')
class DoctorViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления данными врачей.
    """
    serializer_class = DoctorListSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DoctorDetailSerializer
        return DoctorListSerializer

    def get_queryset(self):
        """
        Получение списка активных врачей
        """
        try:
            today = timezone.now().date()
            logger.info(f"Получение списка врачей на дату: {today}")
            
            # Базовый queryset с оптимизированными запросами
            queryset = Doctor.objects.filter(
                is_active=True
            ).select_related(
                'user'
            ).prefetch_related(
                'specialization',
                'photos',
                'schedule_templates',
                'time_slots'
            )
            
            logger.info(f"Найдено активных врачей: {queryset.count()}")

            # Фильтрация по специализации
            specialization = self.request.query_params.get('specialization')
            if specialization:
                queryset = queryset.filter(specialization__name_specialization=specialization)
                logger.info(f"После фильтрации по специализации '{specialization}': {queryset.count()} врачей")

            # Проверяем наличие активных шаблонов
            doctors_with_templates = queryset.filter(
                schedule_templates__is_active=True
            ).distinct()
            
            logger.info(f"Врачей с активными шаблонами: {doctors_with_templates.count()}")

            if not doctors_with_templates.exists():
                logger.warning("Нет врачей с активными шаблонами")
                # Возвращаем всех активных врачей, если нет шаблонов
                return queryset

            # Проверяем наличие доступных слотов
            doctors_with_slots = doctors_with_templates.filter(
                time_slots__date__gte=today,
                time_slots__is_available=True
            ).distinct()
            
            logger.info(f"Врачей с доступными слотами: {doctors_with_slots.count()}")

            # Если есть врачи со слотами, возвращаем их
            if doctors_with_slots.exists():
                return doctors_with_slots

            # Если нет врачей со слотами, возвращаем врачей с шаблонами
            return doctors_with_templates

        except Exception as e:
            logger.error(f"Ошибка при получении списка врачей: {str(e)}")
            # В случае ошибки возвращаем всех активных врачей
            return Doctor.objects.filter(is_active=True)

    def list(self, request, *args, **kwargs):
        try:
            # Запускаем генерацию слотов перед получением списка
            from .middleware import SlotGenerationMiddleware
            SlotGenerationMiddleware(None).generate_slots()
            
            queryset = self.get_queryset()
            
            if not queryset.exists():
                logger.warning("Нет доступных врачей для отображения")
                return Response(
                    {
                        "message": "Нет доступных врачей",
                        "details": "В данный момент нет активных врачей. Пожалуйста, попробуйте позже."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = self.get_serializer(queryset, many=True)
            logger.info(f"Успешно получен список из {len(serializer.data)} врачей")
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Ошибка при формировании списка врачей: {str(e)}")
            return Response(
                {
                    "message": "Ошибка при получении списка врачей",
                    "details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'available_slots']:
            return [AllowAny()]
        return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]

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
        
        # Очищаем кэш при загрузке новой фотографии
        cache_key = f'doctor_photo_{doctor.id}'
        cache.delete(cache_key)
        
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
            # Очищаем кэш при удалении фотографии
            cache_key = f'doctor_photo_{doctor.id}'
            cache.delete(cache_key)
            
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

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def available_slots(self, request, pk=None):
        from datetime import timedelta
        doctor = self.get_object()
        date_str = request.query_params.get('date')
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        
        try:
            today = timezone.localtime().date()
            now = timezone.localtime()
            
            if date_str:
                # Если передана конкретная дата
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    logger.info(f"Запрошена дата: {date}")
                    
                    # Получаем все слоты для диагностики
                    all_slots = TimeSlot.objects.filter(
                            doctor=doctor,
                            date=date,
                            is_deleted=False
                    )
                    
                    # Получаем только доступные слоты
                    available_slots = all_slots.filter(is_available=True)
                    
                    # ДИАГНОСТИКА: Проверяем слоты с записями
                    from patient.models import Appointment
                    slots_with_appointments = []
                    for slot in all_slots:
                        if Appointment.objects.filter(time_slot=slot).exists():
                            slots_with_appointments.append(slot.id)
                    
                    logger.info(f"=== ДИАГНОСТИКА СЛОТОВ ===")
                    logger.info(f"Всего слотов на {date}: {all_slots.count()}")
                    logger.info(f"Доступных слотов: {available_slots.count()}")
                    logger.info(f"Слотов с записями: {len(slots_with_appointments)}")
                    if slots_with_appointments:
                        logger.warning(f"ID слотов с записями: {slots_with_appointments}")
                    
                    # Проверяем, есть ли слоты, которые помечены как доступные, но имеют записи
                    problematic_slots = []
                    for slot in available_slots:
                        if Appointment.objects.filter(time_slot=slot).exists():
                            problematic_slots.append(slot.id)
                    
                    if problematic_slots:
                        logger.error(f"НАЙДЕНЫ ПРОБЛЕМНЫЕ СЛОТЫ! ID: {problematic_slots}")
                        # Исключаем проблемные слоты из результатов
                        available_slots = available_slots.exclude(id__in=problematic_slots)
                        logger.info(f"После исключения проблемных слотов: {available_slots.count()}")
                    
                    slots = available_slots.order_by('date', 'start_time')
                    
                    logger.info(f"Итоговое количество слотов: {slots.count()}")
                    
                except ValueError:
                    return Response(
                        {'error': 'Неверный формат даты. Используйте YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            elif year and month:
                # Если переданы год и месяц
                try:
                    year = int(year)
                    month = int(month)
                    if not (1 <= month <= 12):
                        raise ValueError("Неверный номер месяца")
                    
                    start_date = datetime(year, month, 1).date()
                    if month == 12:
                        end_date = datetime(year + 1, 1, 1).date()
                    else:
                        end_date = datetime(year, month + 1, 1).date()
                    logger.info(f"Используем диапазон месяца: с {start_date} по {end_date}")
                    
                    # Получаем все слоты для диагностики
                    all_slots = TimeSlot.objects.filter(
                        doctor=doctor,
                        date__gte=start_date,
                        date__lt=end_date,
                        is_deleted=False
                    )
                    
                    # Получаем только доступные слоты
                    available_slots = all_slots.filter(is_available=True)
                    
                    # ДИАГНОСТИКА: Проверяем слоты с записями
                    from patient.models import Appointment
                    slots_with_appointments = []
                    for slot in all_slots:
                        if Appointment.objects.filter(time_slot=slot).exists():
                            slots_with_appointments.append(slot.id)
                    
                    logger.info(f"=== ДИАГНОСТИКА СЛОТОВ ===")
                    logger.info(f"Всего слотов на период: {all_slots.count()}")
                    logger.info(f"Доступных слотов: {available_slots.count()}")
                    logger.info(f"Слотов с записями: {len(slots_with_appointments)}")
                    if slots_with_appointments:
                        logger.warning(f"ID слотов с записями: {slots_with_appointments}")
                    
                    # Проверяем, есть ли слоты, которые помечены как доступные, но имеют записи
                    problematic_slots = []
                    for slot in available_slots:
                        if Appointment.objects.filter(time_slot=slot).exists():
                            problematic_slots.append(slot.id)
                    
                    if problematic_slots:
                        logger.error(f"НАЙДЕНЫ ПРОБЛЕМНЫЕ СЛОТЫ! ID: {problematic_slots}")
                        # Исключаем проблемные слоты из результатов
                        available_slots = available_slots.exclude(id__in=problematic_slots)
                        logger.info(f"После исключения проблемных слотов: {available_slots.count()}")
                    
                    slots = available_slots.order_by('date', 'start_time')
                    
                    logger.info(f"Итоговое количество слотов: {slots.count()}")
                    
                except ValueError as e:
                    return Response(
                        {'error': f'Неверные параметры года/месяца: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Если не переданы параметры, используем текущий месяц
                start_date = today.replace(day=1)
                if today.month == 12:
                    end_date = datetime(today.year + 1, 1, 1).date()
                else:
                    end_date = datetime(today.year, today.month + 1, 1).date()
                logger.info(f"Используем текущий месяц: с {start_date} по {end_date}")
                
                # Получаем все слоты для диагностики
                all_slots = TimeSlot.objects.filter(
                    doctor=doctor,
                    date__gte=start_date,
                    date__lt=end_date,
                    is_deleted=False
                )
                
                # Получаем только доступные слоты
                available_slots = all_slots.filter(is_available=True)
                
                # ДИАГНОСТИКА: Проверяем слоты с записями
                from patient.models import Appointment
                slots_with_appointments = []
                for slot in all_slots:
                    if Appointment.objects.filter(time_slot=slot).exists():
                        slots_with_appointments.append(slot.id)
                
                logger.info(f"=== ДИАГНОСТИКА СЛОТОВ ===")
                logger.info(f"Всего слотов на период: {all_slots.count()}")
                logger.info(f"Доступных слотов: {available_slots.count()}")
                logger.info(f"Слотов с записями: {len(slots_with_appointments)}")
                if slots_with_appointments:
                    logger.warning(f"ID слотов с записями: {slots_with_appointments}")
                
                # Проверяем, есть ли слоты, которые помечены как доступные, но имеют записи
                problematic_slots = []
                for slot in available_slots:
                    if Appointment.objects.filter(time_slot=slot).exists():
                        problematic_slots.append(slot.id)
                
                if problematic_slots:
                    logger.error(f"НАЙДЕНЫ ПРОБЛЕМНЫЕ СЛОТЫ! ID: {problematic_slots}")
                    # Исключаем проблемные слоты из результатов
                    available_slots = available_slots.exclude(id__in=problematic_slots)
                    logger.info(f"После исключения проблемных слотов: {available_slots.count()}")
                
                slots = available_slots.order_by('date', 'start_time')
                
                logger.info(f"Итоговое количество слотов: {slots.count()}")
            
            logger.info(f"Найдено слотов: {slots.count()}")
            for slot in slots:
                logger.debug(f"Слот: дата={slot.date}, время={slot.start_time}, тип={slot.slot_type}")
            
            serializer = TimeSlotSerializer(slots, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Ошибка при получении слотов: {str(e)}")
            return Response(
                {'error': f'Ошибка при получении слотов: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def schedule(self, request, pk=None):
        """
        Получение расписания врача
        """
        doctor = self.get_object()
        schedules = doctor.schedules.all()
        serializer = ScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def create_appointment(self, request, pk=None):
        """
        Создание записи на прием к врачу для авторизованных и неавторизованных пользователей
        """
        doctor = self.get_object()
        
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

        # Получаем данные пациента
        patient_name = request.data.get('patient_name', '').strip()
        patient_phone = request.data.get('patient_phone', '').strip()
        comment = request.data.get('comment', '').strip()

        # Валидация имени
        if not patient_name:
            return Response(
                {'error': 'Имя пациента обязательно для заполнения'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if len(patient_name) < 2:
            return Response(
                {'error': 'Имя пациента должно содержать минимум 2 символа'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not re.match(r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s\-]+$', patient_name):
            return Response(
                {'error': 'Имя может содержать только русские, английские буквы, символы Ң ң, Ө ө, Ү ү и дефис'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Валидация телефона
        if not patient_phone:
            return Response(
                {'error': 'Номер телефона обязателен для заполнения'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not re.match(r'^\+996(22\d|55\d|70\d|99\d|77\d|54\d|51\d|57\d|56\d|50\d)\d{6}$', patient_phone):
            return Response(
                {'error': 'Неверный формат номера телефона. Номер должен начинаться с +996 и содержать 9 цифр после кода страны'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Создаем или получаем профиль пациента
            if request.user.is_authenticated:
                patient = request.user.profile
            else:
                # Пытаемся найти существующий профиль по номеру телефона
                patient = Profile.objects.filter(phone_number=patient_phone).first()
                if not patient:
                    try:
                        # Если профиль не найден, создаем новый
                        patient = Profile.objects.create(
                            username=f"guest_{uuid.uuid4().hex[:8]}",
                            full_name=patient_name,
                            phone_number=patient_phone,
                            is_guest=True
                        )
                    except IntegrityError:
                        # Если возникла ошибка уникальности, значит профиль с таким номером уже существует
                        # Пробуем найти его еще раз после нормализации
                        normalized_phone = patient_phone
                        if not normalized_phone.startswith('+'):
                            normalized_phone = f'+{normalized_phone}'
                        patient = Profile.objects.filter(phone_number=normalized_phone).first()
                        if not patient:
                            return Response(
                                {'error': 'Не удалось создать профиль. Возможно, номер телефона уже используется.'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                
                # Если профиль найден, обновляем имя если оно изменилось
                if patient.full_name != patient_name:
                    patient.full_name = patient_name
                    patient.save()

            # Создаем запись на прием
            appointment = Appointment.objects.create(
                patient=patient,
                doctor=doctor,
                time_slot=slot,
                description=comment,
                status='scheduled'
            )
            
            # Помечаем слот как занятый
            slot.is_available = False
            slot.save()
            
            return Response(
                {
                    'success': True,
                    'message': 'Запись создана успешно',
                    'appointment_id': appointment.id
                },
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.all()
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

@cache_control(max_age=3600)
@api_view(['GET'])
def doctor_detail(request, doctor_id):
    """
    Получение детальной информации о враче с кэшированием
    """
    cache_key = f'doctor_detail_{doctor_id}'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return Response(cached_data)
    
    doctor = get_object_or_404(
        Doctor.objects.prefetch_related('photos').select_related('user'),
        id=doctor_id,
        is_active=True
    )
    serializer = DoctorDetailSerializer(doctor, context={'request': request})
    data = serializer.data
    
    # Кэшируем данные на 1 час
    cache.set(cache_key, data, timeout=3600)
    
    return Response(data)

@cache_control(max_age=3600)
@api_view(['GET'])
def doctor_photos(request, doctor_id):
    """
    Получение всех фотографий врача с кэшированием
    """
    cache_key = f'doctor_photos_{doctor_id}'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return Response(cached_data)
    
    doctor = get_object_or_404(Doctor, id=doctor_id, is_active=True)
    serializer = DoctorPhotoSerializer(doctor)
    data = serializer.data
    
    # Кэшируем данные на 1 час
    cache.set(cache_key, data, timeout=3600)
    
    return Response(data)

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
@permission_classes([AllowAny])
def create_appointment(request, doctor_id):
    """
    Создание записи на прием к врачу.
    """
    try:
        # Получаем данные из запроса с поддержкой разных названий полей
        time_slot_id = request.data.get('time_slot_id') or request.data.get('slot_id')
        comment = request.data.get('comment', '') or request.data.get('description', '')
        phone_number = request.data.get('phone_number') or request.data.get('patient_phone')
        full_name = request.data.get('full_name') or request.data.get('patient_name')

        logger.info(f"=== СОЗДАНИЕ ЗАПИСИ ===")
        logger.info(f"time_slot_id: {time_slot_id}")
        logger.info(f"phone_number: {phone_number}")
        logger.info(f"full_name: {full_name}")

        if not all([time_slot_id, phone_number, full_name]):
            missing_fields = []
            if not time_slot_id:
                missing_fields.append('time_slot_id/slot_id')
            if not phone_number:
                missing_fields.append('phone_number/patient_phone')
            if not full_name:
                missing_fields.append('full_name/patient_name')
            
            return Response(
                {
                    'error': f'Необходимо указать: {", ".join(missing_fields)}',
                    'received_data': {
                        'time_slot_id': time_slot_id,
                        'phone_number': phone_number,
                        'full_name': full_name
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Используем транзакцию для предотвращения гонки условий
        with transaction.atomic():
            # Получаем слот и проверяем его доступность с блокировкой
            try:
                slot = TimeSlot.objects.select_for_update().get(id=time_slot_id)
                logger.info(f"Слот найден: ID={slot.id}, доступен={slot.is_available}")
            except TimeSlot.DoesNotExist:
                logger.error(f"Слот не найден: ID={time_slot_id}")
                return Response(
                    {'error': 'Указанный слот не найден'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not slot.is_available:
                logger.warning(f"Слот уже занят: ID={slot.id}")
                return Response(
                    {'error': 'Этот слот уже занят'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Проверяем, нет ли уже записи на этот слот
            existing_appointment = Appointment.objects.filter(time_slot=slot).first()
            if existing_appointment:
                logger.error(f"Найдена существующая запись на слот: ID={slot.id}, appointment_id={existing_appointment.id}")
                # Помечаем слот как недоступный, если он не помечен
                if slot.is_available:
                    slot.is_available = False
                    slot.save()
                return Response(
                    {'error': 'Этот слот уже занят'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Получаем или создаем профиль пациента
            try:
                patient = Profile.objects.get(phone_number=phone_number)
                # Обновляем имя, если оно изменилось
                if patient.full_name != full_name:
                    patient.full_name = full_name
                    patient.save()
                    logger.info(f"Найден существующий профиль: ID={patient.id}")
            except Profile.DoesNotExist:
                # Создаем нового пользователя
                username = f"patient_{phone_number.replace('+', '')}"
                user = User.objects.create_user(
                    username=username,
                    password=User.objects.make_random_password()
                )
                # Создаем профиль
                patient = Profile.objects.create(
                    user=user,
                    full_name=full_name,
                    phone_number=phone_number
                )
                logger.info(f"Создан новый профиль: ID={patient.id}")

            # Создаем запись на прием
            appointment = Appointment.objects.create(
                patient=patient,
                doctor=slot.doctor,
                time_slot=slot,
                description=comment,
                status='scheduled'
            )
        
            # Помечаем слот как занятый
            slot.is_available = False
            slot.save()
            
            logger.info(f"Запись успешно создана: appointment_id={appointment.id}, slot_id={slot.id}")
        
            return Response(
                {
                    'success': True,
                    'message': 'Запись создана успешно',
                    'appointment_id': appointment.id
                },
                status=status.HTTP_201_CREATED
            )
    except ValidationError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Ошибка при создании записи: {str(e)}")
        return Response(
            {'error': f'Ошибка при создании записи: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class TimeSlotViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления временными слотами.
    Админ может управлять всеми слотами, врач только своими.
    """
    serializer_class = TimeSlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """
        Переопределяем права доступа:
        - GET запросы доступны всем
        - Остальные действия требуют аутентификации
        """
        if self.action in ['retrieve', 'list']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """
        Определяем queryset в зависимости от действия и пользователя:
        - Для retrieve возвращаем слот независимо от доступности (для проверки)
        - Для list возвращаем только доступные слоты
        - Для админа возвращаем все слоты
        - Для врача возвращаем только его слоты
        - Для остальных возвращаем пустой queryset
        """
        if self.action == 'retrieve':
            # Для получения конкретного слота возвращаем его независимо от доступности
            return TimeSlot.objects.filter(is_deleted=False)
        elif self.action == 'list':
            # Для списка возвращаем только доступные слоты
            return TimeSlot.objects.filter(is_available=True, is_deleted=False)
        
        user = self.request.user
        if user.is_staff:
            return TimeSlot.objects.all()
        elif hasattr(user, 'doctor'):
            return TimeSlot.objects.filter(doctor=user.doctor)
        return TimeSlot.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_staff and hasattr(user, 'doctor'):
            serializer.save(doctor=user.doctor)
        else:
            serializer.save()

    @action(detail=False, methods=['post'])
    def generate_slots(self, request):
        """
        Генерация временных слотов для врача.
        """
        if not hasattr(request.user, 'doctor'):
            return Response(
                {'error': 'Только врачи могут генерировать слоты'},
                status=status.HTTP_403_FORBIDDEN
            )

        doctor = request.user.doctor
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        slot_type = request.data.get('slot_type')

        if not all([start_date, end_date, slot_type]):
            return Response(
                {'error': 'Необходимо указать start_date, end_date и slot_type'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Неверный формат даты. Используйте YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if slot_type not in ['consultation', 'treatment']:
            return Response(
                {'error': 'slot_type должен быть consultation или treatment'},
                status=status.HTTP_400_BAD_REQUEST
            )

        current_date = start_date
        created_slots = []

        while current_date <= end_date:
            # Получаем расписание для текущего дня недели
            day_schedule = Schedule.objects.filter(
                doctor=doctor,
                day_of_week=current_date.isoweekday()
            ).first()

            if day_schedule:
                # Определяем время начала и конца
                if slot_type == 'consultation':
                    # Для консультаций (XX:40 каждого часа)
                    current_time = datetime.combine(current_date, day_schedule.start_time)
                    current_time = current_time.replace(minute=40)
                    end_time = datetime.combine(current_date, day_schedule.end_time)

                    while current_time + timedelta(minutes=15) <= end_time:
                        # Проверяем, не попадает ли слот на перерыв
                        slot_end_time = current_time + timedelta(minutes=15)
                        is_break_time = False

                        if day_schedule.break_start and day_schedule.break_end:
                            break_start = datetime.combine(current_date, day_schedule.break_start)
                            break_end = datetime.combine(current_date, day_schedule.break_end)

                            if (current_time >= break_start and current_time < break_end) or \
                               (slot_end_time > break_start and slot_end_time <= break_end):
                                is_break_time = True

                        if not is_break_time:
                            slot = TimeSlot.objects.create(
                                doctor=doctor,
                                date=current_date,
                                start_time=current_time.time(),
                                slot_type='consultation',
                                is_available=True
                            )
                            created_slots.append(slot)

                        current_time += timedelta(hours=1)

                elif slot_type == 'treatment':
                    # Для лечения (XX:00 каждого часа)
                    current_time = datetime.combine(current_date, day_schedule.start_time)
                    current_time = current_time.replace(minute=0)
                    end_time = datetime.combine(current_date, day_schedule.end_time)

                    while current_time + timedelta(minutes=40) <= end_time:
                        # Проверяем, не попадает ли слот на перерыв
                        slot_end_time = current_time + timedelta(minutes=40)
                        is_break_time = False

                        if day_schedule.break_start and day_schedule.break_end:
                            break_start = datetime.combine(current_date, day_schedule.break_start)
                            break_end = datetime.combine(current_date, day_schedule.break_end)

                            if (current_time >= break_start and current_time < break_end) or \
                               (slot_end_time > break_start and slot_end_time <= break_end):
                                is_break_time = True

                        if not is_break_time:
                            slot = TimeSlot.objects.create(
                                doctor=doctor,
                                date=current_date,
                                start_time=current_time.time(),
                                slot_type='treatment',
                                is_available=True
                            )
                            created_slots.append(slot)

                        current_time += timedelta(hours=1)

            current_date += timedelta(days=1)

        serializer = TimeSlotSerializer(created_slots, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_slots(self, request):
        """
        Получение всех слотов врача.
        """
        if not hasattr(request.user, 'doctor'):
            return Response(
                {'error': 'Только врачи могут просматривать свои слоты'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Получаем параметры фильтрации
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        slot_type = request.query_params.get('slot_type')

        # Базовый queryset
        queryset = TimeSlot.objects.filter(doctor=request.user.doctor)

        # Применяем фильтры
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                pass

        if slot_type in ['consultation', 'treatment']:
            queryset = queryset.filter(slot_type=slot_type)

        serializer = TimeSlotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_slot(self, request, pk=None):
        """
        Обновление временного слота (доступность, время начала).
        """
        try:
            slot = TimeSlot.objects.get(pk=pk)
        except TimeSlot.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Проверяем права доступа
        if not request.user.is_staff and (not hasattr(request.user, 'doctor') or request.user.doctor != slot.doctor):
            return Response(
                {'error': 'У вас нет прав для изменения этого слота'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Получаем новое время начала
        new_start_time = request.data.get('start_time')
        if new_start_time:
            try:
                # Проверяем формат времени
                datetime.strptime(new_start_time, '%H:%M').time()
            except ValueError:
                return Response(
                    {'error': 'Неверный формат времени. Используйте HH:MM'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Обновляем слот
        serializer = TimeSlotSerializer(slot, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_time_slot(request, slot_id):
    """
    Получение информации о конкретном временном слоте
    """
    try:
        slot = TimeSlot.objects.get(id=slot_id, is_deleted=False)
        serializer = TimeSlotSerializer(slot)
        return Response(serializer.data)
    except TimeSlot.DoesNotExist:
        return Response(
            {'error': 'Временной слот не найден'},
            status=status.HTTP_404_NOT_FOUND
        )
