from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Appointment, Review, Notification, kg_phone_validator
from doctor.serializers import DoctorSerializer
from django.utils import timezone
import re


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['user', 'full_name', 'phone_number']
        read_only_fields = ['id']

    # Удаляем всё кроме цифр
    def validate_phone_number(self, value):
        raw = ''.join(filter(str.isdigit, value))

        if len(raw) == 9:
            value = f'+996{raw}'
        elif len(raw) == 10 and raw.startswitc('0'):
            value = f'+996{raw[1:]}'
        elif len(raw) == 12 and raw.startswitc('996'):
            value = f'+{raw}'
        elif len(raw) == 13 and raw.startswitc('+996'):
            value = raw
        else:
            raise serializers.ValidationError(
                'Введите коректный мобильный номер. Например 700123456'
            )
        if Profile.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError('Этот номер уже используется.')

        kg_phone_validator(value)
        return value


class PatientAppointmentSerializer(serializers.ModelSerializer):
    patient = ProfileSerializer(read_only=True)
    doctor = DoctorSerializer(read_only=True)
    status = serializers.CharField(read_only=True)
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'doctor', 'appointment_time', 
            'rescheduled_from', 'visit_reason', 'description', 
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        # Проверяем, что статус изменяется только на "отменен пациентом"
        if 'status' in validated_data:
            if validated_data['status'] != 'cancelled_by_patient':
                raise serializers.ValidationError('Вы можете только отменить запись')
            if instance.status not in ['scheduled']:
                raise serializers.ValidationError('Отменить можно только запланированный приём')
            if instance.appointment_time < timezone.now():
                raise serializers.ValidationError('Нельзя отменить прошедший приём')
        return super().update(instance, validated_data)

class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            'appointment_time', 'rescheduled_from', 
            'visit_reason', 'description'
        ]

    def validate_description(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError('Сообщение не должно превышать 1000 символов')
        return value

    def validate_appointment_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError('Это время некорректно. Данное время уже истекло')
        
        # Проверка рабочих часов
        appointment_time = value.time()
        if appointment_time.hour < 8 or appointment_time.hour >= 19:
            raise serializers.ValidationError('Время приёма должно быть с 8:00 до 19:00')
        
        # Проверка длительности
        if appointment_time.minute % 5 != 0:
            raise serializers.ValidationError('Время приёма должно быть кратно 5 минутам')
            
        return value

    def validate(self, data):
        patient = data.get('patient')
        doctor = data.get('doctor')
        appointment_time = data.get('appointment_time')

        instance = getattr(self, 'instance', None)

        if Appointment.objects.filter(
            doctor=doctor,
            appointment_time = appointment_time
        ).exclude(pk=getattr(instance, 'pk', None)).exists():
            raise serializers.ValidationError('На это время уже есть запись.')

        if Appointment.objects.filter(
            patient=patient,
            appointment_time = appointment_time
        ).exclude(doctor=doctor).exclude(pk=getattr(instance, 'pk', None)).exists():
            raise serializers.ValidationError('Вы уже записаны к врачу на это время.')
        return data

    def create(self, validated_data):
        validated_data['status'] = 'scheduled'  # Устанавливаем статус по умолчанию
        request = self.context['request']
        validated_data['patient'] = request.user.profile
        return super().create(validated_data)

class PatientAppointmentDetailSerializer(serializers.ModelSerializer):
    doctor = DoctorSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    appointment_time = serializers.SerializerMethodField()
    
    def get_appointment_time(self, obj):
        return {
            'start': obj.time_slot.start_time.strftime('%Y-%m-%d %H:%M'),
            'end': obj.time_slot.end_time.strftime('%Y-%m-%d %H:%M')
        }
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'doctor', 'appointment_time', 'status', 'status_display',
            'description', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

class PatientReviewSerializers(serializers.ModelSerializer):
    patient = ProfileSerializer(read_only=True)
    doctor = DoctorSerializer(read_only=True)
    appointment = PatientAppointmentSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'patient', 'doctor', 'appointment',
            'rating', 'comment', 'create_at'
        ]
        read_only_fields = ['id', 'doctor', 'patient', 'create_at']

    def validate_comment(self, value):
        if len(value) < 5:
            raise serializers.ValidationError('Минимальная длина отзыва - 5 символов')
        if len(value) > 500:
            raise serializers.ValidationError('Максимальная длина отзыва - 500 символов')
        return value

    def validate_rating(self, value):
        if value < 1:
            raise serializers.ValidationError('Минимальная оценка - 1')
        if value > 5:
            raise serializers.ValidationError('Максимальная оценка - 5')
        return value

    def validate(self, data):
        appointment = data.get('appointment')
        user = self.context['request'].user

        if appointment.patient.user != user:
            raise serializers.ValidationError('Вы можетет оставлять заявки только на свой приём')

        if appointment.status != 'visited':
            raise serializers.ValidationError('В можете оставить отзыв только после посещения приёма')

        return data

    # Используем метод create послольку поля 'doctor' и 'patient' находятся в поле read_only_fields
    def create(self, validated_data):
        # Автоподставка doctor и patient
        appointment = validated_data['appointment']
        validated_data['doctor'] =  appointment.doctor
        validated_data['patient'] = appointment.patient
        return super().create(validate_data)



class PatientNotificationSerializers(serializers.ModelSerializer):
    appointment = PatientAppointmentSerializer(read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'appointment', 'profile', 'message_type',
            'message', 'status', 'sent_at', 'error_message'
        ]
        read_only_fields = [
            'id', 'sent_at', 'status', 'error_message'
        ]

    def validate_message(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError('Сообщение должно содержать минимум 5 символов')
        return value

    def validate(self, data):
        request = self.context['request']
        profile  = request.user.profile # Автоматически получаем профиль

        appointment = data.get('appointment')
        if appointment and appointment.patient != profile:
            raise serializers.ValidationError('Нельзя отправить сообщение пациенту не с заявки')
        return data








