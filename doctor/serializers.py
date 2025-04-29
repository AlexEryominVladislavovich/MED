from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Doctor, Specialization, Schedule

class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = '__all__'

class DoctorSerializer(serializers.ModelSerializers):
    specialization = SpecializationSerializer()
    class Meta:
        model = Doctor
        fields = ['username', 'first_name', 'last_name', 'password', 'specialization',
                  'room_number', 'bio', 'phone_number']

class ScheduleSerializer(serializers.ModelSerializers):
    doctor = DoctorSerializer()
    class Meta:
        model = Schedule
        fields = ['day_of_weak', 'start_time', 'end_time', 'break_time']





