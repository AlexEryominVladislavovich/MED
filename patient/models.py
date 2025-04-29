from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models
from doctor.models import Doctor
from django.db.models import  UniqueConstraint
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator

kg_phone_validator = RegexValidator(
    regex=r'^\+996\(22\d|55\d|70\d|99\d)d{6}$',
    message='Номер телефона должен начинаться с +996 и содержать 9 цифр после кода страны(Пример: +996700123456)'
)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=35)
    phone_number = models.CharField(
        max_length=13,
        validators=[kg_phone_validator],
        unique=True
    )

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

    patient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')

    appointment_time = models.DateTimeField()
    rescheduled_from = models.DateTimeField(blank=True, null=True)

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

    # Запрещает пересичение новых заявок с занятым временем.
    class Meta:
        constraints = [
            UniqueConstraint(
                fields = ['doctor', 'appointment_time'],
                name = 'unique_doctor_appointment_if_scheduled'
        )
    ]

    def clean(self):
        super().clean()
        if not self.doctor.is_available(self.appointment_time):
            raise ValidationError ('Врач не доступен в это время.')
        if self.appointment_time <  timezone.now():
            raise ValidationError ('Вы пытаетесь записаться в прошлое.')
        if Appointment.objects.filter(
            doctor=self.doctor,
            appointment_time=self.appointment_time
        ).exclude(pk=self.pk).exists():
            raise ValidationError('На это время уже есть запись.')
        if Appointment.objects.filter(
            patient=self.patient,
            appointment_time=self.appointment_time
        ).exclude(doctor=self.doctor).exclude(pk=self.pk).exist():
            raise ValidationError('Вы уже записаны к другому врачу на это время.')
        if self.status == 'rescheduled' and not self.rescheduled_from:
            raise ValidationError('Не указанно время переноса.')

class Review(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    patient = models.ForeignKey(Profile, on_delete=models.DO_NOTHING)
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    comment = models.TextField()
    create_at = models.DateTimeField(auto_now_add=True)
    rating = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ]
    )
    def clean(self):
        super().clean()
        if self.appointment.patient != self.patient:
            raise ValidationError('Пациент не совпадает с указанным в приёме.')
        if self.appointment.status != 'visited':
            raise ValidationError('Оставить отзыв можно только после посщения')

class Notification(models.Model):

    STATUS_CHOICES = [
        ('sent', 'отправленно'),
        ('pending', 'в ожидании'),
        ('failed', 'не доставленно')
    ]

    MESSAGE_TYPES = (
        ('registration_success', 'Успешная регистрация'),
        ('appointment_reminder', 'Оповищение')
    )

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)

    sent_at = models.DateTimeField(auto_now_add=True)
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPES)
    message = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default = 'pending')
    error_message = models.CharField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.profile != self.appointment.patient:
            raise ValidationError('Нельзя отправлять уведомления не тому пользователю.')

    def __str__(self):
        return f'{self.profile.full_name}-{self.message_type}'


