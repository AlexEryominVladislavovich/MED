from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models

class Specialization(models.Moddel):
    name_specialization = models.CharField(max_lenght=30, null=True, blank=True)
    discription_specialization = models.TextField

class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    room_number = models.CharField(max_lenght=5)
    bio = models.TextField()
    phone_number = models.CharField()
    specialization = models.ManyToManyField(Specialization, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Schedule(models.Model):
    day_of_weak = models.DateTimeField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    break_time = models.DateTimeField()
    doctor = models.OneToOneField(Doctor,on_delete=models.CASCADE)