from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Appointment, Review, Notification, kg_phone_validator
from doctor.serializers import DoctorSerializer
from django.utils import timezone
import re

from ..med.wsgi import application


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

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
    patient = ProfileSerializer()
    doctor = DoctorSerializer()
    class Meta:
        model = Appointment
        fields = ['appointment_time', 'rescheduled_from', 'visit_reason', 'description', 'status']

class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['appointment_time', 'rescheduled_from', 'visit_reason', 'description', 'status']

    def validate_description_length(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError('Сообщение не должно привышать 1000 символов')

    def validate_appointment_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError('Это время не корректно. Данное время уже истекло')
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
        request = self.context['request']
        validated_data['patient'] = request.user.profile   # Автоматически добавляет пациента
        return super().create(validated_data)

class PatientReviewSerializers(serializers.ModelSerializer):
    patient = ProfileSerializer()
    doctor = DoctorSerializer()
    appointment = PatientAppointmentSerializer()
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        read_only_fields = ['doctor', 'patient', 'create_at']

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
    appointment = PatientAppointmentSerializer()
    class Meta:
        model = Notification
        fields = ['message']
        read_only_fields = ['sent_at', 'status', 'error_message']

    def validate(self, data):
        request = self.context['request']
        profile  = request.user.profile # Автоматически получаем профиль

        appointment = data.get('appointment')
        if appointment and appointment.patient != profile:
            raise serializers.ValidationError('Нельзя отправить сообщение пациенту не с заявки')
        return data

    def validate_message_empty(self, value):
        if not value.strip():
            raise serializers.ValidatorError('Сообщение не может быть пустым')
        return value






