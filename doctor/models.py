#from xml.etree.ElementInclude import default_loader
from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import (RegexValidator, MinLengthValidator, MaxLengthValidator, 
    MinValueValidator, MaxValueValidator, FileExtensionValidator)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import os
import logging
import re
from PIL import Image
import io
from django.core.files.base import ContentFile
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
    limit = 5 * 1024 * 1024
    if value.size > limit:
        raise ValidationError('Размер файла не должен превышать 5MB')

def optimize_image(image, max_size):
    """
    Оптимизирует изображение, сохраняя соотношение сторон и качество
    """
    img = Image.open(image)
    
    # Конвертируем в RGB если изображение в RGBA
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    
    # Получаем текущие размеры
    width, height = img.size
    
    # Вычисляем новые размеры, сохраняя пропорции
    if width > height:
        if width > max_size:
            ratio = max_size / width
            new_width = max_size
            new_height = int(height * ratio)
    else:
        if height > max_size:
            ratio = max_size / height
            new_height = max_size
            new_width = int(width * ratio)
    
    # Изменяем размер с высоким качеством
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Сохраняем с оптимальным качеством
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    output.seek(0)
    
    return output

def doctor_photo_path(instance, filename):
    """
    Генерирует путь для сохранения фото врача.
    Формат: doctors/photos/<id>/<filename>
    """
    ext = filename.split('.')[-1].lower()
    new_filename = f"{instance.user.username}.{ext}"
    return os.path.join('doctors', 'photos', str(instance.id), new_filename)

def doctor_gallery_photo_path(instance, filename):
    """
    Генерирует путь для сохранения фото в галерее врача.
    Формат: doctors/gallery/<doctor_id>/<filename>
    """
    ext = filename.split('.')[-1].lower()
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
        settings.AUTH_USER_MODEL,
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
        validators=[MaxLengthValidator(200, message='Биография не должна превышать 1000 символов')],
        verbose_name="Биография"
    )
    full_bio = models.TextField(
        validators=[MaxLengthValidator(1000, message='Полная биография не должна превышать 1000 символов')],
        verbose_name="Полная биография",
        blank=True,
        null=True
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

    def save(self, *args, **kwargs):
        # Если это новый объект (еще не сохранен в БД)
        if self.pk is None:
            super().save(*args, **kwargs)
        
        # Если есть новое фото
        if self.photo and hasattr(self.photo, 'file'):
            # Оптимизируем оригинальное изображение
            optimized = optimize_image(self.photo, 1200)
            self.photo.save(
                self.photo.name,
                ContentFile(optimized.getvalue()),
                save=False
            )
        
        super().save(*args, **kwargs)

class Treatment(models.Model):
    """История болезни"""
    patient = models.ForeignKey('patient.Profile', on_delete=models.DO_NOTHING, related_name='treatments')
    doctor = models.ForeignKey('Doctor', on_delete=models.DO_NOTHING, related_name='treatments')
    initial_appointment = models.ForeignKey('patient.Appointment', on_delete=models.DO_NOTHING)
    status = models.CharField(
        max_length=30,
        choices=[
            ('active', 'Активно'),
            ('completed', 'Завершено'),
            ('canceled', 'Отменено'),
        ],
        default='active',
        verbose_name="Статус",
        help_text=_('Выберите статус лечения')
    )
    diagnosis = models.CharField(
        max_length=50,
        validators=[MinLengthValidator(5)],
        verbose_name="Диагноз",
        help_text=_('Введите диагноз болезни (5-50 символов)')
    )
    treatment_plan = models.TextField(
        max_length=2000,
        validators=[
            MinLengthValidator(10, message='План лечения должен содержать минимум 10 символов'),
            RegexValidator(
                regex=r'^[а-яА-ЯёЁa-zA-ZҢңӨөҮү\s.,!?()-]+$',
                message='План лечения может содержать только русские, английские буквы, символы Ң ң, Ө ө, Ү ү, точки, запятые, восклицательные и вопросительные знаки, скобки и дефис'
            )
        ],
        verbose_name="План лечения",
        help_text=_('Введите план лечения (10-2000 символов)')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.initial_appointment and self.initial_appointment.status != 'visited':
            raise ValidationError({'initial_appointment': _('Начальная запись должна быть посещена')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('История болезни')
        verbose_name_plural = _('Истории болезни')
        ordering = ['-created_at']

class TreatmentSession(models.Model):
    treatment = models.ForeignKey(Treatment, on_delete=models.CASCADE, related_name='sessions')
    appointment = models.ForeignKey('patient.Appointment', on_delete=models.CASCADE)
    notes = models.TextField(
        max_length=4000,
        validators=[
            RegexValidator(
                regex=r'^[а-яА-ЯёЁa-zA-Z0-9\s.,!?()-]+$',
                message=_('Заметки могут содержать только буквы, цифры и знаки препинания')
            )
        ],
        help_text=_('Заметки о сессии могут содержать максимум 4000 символов')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Сессия лечения')
        verbose_name_plural = _('Сессии лечения')
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        if self.appointment and self.appointment.status != 'visited':
            raise ValidationError({'appointment': _('Запись должна быть завершена')})
        if self.treatment and self.treatment.status != 'active':
            raise ValidationError({'treatment': _('Нельзя добавить сессию к неактивной истории болезни')})
        if self.appointment and self.appointment.time_slot.start_time > timezone.now():
            raise ValidationError({'appointment': _('Нельзя создать сессию для будущей записи')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class TreatmentPhoto(models.Model):
    session = models.ForeignKey(TreatmentSession, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(
        upload_to='treatment_photos/%Y%m%d/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png'],
                message='Разрешены только форматы: jpg, jpeg, png'
            )
        ],
        help_text=_('Максимальный размер фотографии 10мб, форматы: jpg, jpeg, png')
    )
    description = models.TextField(max_length=2000, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.session and not self.pk:
            photo_count = TreatmentPhoto.objects.filter(session=self.session).count()
            if photo_count >= 1000:
                raise ValidationError({'session': _('Максимальное количество фотографий на сессию 1000')})
        if self.image:
            ext = os.path.splitext(self.image.name)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png']:
                raise ValidationError({'image': _('Разрешены только форматы jpg, jpeg, png')})
            if self.image.size > 10 * 1024 * 1024:
                raise ValidationError({'image': _('Максимальный размер 10 мб')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

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
    
    doctor = models.ForeignKey(
        'Doctor',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name="Врач"
    )
    template = models.ForeignKey(
        'ScheduleTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules',
        verbose_name="Шаблон расписания"
    )
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

class ScheduleTemplateManager(models.Manager):
    def get_templates_requiring_generation(self):
        """Получает шаблоны, требующие генерации слотов"""
        today = timezone.now().date()
        return self.filter(
            models.Q(last_slot_generation__isnull=True) |  # Никогда не генерировались
            models.Q(last_slot_generation__lt=today),      # Последняя генерация была раньше
            is_active=True
        )

    def generate_slots_for_template(self, template):
        """Генерирует слоты для конкретного шаблона"""
        today = timezone.now().date()
        end_date = today + timedelta(days=template.generation_period_days)
        
        # Создаем слоты
        template.create_time_slots(today, end_date)
        
        # Обновляем дату последней генерации
        template.last_slot_generation = today
        template.save(update_fields=['last_slot_generation'])

class ScheduleTemplate(models.Model):
    """Шаблон расписания врача"""
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name='schedule_templates',
        verbose_name="Врач"
    )
    day_of_week = models.IntegerField(
        choices=Schedule.DAYS_OF_WEEK,
        verbose_name="День недели"
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
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    last_slot_generation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Последняя генерация слотов"
    )
    generation_period_days = models.IntegerField(
        default=31,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        verbose_name="Период генерации слотов (дней)"
    )

    objects = ScheduleTemplateManager()

    class Meta:
        verbose_name = "Шаблон расписания"
        verbose_name_plural = "Шаблоны расписания"
        ordering = ['doctor', 'day_of_week']

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError('Время начала должно быть меньше времени окончания')
            
        if self.break_start and self.break_end:
            if self.break_start >= self.break_end:
                raise ValidationError('Время начала перерыва должно быть меньше времени окончания')
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValidationError('Перерыв должен быть в рамках рабочего времени')

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        
        # После сохранения шаблона создаем или обновляем расписание
        schedule, created = Schedule.objects.get_or_create(
            doctor=self.doctor,
            day_of_week=self.day_of_week,
            defaults={
                'start_time': self.start_time,
                'end_time': self.end_time,
                'break_start': self.break_start,
                'break_end': self.break_end,
                'is_active': self.is_active
            }
        )
        
        if not created:
            schedule.start_time = self.start_time
            schedule.end_time = self.end_time
            schedule.break_start = self.break_start
            schedule.break_end = self.break_end
            schedule.is_active = self.is_active
            schedule.save()

    def create_time_slots(self, start_date, end_date=None):
        """
        Создает временные слоты на основе шаблона
        """
        if not self.doctor_id:
            logger.error('Невозможно создать слоты: не указан врач')
            raise ValidationError('Невозможно создать слоты: не указан врач')
            
        if not end_date:
            end_date = start_date + timedelta(days=30)  # По умолчанию на месяц вперед
        
        logger.info(f"Начало генерации слотов для врача {self.doctor} с {start_date} по {end_date}")
        
        current_date = start_date
        slots_created = 0  # Счетчик созданных слотов
        
        # Получаем все временные слоты шаблона
        template_slots = self.template_slots.all()
        if not template_slots.exists():
            logger.warning(f"Шаблон {self.id} не имеет определенных временных слотов")
            return 0
            
        while current_date <= end_date:
            # Создаем слоты только для соответствующего дня недели
            if current_date.isoweekday() == self.day_of_week:
                logger.info(f"Генерация слотов для даты {current_date}")
                
                for template_slot in template_slots:
                    # Проверяем, не попадает ли слот на перерыв
                    if not self._is_break_time(datetime.combine(current_date, template_slot.start_time), current_date):
                        try:
                            # Проверяем существование слота
                            existing_slot = TimeSlot.objects.with_deleted().filter(
                                doctor=self.doctor,
                                date=current_date,
                                start_time=template_slot.start_time,
                                slot_type=template_slot.slot_type
                            ).first()
                            
                            if existing_slot:
                                if existing_slot.is_deleted:
                                    # Восстанавливаем удаленный слот
                                    existing_slot.is_deleted = False
                                    existing_slot.is_available = True
                                    existing_slot.save()
                                    slots_created += 1
                                    logger.info(f"Восстановлен слот: {current_date} {template_slot.start_time}")
                            else:
                                # Создаем новый слот
                                TimeSlot.objects.create(
                                    doctor=self.doctor,
                                    date=current_date,
                                    start_time=template_slot.start_time,
                                    duration=template_slot.duration,
                                    slot_type=template_slot.slot_type,
                                    template=self,
                                    is_available=True
                                )
                                slots_created += 1
                                logger.info(f"Создан слот: {current_date} {template_slot.start_time} ({template_slot.slot_type})")
                        except Exception as e:
                            logger.error(f"Ошибка создания слота: {e}")
            
            current_date += timedelta(days=1)
        
        logger.info(f"Завершена генерация слотов. Создано {slots_created} слотов")
        return slots_created

    def _is_break_time(self, time, date):
        """Проверяет, попадает ли время на перерыв"""
        if not (self.break_start and self.break_end):
            return False
            
        break_start = datetime.combine(date, self.break_start)
        break_end = datetime.combine(date, self.break_end)
        
        return break_start <= time < break_end

    def __str__(self):
        try:
            days_dict = dict(Schedule.DAYS_OF_WEEK)
            day_name = days_dict.get(self.day_of_week, 'Неизвестный день')
            if self.doctor_id:
                return f"Шаблон {self.doctor} ({day_name})"
            return f"Новый шаблон ({day_name})"
        except Exception:
            return "Шаблон расписания"

class TemplateTimeSlot(models.Model):
    """Временной слот шаблона расписания"""
    SLOT_TYPES = [
        ('consultation', 'Консультация'),
        ('treatment', 'Лечение'),
    ]

    template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.CASCADE,
        related_name='template_slots',
        verbose_name="Шаблон"
    )
    start_time = models.TimeField(verbose_name="Время начала")
    duration = models.IntegerField(
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(55)],
        verbose_name="Длительность (минут)"
    )
    slot_type = models.CharField(
        max_length=20,
        choices=SLOT_TYPES,
        verbose_name="Тип слота"
    )

    class Meta:
        verbose_name = "Временной слот шаблона"
        verbose_name_plural = "Временные слоты шаблона"
        ordering = ['start_time']
        unique_together = ['template', 'start_time']

    def clean(self):
        super().clean()
        if self.start_time:
            # Проверяем корректность длительности для типа слота
            if self.slot_type == 'consultation' and self.duration != 15:
                raise ValidationError('Длительность консультации должна быть 15 минут')
            elif self.slot_type == 'treatment' and self.duration != 40:
                raise ValidationError('Длительность лечения должна быть 40 минут')
            
            # Проверяем корректность времени начала для типа слота
            if self.slot_type == 'consultation' and self.start_time.minute != 40:
                raise ValidationError('Консультация должна начинаться в XX:40')
            elif self.slot_type == 'treatment' and self.start_time.minute != 0:
                raise ValidationError('Лечение должно начинаться в XX:00')
            
            # Проверки, которые требуют сохраненного шаблона, выполняем только если шаблон существует
            if hasattr(self, 'template') and self.template and self.template.pk:
                # Проверяем, что время слота входит в рабочее время шаблона
                if self.start_time < self.template.start_time or self.start_time >= self.template.end_time:
                    raise ValidationError('Время слота должно быть в пределах рабочего времени')
                
                # Проверяем, что слот не попадает на перерыв
                if self.template.break_start and self.template.break_end:
                    if self.start_time >= self.template.break_start and self.start_time < self.template.break_end:
                        raise ValidationError('Слот не может начинаться во время перерыва')
                
                # Проверяем, что слот заканчивается до конца рабочего дня
                end_time = self.get_end_time()
                if end_time and end_time > self.template.end_time:
                    raise ValidationError('Слот должен заканчиваться до конца рабочего дня')
                
                # Проверяем пересечение с другими слотами
                overlapping_slots = TemplateTimeSlot.objects.filter(
                    template_id=self.template.pk
                ).exclude(pk=self.pk or None)
                
                for slot in overlapping_slots:
                    slot_end = slot.get_end_time()
                    if slot_end and self.start_time < slot_end and slot.start_time < end_time:
                        raise ValidationError('Слот пересекается с существующим слотом')

    def get_end_time(self):
        """Получить время окончания слота"""
        if self.start_time and self.duration:
            return (datetime.combine(datetime.today(), self.start_time) + 
                   timedelta(minutes=self.duration)).time()
        return None

    def __str__(self):
        return f"{self.template.doctor} - {self.start_time.strftime('%H:%M')} ({self.get_slot_type_display()})"

class TimeSlotManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()

    def only_deleted(self):
        return super().get_queryset().filter(is_deleted=True)

class TimeSlot(models.Model):
    """Временной слот для приема"""
    SLOT_TYPES = [
        ('consultation', 'Консультация'),
        ('treatment', 'Лечение'),
    ]

    SLOT_DURATIONS = {
        'consultation': 15,
        'treatment': 40,
    }
    
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
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(55)],
        verbose_name="Длительность (минут)"
    )
    slot_type = models.CharField(
        max_length=20,
        choices=SLOT_TYPES,
        verbose_name="Тип слота"
    )
    is_available = models.BooleanField(default=True, verbose_name="Доступен")
    is_deleted = models.BooleanField(default=False, verbose_name="Удален")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    
    objects = TimeSlotManager()

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
        # Право доступа врачу изменять слоты
        permissions = [
            ("can_manage_slots", "Can manage time slots"),
        ]
        # Добавляем default_manager_name для автоматической фильтрации удаленных слотов
        default_manager_name = 'objects'

    def clean(self):
        super().clean()
        
        # Проверка типа слота и длительности
        if self.slot_type not in self.SLOT_DURATIONS:
            raise ValidationError('Неверный тип слота')
        
        self.duration = self.SLOT_DURATIONS[self.slot_type]


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

        # Проверка рабочих часов только если есть шаблон
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

    def save(self, *args, **kwargs):
        # Если это новый объект (еще не сохранен в БД)
        if self.pk is None:
            super().save(*args, **kwargs)
        
        # Если есть новое изображение
        if self.image and hasattr(self.image, 'file'):
            # Оптимизируем оригинальное изображение
            optimized = optimize_image(self.image, 1200)
            self.image.save(
                self.image.name,
                ContentFile(optimized.getvalue()),
                save=False
            )
        
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Фотография врача"
        verbose_name_plural = "Фотографии врача"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Фото {self.id} врача {self.doctor}"

