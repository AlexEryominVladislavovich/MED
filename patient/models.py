from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models
from doctor.models import Doctor
from django.db.models import  UniqueConstraint
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator, MinLengthValidator, MaxLengthValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import re
import uuid

kg_phone_validator = RegexValidator(
    regex=r'^\+996(22\d|55\d|70\d|99\d|77\d|54\d|51\d|57\d|56\d|50\d)\d{6}$',
    message='Номер телефона начинается с +996 и должен содержать 9 цифр после кода страны(Пример: +996 700123456)'
)

# Валидатор для кыргызских имен
name_validator = RegexValidator(
    regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s\-]+$',
    message='Имя может содержать только русские, английские буквы, символы Ң ң, Ө ө, Ү ү и дефис'
)

class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        null=True,  # Разрешаем пустое значение для гостевых пользователей
        blank=True  # Разрешаем пустое значение в формах для гостевых пользователей
    )
    full_name = models.CharField(
        max_length=35,
        validators=[
            MinLengthValidator(4, message='ФИО должно содержать минимум 4 символа'),
            name_validator
        ],
        verbose_name="ФИО"
    )
    phone_number = models.CharField(
        max_length=13,
        validators=[kg_phone_validator],
        verbose_name="Номер телефона"
    )
    is_guest = models.BooleanField(
        default=False,
        verbose_name="Гостевой пользователь"
    )
    username = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Имя пользователя",
        default='user'  # Значение по умолчанию для существующих записей
    )

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def clean(self):
        super().clean()
        # Нормализация имени
        if self.full_name:
            # Убираем множественные пробелы
            self.full_name = ' '.join(self.full_name.split())
            # Каждое слово с большой буквы
            self.full_name = ' '.join(word.capitalize() for word in self.full_name.split())

        # Нормализация телефона
        value = ''.join(filter(str.isdigit, self.phone_number))
        if len(value) == 9:
            normalized = f'+996{value}'
        elif len(value) == 10 and value.startswith('0'):
            normalized = f'+996{value[1:]}'
        elif len(value) == 12 and value.startswith('996'):
            normalized = f'+{value}'
        elif len(value) == 13 and value.startswith('+996'):
            normalized = value
        else:
            raise ValidationError({'phone_number': 'Введите корректный номер в формате +996XXXXXXXXX'})

        self.phone_number = normalized

    def save(self, *args, **kwargs):
        # Если имя пользователя не задано и пользователь существует, используем его username
        if not self.username and self.user:
            self.username = self.user.username
        # Если имя пользователя не задано и нет пользователя (гость), генерируем уникальное имя
        elif not self.username:
            self.username = f"guest_{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

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
        ('completed_with_treatment', 'Завершено с назначением лечения')
    ]

    VISIT_REASON_CHOICES = [
        ('examination', 'Обследование'),
        ('treatment', 'Лечение'),
    ]

    STATUS_OPEN = ['scheduled']
    STATUS_CLOSED = ['visited', 'no_show', 'cancelled_by_patient', 'cancelled_by_admin', 'rescheduled']

    patient = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='appointments',
        verbose_name="Пациент"
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name='appointments',
        verbose_name="Врач"
    )
    time_slot = models.OneToOneField(
        'doctor.TimeSlot',
        on_delete=models.PROTECT,
        verbose_name="Временной слот"
    )
    diagnosis = models.TextField(
        blank=True,
        null=True,
        verbose_name="Диагноз"
    )
    treatment_appointment = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='examination_appointment',
        verbose_name="Назначенное лечение"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    status = models.CharField(
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name="Статус"
    )
    description = models.TextField(
        blank=True,
        null=True,
        validators=[MaxLengthValidator(1000)],
        verbose_name="Описание"
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[
            MinValueValidator(0, message='Цена не может быть отрицательной'),
            MaxValueValidator(100000, message='Цена не может превышать 100 000')
        ],
        verbose_name="Цена",
        default=0
    )

    guest_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Имя гостя"
    )
    guest_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Телефон гостя"
    )
    guest_comment = models.TextField(
        blank=True,
        null=True,
        verbose_name="Комментарий гостя"
    )

    # Запрещает пересечение новых заявок с занятым временем
    class Meta:
        verbose_name = "Запись на приём"
        verbose_name_plural = "Записи на приём"
        constraints = [
            UniqueConstraint(
                fields=['doctor', 'time_slot'],
                name='unique_doctor_time_slot'
            )
        ]

    def is_open(self):
        return self.status in self.STATUS_OPEN

    def is_closed(self):
        return self.status in self.STATUS_CLOSED

    def __str__(self):
        return f"{self.patient.username} → {self.doctor} @ {self.time_slot.start_time.strftime('%Y-%m-%d %H:%M')} [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        if not self.doctor.is_available(self.time_slot.start_time):
            raise ValidationError('Врач не доступен в это время.')
        if self.time_slot.start_time < timezone.now():
            raise ValidationError('Вы пытаетесь записаться в прошлое.')
            
        # Проверка рабочих часов
        appointment_time = self.time_slot.start_time.time()
        if appointment_time.hour < 8 or appointment_time.hour >= 18:
            raise ValidationError('Время приёма должно быть с 8:00 до 19:00')
        
        # Проверка длительности
        if self.time_slot.start_time.minute % 5 != 0:
            raise ValidationError('Время приёма должно быть кратно 5 минутам')

        if Appointment.objects.filter(
            doctor=self.doctor,
            time_slot=self.time_slot
        ).exclude(pk=self.pk).exists():
            raise ValidationError('На это время уже есть запись.')
        if Appointment.objects.filter(
            patient=self.patient,
            time_slot=self.time_slot
        ).exclude(pk=self.pk).exists():
            raise ValidationError('Вы уже записаны к другому врачу на это время.')
        if self.status == 'rescheduled' and not self.treatment_appointment:
            raise ValidationError('Не указанно время переноса.')
        if self.treatment_appointment and self.status != 'rescheduled':
            raise ValidationError('Время переноса указанно, но статус не "перенесенно"')

@receiver(post_save, sender=Appointment)
def update_timeslot_on_appointment_save(sender, instance, created, **kwargs):
    """
    Обновляет статус доступности временного слота при создании/изменении записи
    """
    if instance.time_slot:
        # Если запись не отменена, помечаем слот как недоступный
        is_available = instance.status in ['cancelled_by_patient', 'cancelled_by_admin']
        instance.time_slot.is_available = is_available
        instance.time_slot.save()

@receiver(post_delete, sender=Appointment)
def update_timeslot_on_appointment_delete(sender, instance, **kwargs):
    """
    Обновляет статус доступности временного слота при удалении записи
    """
    if instance.time_slot:
        instance.time_slot.is_available = True
        instance.time_slot.save()

class Review(models.Model):
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        verbose_name="Врач"
    )
    patient = models.ForeignKey(
        Profile,
        on_delete=models.DO_NOTHING,
        verbose_name="Пациент"
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        verbose_name="Приём"
    )
    comment = models.TextField(
        validators=[
            MinLengthValidator(5, message='Минимальная длина отзыва - 10 символов'),
            MaxLengthValidator(500, message='Максимальная длина отзыва - 500 символов')
        ],
        verbose_name="Комментарий"
    )
    rating = models.IntegerField(
        validators=[
            MinValueValidator(1, message='Минимальная оценка - 1'),
            MaxValueValidator(5, message='Максимальная оценка - 5')
        ],
        verbose_name="Оценка"
    )
    create_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ['-create_at']

    def clean(self):
        super().clean()
        if self.appointment.patient != self.patient:
            raise ValidationError('Пациент не совпадает с указанным в приёме.')
        if self.appointment.status != 'visited':
            raise ValidationError('Оставить отзыв можно только после посщения')

    # Определяет доктора который привязан к заявке
    def save(self, *args, **kwargs):
        if not self.doctor and self.appointment:
            self.doctor = self.appointment.doctor
        super().save(*args, **kwargs)

class Notification(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Отправлено'),
        ('pending', 'В ожидании'),
        ('failed', 'Не доставлено')
    ]

    MESSAGE_TYPES = (
        ('appointment_created', 'Заявка создана'),
        ('appointment_reminder', 'Напоминание о записи'),
        ('registration_code', 'Код подтверждения'),
        ('registration_success', 'Успешная регистрация'),
        ('appointment_confirmation', 'Подтверждение записи'),
        ('appointment_cancellation', 'Отмена записи'),
        ('treatment_assigned', 'Назначено лечение')
    )

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Приём",
        null=True,
        blank=True  # Для уведомлений о регистрации запись на прием не нужна
    )
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Профиль",
        null=True,
        blank=True  # Для неавторизованных пользователей профиля нет
    )
    phone_number = models.CharField(
        max_length=13,
        validators=[kg_phone_validator],
        null=True,
        blank=True,
        verbose_name="Номер телефона"
    )
    email = models.EmailField(
        null=True,
        blank=True,
        verbose_name="Email"
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата отправки"
    )
    message_type = models.CharField(
        max_length=50,
        choices=MESSAGE_TYPES,
        verbose_name="Тип сообщения"
    )
    message = models.TextField(
        validators=[MinLengthValidator(5)],
        verbose_name="Сообщение"
    )
    status = models.CharField(
        max_length=20,
        default='pending',
        choices=STATUS_CHOICES,
        verbose_name="Статус"
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name="Сообщение об ошибке"
    )
    verification_code = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        verbose_name="Код подтверждения"
    )

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['profile', '-sent_at']),
            models.Index(fields=['appointment', 'message_type']),
            models.Index(fields=['phone_number', 'message_type']),
            models.Index(fields=['verification_code'])
        ]

    def __str__(self):
        recipient = self.profile if self.profile else self.phone_number
        return f"{self.get_message_type_display()} для {recipient} ({self.get_status_display()})"


