import os
import re
import io
import logging
from datetime import datetime, timedelta

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MinLengthValidator, 
    MaxLengthValidator,
    RegexValidator, 
    MinValueValidator, 
    MaxValueValidator, 
    FileExtensionValidator
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, get_language
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from rest_framework import serializers

from .models import (
    Doctor, 
    Specialization, 
    Schedule, 
    ScheduleTemplate, 
    TimeSlot, 
    DoctorPhoto, 
    Treatment, 
    TreatmentSession, 
    TreatmentPhoto
)
from patient.models import Profile, Appointment
from patient.serializers import ProfileSerializer, AppointmentCreateSerializer


logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = ['id']

class SpecializationSerializer(serializers.ModelSerializer):
    name_specialization = serializers.SerializerMethodField()
    description_specialization = serializers.SerializerMethodField()

    class Meta:
        model = Specialization
        fields = ['id', 'name_specialization', 'description_specialization']
        read_only_fields = ['id']

    def get_name_specialization(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'name_specialization_{lang}', obj.name_specialization)

    def get_description_specialization(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'description_specialization_{lang}', obj.description_specialization)

class ScheduleSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = Schedule
        fields = ['id', 'day_of_week', 'day_name', 'start_time', 'end_time', 
                 'break_start', 'break_end', 'doctor']
        read_only_fields = ['id']

    def validate(self, data):
        if 'break_start' in data and 'break_end' in data:
            if data['break_start'] and data['break_end']:
                if data['break_start'] >= data['break_end']:
                    raise serializers.ValidationError(
                        'Время начала перерыва должно быть меньше времени окончания'
                    )
        return data

class DoctorSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Doctor.
    
    Attributes:
        user: Данные пользователя
        specialization: Специализации врача
        schedules: Расписание врача
        available_slots: Доступные слоты для записи
        photo_url: URL фотографии врача
    """
    user = UserSerializer()
    specialization = SpecializationSerializer(many=True, read_only=True)
    schedules = ScheduleSerializer(many=True, read_only=True)
    available_slots = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    full_bio = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'user',  'patronymic', 'room_number', 'bio', 'full_bio', 'phone_number',
            'specialization', 'schedules', 'is_active', 'available_slots',
            'photo', 'photo_url'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'photo_url']
        extra_kwargs = {
            'photo': {'write_only': True}  # Фото передается только при записи
        }

    def validate_room_number(self, value):
        if not re.match(r'^\d{3}[A-Za-z]?$', value):
            raise serializers.ValidationError('Формат кабинета: 3 цифры + опциональная буква (например: 101, 201А)')
        return value

    def validate_bio(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError('Биография не должна превышать 1000 символов')
        return value

    def get_available_slots(self, obj):
        date = self.context.get('date')
        if date:
            slots = obj.get_available_slots(date)
            return TimeSlotSerializer(slots, many=True).data
        return []

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        elif obj.photo:
            return obj.photo.url
        return None

    def get_bio(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'bio_{lang}', obj.bio)

    def get_full_bio(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'full_bio_{lang}', obj.full_bio)

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user = User.objects.create_user(**user_data)
        doctor = Doctor.objects.create(user=user, **validated_data)
        return doctor

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', None)
        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save()
        return super().update(instance, validated_data)

class TreatmentPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPhoto
        fields = ['id', 'image', 'session', 'description', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def validate_image(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(_('Максимальный размер фотографии 10мб'))
        if not value.content_type.startswith('image/'):
            raise serializers.ValidationError(_('Фотография должна быть изображением'))
        return value
    
    def validate_description(self, value):
        if len(value) > 2000:
            raise serializers.ValidationError(_('Описание не должно превышать 2000 символов'))
        if not RegexValidator(
            regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s.,!?()-]+$',
        ).regex.match(value):
            raise serializers.ValidationError(_('Описание может содержать только русские, кыргызские, английские буквы, цифры, точки, запятые, восклицательные и вопросительные знаки, скобки и дефис'))
        return value

class TreatmentSessionSerializer(serializers.ModelSerializer):
    treatment = serializers.PrimaryKeyRelatedField(queryset=Treatment.objects.all())
    appointment = serializers.PrimaryKeyRelatedField(queryset=Appointment.objects.all())        
    photos = TreatmentPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = TreatmentSession
        fields = ['id', 'treatment', 'appointment', 'photos', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_notes(self, value):
        if len(value) > 4000:
            raise serializers.ValidationError(_('Заметки не должны превышать 4000 символов'))
        if not RegexValidator(
            regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s.,!?()-]+$',
        ).regex.match(value):
            raise serializers.ValidationError(_('Заметки могут содержать только русские, английские буквы, цифры, точки, запятые, восклицательные и вопросительные знаки, скобки и дефис'))
        return value
    
    def validate_treatment(self, value):
        if value.status != 'active':
            raise serializers.ValidationError(_('Нельзя добавить сессию к неактивной истории болезни'))
        return value
    
    def validate_appointment(self, value):
        if value.time_slot.start_time > timezone.now():
            raise serializers.ValidationError(_('Время сессии не может быть в будущем'))
        return value
    
    def validate(self, data):
        treatment = data.get('treatment')
        appointment = data.get('appointment')
        
        if treatment and treatment.status != 'active':
            raise serializers.ValidationError(_('Нельзя добавить сессию к неактивной истории болезни'))
        if appointment and appointment.status != 'visited':
            raise serializers.ValidationError(_('Начальная запись должна быть завершена'))
        if appointment and treatment:
            if appointment.doctor != treatment.doctor:
                raise serializers.ValidationError(_('Врач должен совпадать с врачом из начальной записи'))
            if appointment.patient != treatment.patient:
                raise serializers.ValidationError(_('Пациент должен совпадать с пациентом из начальной записи'))
            if appointment.time_slot.start_time > timezone.now():
                raise serializers.ValidationError(_('Время сессии не может быть в будущем'))
        return data

class TreatmentSerializer(serializers.ModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())
    initial_appointment = serializers.PrimaryKeyRelatedField(queryset=Appointment.objects.all())
    sessions = TreatmentSessionSerializer(many=True, read_only=True)

    class Meta:
        model = Treatment
        fields = ['id', 'patient', 'doctor', 'initial_appointment', 'status', 'diagnosis', 'treatment_plan', 'created_at', 'updated_at', 'sessions']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_diagnosis(self, value): 
        if len(value) < 5 or len(value) > 50:
            raise serializers.ValidationError(_('Диагноз должен содержать от 5 до 50 символов'))
        if not RegexValidator(
            regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s.,!?()-]+$',
        ).regex.match(value):
            raise serializers.ValidationError(_('Диагноз может содержать только русские, английские буквы, цифры, точки, запятые, восклицательные и вопросительные знаки, скобки и дефис'))
        return value
    
    def validate_treatment_plan(self, value):
        if len(value) < 10 or len(value) > 2000:
            raise serializers.ValidationError(_('План лечения должен содержать от 10 до 2000 символов'))
        if not RegexValidator(
            regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s.,!?()-]+$',
        ).regex.match(value):
            raise serializers.ValidationError(_('План лечения может содержать только русские, английские буквы, цифры, точки, запятые, восклицательные и вопросительные знаки, скобки и дефис'))
        return value
    
    def validate_initial_appointment(self, value):
        if value.status != 'visited':
            raise serializers.ValidationError(_('Начальная запись должна быть посещена'))
        return value

    def validate(self, data):
        initial_appointment = data.get('initial_appointment')
        doctor = data.get('doctor')
        patient = data.get('patient')

        if initial_appointment:
            if initial_appointment.status != 'visited':
                raise serializers.ValidationError({
                    'initial_appointment': _('Начальная запись должна быть завершена')
                })
            if initial_appointment.doctor != doctor:
                raise serializers.ValidationError({
                    'doctor': _('Врач должен совпадать с врачом из начальной записи')
                })
            if initial_appointment.patient != patient:
                raise serializers.ValidationError({
                    'patient': _('Пациент должен совпадать с пациентом из начальной записи')
                })
        return data

class ScheduleTemplateSerializer(serializers.ModelSerializer):
    days_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduleTemplate
        fields = [
            'id', 'doctor', 'days_of_week', 'days_display',
            'start_time', 'end_time', 'break_start', 'break_end',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'days_display']

    def get_days_display(self, obj):
        return obj.get_days_display()

    def validate_days_of_week(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Должен быть списком')
        if not all(isinstance(day, int) and 1 <= day <= 7 for day in value):
            raise serializers.ValidationError('Каждый день должен быть числом от 1 до 7')
        if len(set(value)) != len(value):
            raise serializers.ValidationError('Дни не должны повторяться')
        return sorted(value)

    def validate(self, data):
        if data.get('start_time') and data.get('end_time'):
            if data['start_time'] >= data['end_time']:
                raise serializers.ValidationError('Время начала должно быть меньше времени окончания')

        break_start = data.get('break_start')
        break_end = data.get('break_end')
        
        if break_start and break_end:
            if break_start >= break_end:
                raise serializers.ValidationError('Время начала перерыва должно быть меньше времени окончания')
            if break_start < data['start_time'] or break_end > data['end_time']:
                raise serializers.ValidationError('Перерыв должен быть в рамках рабочего времени')

        # Проверка уникальности дней для врача
        doctor = data.get('doctor')
        days_of_week = data.get('days_of_week', [])
        
        if doctor and days_of_week:
            if self.instance:  # Если это обновление существующего шаблона
                conflicts = ScheduleTemplate.objects.filter(
                    doctor=doctor,
                    is_active=True
                ).exclude(pk=self.instance.pk)
            else:  # Если это создание нового шаблона
                conflicts = ScheduleTemplate.objects.filter(
                    doctor=doctor,
                    is_active=True
                )

            for template in conflicts:
                if any(day in template.days_of_week for day in days_of_week):
                    raise serializers.ValidationError(
                        'У врача уже есть активный шаблон для некоторых из указанных дней'
                    )
        
        return data

    def create(self, validated_data):
        days = validated_data.pop('days_of_week', [])
        template = super().create(validated_data)
        
        for day in days:
            ScheduleTemplateDays.objects.create(
                template=template,
                day_of_week=day
            )
        
        return template

    def update(self, instance, validated_data):
        days = validated_data.pop('days_of_week', None)
        template = super().update(instance, validated_data)
        
        if days is not None:
            # Удаляем старые дни
            instance.template_days.all().delete()
            # Создаем новые
            for day in days:
                ScheduleTemplateDays.objects.create(
                    template=template,
                    day_of_week=day
                )
        
        return template

class TimeSlotSerializer(serializers.ModelSerializer):
    end_time = serializers.TimeField(source='get_end_time', read_only=True)
    slot_type_display = serializers.CharField(source='get_slot_type_display', read_only=True)
    
    class Meta:
        model = TimeSlot
        fields = [
            'id', 'doctor', 'date', 'start_time', 'end_time',
            'duration', 'slot_type', 'slot_type_display',
            'is_available', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'end_time', 'created_at', 'updated_at', 'duration']

    def validate(self, data):
        # Проверка типа слота
        slot_type = data.get('slot_type')
        start_time = data.get('start_time')
        
        if not start_time:
            raise serializers.ValidationError('Время начала обязательно')
            
        if not slot_type:
            raise serializers.ValidationError('Тип слота обязателен')

        # Проверка пересечений
        doctor = data.get('doctor')
        date = data.get('date')
        
        if doctor and date and start_time:
            end_time = (datetime.combine(datetime.min, start_time) + 
                       timedelta(minutes=TimeSlot.SLOT_DURATIONS[slot_type])).time()
            
            overlapping = TimeSlot.objects.filter(
                doctor=doctor,
                date=date,
                start_time__lt=end_time,
                is_available=True
            )
            
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
                
            for slot in overlapping:
                if slot.get_end_time() > start_time:
                    raise serializers.ValidationError('Слот пересекается с существующими')

        # Проверка рабочих часов только если есть шаблон
        if data.get('template'):
            template = data['template']
            duration = TimeSlot.SLOT_DURATIONS[slot_type]
            end_time = (datetime.combine(datetime.min, start_time) + 
                       timedelta(minutes=duration)).time()
            
            if start_time < template.start_time or end_time > template.end_time:
                raise serializers.ValidationError(
                    'Слот должен быть в рамках рабочего времени шаблона'
                )

            # Проверка перерыва
            if template.break_start and template.break_end:
                if (
                    (start_time >= template.break_start and start_time < template.break_end) or
                    (end_time > template.break_start and end_time <= template.break_end)
                ):
                    raise serializers.ValidationError('Слот не может пересекаться с перерывом')
        
        return data

    def create(self, validated_data):
        # Устанавливаем длительность в зависимости от типа слота
        validated_data['duration'] = TimeSlot.SLOT_DURATIONS[validated_data['slot_type']]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Устанавливаем длительность в зависимости от типа слота
        if 'slot_type' in validated_data:
            validated_data['duration'] = TimeSlot.SLOT_DURATIONS[validated_data['slot_type']]
        return super().update(instance, validated_data)

class DoctorPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    photo_sizes = serializers.SerializerMethodField()

    class Meta:
        model = DoctorPhoto
        fields = ['id', 'photo_url', 'photo_sizes', 'order']

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None

    def get_photo_sizes(self, obj):
        request = self.context.get('request')
        if not obj.image:
            return None

        # Получаем базовый URL изображения
        base_url = obj.image.url
        filename = os.path.basename(base_url)
        path = os.path.dirname(base_url)

        # Формируем URLs для разных размеров
        sizes = {
            'small': f"{path}/small_{filename}",
            'medium': f"{path}/medium_{filename}",
            'large': f"{path}/large_{filename}"
        }

        # Если есть request, преобразуем в абсолютные URLs
        if request:
            return {
                size: request.build_absolute_uri(url)
                for size, url in sizes.items()
            }
        return sizes

class DoctorDetailSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    specialization = SpecializationSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()
    photos = DoctorPhotoSerializer(many=True, read_only=True, source='photos.all')
    photo_url = serializers.SerializerMethodField()
    photo_sizes = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    full_bio = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'user', 'patronymic', 'full_name', 'room_number',
            'bio', 'full_bio', 'phone_number', 'specialization', 'photo_url',
            'photo_sizes', 'photos', 'is_active'
        ]

    def get_full_name(self, obj):
        return f"{obj.user.last_name} {obj.user.first_name} {obj.patronymic}".strip()

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        elif obj.photo:
            return obj.photo.url
        return None

    def get_photo_sizes(self, obj):
        request = self.context.get('request')
        if not obj.photo:
            return None

        # Получаем базовый URL изображения
        base_url = obj.photo.url
        filename = os.path.basename(base_url)
        path = os.path.dirname(base_url)

        # Формируем URLs для разных размеров
        sizes = {
            'small': f"{path}/small_{filename}",
            'medium': f"{path}/medium_{filename}",
            'large': f"{path}/large_{filename}"
        }

        # Если есть request, преобразуем в абсолютные URLs
        if request:
            return {
                size: request.build_absolute_uri(url)
                for size, url in sizes.items()
            }
        return sizes

    def get_bio(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'bio_{lang}', obj.bio)

    def get_full_bio(self, obj):
        lang = get_language() or 'ru'
        return getattr(obj, f'full_bio_{lang}', obj.full_bio)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Добавляем request в контекст для DoctorPhotoSerializer
        photos_serializer = DoctorPhotoSerializer(
            instance.photos.all(),
            many=True,
            context=self.context
        )
        data['photos'] = photos_serializer.data
        return data


class ScheduleSerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            'id', 'day_of_week', 'day_of_week_display',
            'start_time', 'end_time', 'break_start', 'break_end'
        ]

    def get_day_of_week_display(self, obj):
        return obj.get_day_of_week_display()

class DoctorListSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    specialization = SpecializationSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'user', 'full_name', 'patronymic', 'photo', 'photo_url',
            'specialization', 'room_number', 'bio', 'is_active'
        ]

    def get_full_name(self, obj):
        return f"{obj.user.last_name} {obj.user.first_name} {obj.patronymic or ''}".strip()

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        elif obj.photo:
            return obj.photo.url
        return None





