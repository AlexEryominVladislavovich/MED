from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Doctor, Specialization, Schedule, ScheduleTemplate, TimeSlot, DoctorPhoto
import re
from datetime import datetime, timedelta

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = ['id']

class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = ['id', 'name_specialization', 'description_specialization']
        read_only_fields = ['id']

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

    class Meta:
        model = Doctor
        fields = [
            'id', 'user',  'patronymic', 'room_number', 'bio', 'phone_number',
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

class ScheduleTemplateSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = ScheduleTemplate
        fields = [
            'id', 'doctor', 'day_of_week', 'day_name',
            'start_time', 'end_time', 'break_start', 'break_end',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError('Время начала должно быть меньше времени окончания')

        break_start = data.get('break_start')
        break_end = data.get('break_end')
        
        if break_start and break_end:
            if break_start >= break_end:
                raise serializers.ValidationError('Время начала перерыва должно быть меньше времени окончания')
            if break_start < data['start_time'] or break_end > data['end_time']:
                raise serializers.ValidationError('Перерыв должен быть в рамках рабочего времени')

        # Проверка на пересечение с существующими шаблонами
        doctor = data.get('doctor')
        day_of_week = data.get('day_of_week')
        
        if doctor and day_of_week:
            existing = ScheduleTemplate.objects.filter(
                doctor=doctor,
                day_of_week=day_of_week
            )
            
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
                
            if existing.exists():
                raise serializers.ValidationError('У врача уже есть шаблон на этот день')
        
        return data

class TimeSlotSerializer(serializers.ModelSerializer):
    end_time = serializers.TimeField(source='get_end_time', read_only=True)
    slot_type_display = serializers.CharField(source='get_slot_type_display', read_only=True)
    
    class Meta:
        model = TimeSlot
        fields = [
            'id', 'doctor', 'template', 'date', 'start_time',
            'end_time', 'duration', 'slot_type', 'slot_type_display',
            'is_available', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'end_time', 'created_at', 'updated_at']

    def validate(self, data):
        # Проверка рабочих часов
        if data.get('template'):
            start_time = data['start_time']
            duration = data.get('duration', 30)
            end_time = (datetime.combine(datetime.min, start_time) + 
                       timedelta(minutes=duration)).time()
            
            template = data['template']
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

        # Проверка пересечений
        doctor = data.get('doctor')
        date = data.get('date')
        start_time = data.get('start_time')
        duration = data.get('duration', 30)
        
        if doctor and date and start_time:
            end_time = (datetime.combine(datetime.min, start_time) + 
                       timedelta(minutes=duration)).time()
            
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
        
        return data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['end_time'] = instance.get_end_time()
        return data

class DoctorPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = DoctorPhoto
        fields = ['id', 'image', 'order', 'photo_url']
        read_only_fields = ['id', 'photo_url']

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None

class DoctorDetailSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    specialization = SpecializationSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()
    photos = DoctorPhotoSerializer(many=True, read_only=True, source='photos.all')
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'user', 'patronymic', 'full_name', 'room_number',
            'bio', 'phone_number', 'specialization', 'photo_url',
            'photos', 'is_active'
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

class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = [
            'id', 'date', 'start_time', 'duration',
            'slot_type', 'is_available'
        ]

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





