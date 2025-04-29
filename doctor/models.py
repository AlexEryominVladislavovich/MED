from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models

class Specialization(models.Model):
    name_specialization = models.CharField(max_length=30)
    description_specialization = models.TextField

    def __str__ (self):
        return f'{self.name_specialization}'

class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    room_number = models.CharField(max_length=5)
    bio = models.TextField()
    phone_number = models.CharField()
    specialization = models.ManyToManyField(Specialization)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
         return f'{self.first_name}-{self.last_name}'

class Schedule(models.Model):
    day_of_weak = models.DateTimeField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    break_time = models.DateTimeField()
    doctor = models.OneToOneField(Doctor,on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

