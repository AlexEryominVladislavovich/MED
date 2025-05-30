#from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, MinLengthValidator, MaxLengthValidator, MinValueValidator, MaxValueValidator, FileExtensionValidator
from datetime import timedelta, datetime
import re
import os

# Валидатор для кыргызских имен
name_validator = RegexValidator(
    regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s\-]+$',
    message='Имя может содержать только русские, английские буквы, символы Ң ң, Ө ө, Ү ү и дефис'
)

kg_phone_validator = RegexValidator(
    regex=r'^\+996(22\d|55\d|70\d|99\d|77\d|54\d|51\d|57\d|56\d|50\d)\d{6}$',
    message='Номер телефона начинается с +996 и должен содержать 9 цифр после кода страны(Пример: +996 700123456)'
)

def validate_image_size(value):
  
    max_size = 7 * 1024 * 1024  # 7MB в байтах
    if value.size > max_size:
        raise ValidationError('Размер изображения не должен превышать 7MB')

def doctor_photo_path(instance, filename):
    """
    Генерирует путь для сохранения фото врача.
    Формат: doctors/photos/<id>/<filename>
    """
    ext = filename.split('.')[-1]
    new_filename = f"{instance.user.username}.{ext}"
    return os.path.join('doctors', 'photos', str(instance.id), new_filename)

def doctor_gallery_photo_path(instance, filename):
    """
    Генерирует путь для сохранения фото в галерее врача.
    Формат: doctors/gallery/<doctor_id>/<filename>
    """
    ext = filename.split('.')[-1]
    new_filename = f"gallery_{instance.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
    return os.path.join('doctors', 'gallery', str(instance.doctor.id), new_filename)

class Specialization(models.Model):
    name_specialization = models.CharField(
        max_length=30,
        validators=[MinLengthValidator(5)],
        verbose_name="Название специализации"
    )
    description_specialization = models.TextField(
        verbose_name="Описание специализации"
    )

    class Meta:
        verbose_name = "Специализация"
        verbose_name_plural = "Специализации"

    def __str__ (self):
        return f'{self.name_specialization}'

class Doctor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    patronymic = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отчество"
    )
    photo = models.ImageField(
        upload_to=doctor_photo_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
            validate_image_size
        ],
        null=True,
        blank=True,
        verbose_name="Фотография"
    )
    room_number = models.CharField(
        max_length=5,
        validators=[
            RegexValidator(
                regex=r'^\d{3}[A-Za-z]?$',
                message='Формат кабинета: 3 цифры + опциональная буква (например: 101, 201А)'
            )
        ],
        verbose_name="Номер кабинета"
    )
    bio = models.TextField(
        validators=[MaxLengthValidator(1000, message='Биография не должна превышать 1000 символов')],
        verbose_name="Биография"
    )
    phone_number = models.CharField(
        max_length=13,
        validators=[kg_phone_validator],
        unique=True,
        verbose_name="Номер телефона"
    )
    specialization = models.ManyToManyField(
        'Specialization',
        verbose_name="Специализации"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Врач"
        verbose_name_plural = "Врачи"
        constraints = [
            models.UniqueConstraint(
                fields=['room_number'],
                condition=models.Q(is_active=True),
                name='unique_active_doctor_room'
            )
        ]

    def clean(self):
        super().clean()
        # Проверка и нормализация имени пользователя
        if self.user.first_name:
            # Проверяем first_name
            if not re.match(name_validator.regex, self.user.first_name):
                raise ValidationError({'user': name_validator.message})
            if len(self.user.first_name.strip()) < 2:
                raise ValidationError({'user': 'Имя должно содержать минимум 2 символа'})
            # Нормализуем first_name
            self.user.first_name = ' '.join(self.user.first_name.split()).title()

        if self.user.last_name:
            # Проверяем last_name
            if not re.match(name_validator.regex, self.user.last_name):
                raise ValidationError({'user': name_validator.message})
            if len(self.user.last_name.strip()) < 2:
                raise ValidationError({'user': 'Фамилия должна содержать минимум 2 символа'})
            # Нормализуем last_name
            self.user.last_name = ' '.join(self.user.last_name.split()).title()

        # Проверка на уникальность кабинета для активных врачей
        if self.is_active and Doctor.objects.exclude(pk=self.pk).filter(
            room_number=self.room_number,
            is_active=True
        ).exists():
            raise ValidationError({'room_number': 'Этот кабинет уже занят активным врачом'})

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
        
        if Doctor.objects.exclude(pk=self.pk).filter(phone_number=normalized).exists():
            raise ValidationError({'phone_number': 'Этот номер уже используется'})
        
        self.phone_number = normalized
        # Сохраняем изменения в user
        self.user.save()

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

    def get_available_slots(self, date):
        """Получить доступные слоты для записи на конкретную дату"""
        return self.time_slots.filter(
            date=date,
            is_available=True
        ).order_by('start_time')

class Schedule(models.Model):
    DAYS_OF_WEEK = [
        (1, 'Понедельник'),
        (2, 'Вторник'),
        (3, 'Среда'),
        (4, 'Четверг'),
        (5, 'Пятница'),
        (6, 'Суббота'),
        (7, 'Воскресенье'),
    ]
    
    day_of_week = models.IntegerField(
        choices=DAYS_OF_WEEK,
        verbose_name="День недели"
    )
    start_time = models.TimeField(
        verbose_name="Время начала работы"
    )
    end_time = models.TimeField(
        verbose_name="Время окончания работы"
    )
    break_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Начало перерыва"
    )
    break_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Конец перерыва"
    )
    doctor = models.ForeignKey(
        'Doctor',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name="Врач"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Расписание"
        verbose_name_plural = "Расписания"
        unique_together = ['doctor', 'day_of_week']

    def clean(self):
        if self.break_start and self.break_end:
            if self.break_start >= self.break_end:
                raise ValidationError('Время начала перерыва должно быть меньше времени окончания')
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValidationError('Перерыв должен быть в рамках рабочего времени')
        
        if self.start_time >= self.end_time:
            raise ValidationError('Время начала работы должно быть меньше времени окончания')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class ScheduleTemplate(models.Model):
    """Шаблон расписания врача"""
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,  # Защита от случайного удаления
        related_name='schedule_templates',
        verbose_name="Врач"
    )
    day_of_week = models.IntegerField(
        choices=Schedule.DAYS_OF_WEEK,
        verbose_name="День недели",
        validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    start_time = models.TimeField(verbose_name="Начало работы")
    end_time = models.TimeField(verbose_name="Конец работы")
    break_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Начало перерыва"
    )
    break_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Конец перерыва"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    
    class Meta:
        verbose_name = "Шаблон расписания"
        verbose_name_plural = "Шаблоны расписания"
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'day_of_week'],
                name='unique_doctor_day_template'
            )
        ]

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError('Время начала должно быть меньше времени окончания')
            
        if self.break_start and self.break_end:
            if self.break_start >= self.break_end:
                raise ValidationError('Время начала перерыва должно быть меньше времени окончания')
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValidationError('Перерыв должен быть в рамках рабочего времени')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class TimeSlot(models.Model):
    """Временной слот для приема"""
    SLOT_TYPES = [
        ('examination', 'Обследование'),
        ('treatment', 'Лечение'),
    ]
    
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name="Врач"
    )
    template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='time_slots',
        verbose_name="Шаблон"
    )
    date = models.DateField(verbose_name="Дата")
    start_time = models.TimeField(verbose_name="Время начала")
    duration = models.IntegerField(
        default=30,
        validators=[MinValueValidator(10), MaxValueValidator(120)],
        verbose_name="Длительность (минут)"
    )
    slot_type = models.CharField(
        max_length=20,
        choices=SLOT_TYPES,
        verbose_name="Тип слота"
    )
    is_available = models.BooleanField(default=True, verbose_name="Доступен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    
    class Meta:
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"
        ordering = ['date', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'date', 'start_time'],
                name='unique_doctor_timeslot'
            )
        ]

    def clean(self):
        # Проверка рабочих часов
        if self.template:
            if (self.start_time < self.template.start_time or 
                self.get_end_time() > self.template.end_time):
                raise ValidationError('Слот должен быть в рамках рабочего времени шаблона')

            # Проверка перерыва
            if self.template.break_start and self.template.break_end:
                slot_end = self.get_end_time()
                if (
                    (self.start_time >= self.template.break_start and self.start_time < self.template.break_end) or
                    (slot_end > self.template.break_start and slot_end <= self.template.break_end)
                ):
                    raise ValidationError('Слот не может пересекаться с перерывом')

        # Проверка пересечений с другими слотами
        end_time = self.get_end_time()
        overlapping = TimeSlot.objects.filter(
            doctor=self.doctor,
            date=self.date,
            start_time__lt=end_time,
            is_available=True
        ).exclude(pk=self.pk)
        
        for slot in overlapping:
            if slot.get_end_time() > self.start_time:
                raise ValidationError('Слот пересекается с существующими')

    def get_end_time(self):
        """Получить время окончания слота"""
        return (datetime.combine(datetime.min, self.start_time) + 
                timedelta(minutes=self.duration)).time()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.doctor} - {self.date} {self.start_time} ({self.get_slot_type_display()})"

class DoctorPhoto(models.Model):
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name="Врач"
    )
    image = models.ImageField(
        upload_to=doctor_gallery_photo_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
            validate_image_size
        ],
        verbose_name="Фотография"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок отображения"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления"
    )

    class Meta:
        verbose_name = "Фотография врача"
        verbose_name_plural = "Фотографии врача"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Фото {self.id} врача {self.doctor}"

