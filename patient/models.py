from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models
from med.doctor.models import Doctor


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_lenght=50)
    phone_number = models.CharField()

    def __str__(self):
         return f'{self.full_name}'

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Запланирована'),
        ('visited', 'Посещена'),
        ('no_show', 'Неявка'),
        ('cancelled_by_patient', 'Отменена пациентом'),
        ('cancelled_by_admin', 'Отменена админом'),
        ('rescheduled', 'Перенос'),
    ]

    VISIT_REASON_CHOICES = [
        ('diagnostics', 'Обследование'),
        ('treatment', 'Лечение'),
    ]

    STATUS_OPEN = ['scheduled']
    STATUS_CLOSED = ['visited', 'no_show', 'cancelled_by_patient', 'cancelled_by_admin', 'rescheduled']

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='appointments')

    appointment_time = models.DateTimeField(null=True, blank=True)
    rescheduled_from = models.DateTimeField(null=True, blank=True)

    visit_reason = models.CharField(choices=VISIT_REASON_CHOICES, default='diagnostics')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    status = models.CharField(choices=STATUS_CHOICES, default='scheduled')
    description = models.TextField(blank=True, null=True)

    def is_open(self):
        return self.status in self.STATUS_OPEN

    def is_closed(self):
        return self.status in self.STATUS_CLOSED

    def __str__(self):
        return f"{self.patient.username} → {self.doctor} @ {self.appointment_time.strftime('%Y-%m-%d %H:%M')} [{self.get_status_display()}]"

    class Meta:
        ordering = ['-appointment_time']
        unique_together = ('doctor', 'appointment_time')