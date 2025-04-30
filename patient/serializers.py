from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Appointment, Review, Notification, kg_phone_validator
from doctor.serializers import DoctorSerializer
from django.utils import timezone
import re

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

        # Удаляем всё кроме цифр
    def validate_phone_number(self, value):
        raw = ''.join(filter(str.isdigit, value))

        if len(raw) == 9:
            value = f'+996{raw}'
        elif len(raw) == 10 and raw.startswitch('0'):
            value = f'+996{raw[1:]}'
        elif len(raw) == 12 and raw.startswitch('996'):
            value = f'+{raw}'
        elif len(raw) == 13 and raw.startswitch('+996'):
            value = raw
        if Profile.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError('Этот номер уже используется.')
        else:
            raise serializers.ValidationError(
                'Введите коректный мобильный номер. Например 700123456'
            )
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

    def validate_appointment_time(selfself, value):
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

class PatientReviewSerializers(serializers.ModelSerializer):
    patient = ProfileSerializer()
    doctor = DoctorSerializer()
    appointment = PatientAppointmentSerializer()
    class Meta:
        model = Review
        fields = ['rating', 'comment']

class PatientNotificationSerializers(serializers.ModelSerializer):
    appointment = PatientAppointmentSerializer()
    class Meta:
        model = Notification
        fields = ['message', 'error_message']





