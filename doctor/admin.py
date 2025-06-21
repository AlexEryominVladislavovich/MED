from django.contrib import admin
from .models import Doctor, Schedule, Specialization, DoctorPhoto, TimeSlot, ScheduleTemplate, TemplateTimeSlot, Treatment, TreatmentSession, TreatmentPhoto
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.forms import ModelForm, MultipleChoiceField, CheckboxSelectMultiple
from django.utils import timezone
import logging
from .forms import ScheduleTemplateForm
from patient.models import Appointment

logger = logging.getLogger(__name__)

@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ['name_specialization', 'name_specialization_ky', 'description_specialization', 'description_specialization_ky']
    search_fields = ['name_specialization', 'name_specialization_ky']
    fields = [
        'name_specialization', 'name_specialization_ky', 
        'description_specialization', 'description_specialization_ky'
    ]

class DoctorPhotoInline(admin.TabularInline):
    model = DoctorPhoto
    extra = 1
    fields = ['image', 'order']

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'get_specializations', 'room_number', 'phone_number', 'is_active']
    list_filter = ['is_active', 'specialization']
    search_fields = ['user__first_name', 'user__last_name', 'patronymic', 'room_number']
    filter_horizontal = ['specialization']
    autocomplete_fields = ['user']
    fields = [
        'user', 'patronymic', 'room_number', 'phone_number', 
        'bio', 'bio_ky', 'full_bio', 'full_bio_ky', 'photo', 
        'specialization', 'is_active'
    ]
    inlines = [DoctorPhotoInline]

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
    get_full_name.short_description = "ФИО"

    def get_specializations(self, obj):
        return ", ".join([spec.name_specialization for spec in obj.specialization.all()])
    get_specializations.short_description = 'Специализации'

class GenerateTimeSlotsForm(forms.Form):
    start_date = forms.DateField(label='Дата начала', widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(label='Дата окончания', widget=forms.DateInput(attrs={'type': 'date'}))
    slot_type = forms.ChoiceField(
        label='Тип слота',
        choices=[('consultation', 'Консультация'), ('treatment', 'Лечение')]
    )

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'get_day_name', 'start_time', 'end_time', 'break_start', 'break_end']
    list_filter = ['day_of_week', 'doctor']
    search_fields = ['doctor__user__first_name', 'doctor__user__last_name']
    ordering = ['doctor', 'day_of_week']
    
    fieldsets = (
        (None, {
            'fields': ('doctor', 'day_of_week')
        }),
        ('Рабочее время', {
            'fields': ('start_time', 'end_time')
        }),
        ('Перерыв', {
            'fields': ('break_start', 'break_end'),
            'classes': ('collapse',)
        })
    )

    def get_day_name(self, obj):
        return obj.get_day_of_week_display()
    get_day_name.short_description = "День недели"

class AppointmentInline(admin.TabularInline):
    model = Appointment
    extra = 0
    fields = ('get_patient_display', 'status', 'price', 'description', 'guest_comment')
    readonly_fields = ('get_patient_display', 'status', 'price', 'description', 'guest_comment')
    can_delete = False
    show_change_link = True

    def get_patient_display(self, obj):
        if obj.patient and not obj.patient.is_guest:
            return f"{obj.patient.full_name} ({obj.patient.phone_number})"
        elif obj.guest_name or obj.guest_phone:
            return f"Гость: {obj.guest_name or ''} ({obj.guest_phone or ''})"
        return "-"
    get_patient_display.short_description = 'Пациент/Гость'

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'date', 'start_time', 'slot_type', 'is_available', 'is_deleted', 'created_at']
    list_filter = ['doctor', 'date', 'slot_type', 'is_available', 'is_deleted']
    search_fields = ['doctor__user__last_name', 'doctor__user__first_name']
    ordering = ['date', 'start_time']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['soft_delete_slots', 'restore_slots', 'generate_time_slots']
    inlines = [AppointmentInline]

    fieldsets = (
        (None, {
            'fields': ('doctor', 'date', 'start_time', 'slot_type')
        }),
        ('Статус', {
            'fields': ('is_available', 'is_deleted')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        # Показываем все слоты, включая удаленные
        return TimeSlot.objects.with_deleted()

    def soft_delete_slots(self, request, queryset):
        """Мягкое удаление выбранных слотов"""
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'Успешно удалено {updated} слотов.')
    soft_delete_slots.short_description = "Удалить выбранные слоты (мягкое удаление)"

    def restore_slots(self, request, queryset):
        """Восстановление удаленных слотов"""
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f'Успешно восстановлено {updated} слотов.')
    restore_slots.short_description = "Восстановить выбранные слоты"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    def generate_time_slots(self, request, queryset):
        if 'apply' in request.POST:
            form = GenerateTimeSlotsForm(request.POST)
            if form.is_valid():
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                slot_type = form.cleaned_data['slot_type']
                created_count = 0
                restored_count = 0
                skipped_count = 0
                
                # Проверяем корректность дат
                if start_date > end_date:
                    self.message_user(
                        request,
                        'Дата начала должна быть меньше или равна дате окончания',
                        level='error'
                    )
                    return HttpResponseRedirect(request.get_full_path())
                
                if start_date < timezone.now().date():
                    self.message_user(
                        request,
                        'Дата начала не может быть в прошлом',
                        level='error'
                    )
                    return HttpResponseRedirect(request.get_full_path())
                
                for doctor in queryset:
                    current_date = start_date
                    while current_date <= end_date:
                        # Получаем шаблон расписания для текущего дня недели
                        template = ScheduleTemplate.objects.filter(
                            doctor=doctor,
                            day_of_week=current_date.isoweekday(),
                            is_active=True
                        ).first()
                        
                        if template:
                            # Определяем время начала и конца
                            if slot_type == 'consultation':
                                # Для консультаций (XX:40 каждого часа)
                                current_time = datetime.combine(current_date, template.start_time)
                                current_time = current_time.replace(minute=40)
                                end_time = datetime.combine(current_date, template.end_time)
                                
                                while current_time + timedelta(minutes=15) <= end_time:
                                    # Проверяем, не попадает ли слот на перерыв
                                    slot_end_time = current_time + timedelta(minutes=15)
                                    is_break_time = False
                                    
                                    if template.break_start and template.break_end:
                                        break_start = datetime.combine(current_date, template.break_start)
                                        break_end = datetime.combine(current_date, template.break_end)
                                        
                                        if (current_time >= break_start and current_time < break_end) or \
                                           (slot_end_time > break_start and slot_end_time <= break_end):
                                            is_break_time = True
                                    
                                    if not is_break_time:
                                        # Проверяем существование слота с учетом удаленных
                                        existing_slot = TimeSlot.objects.with_deleted().filter(
                                            doctor=doctor,
                                            date=current_date,
                                            start_time=current_time.time()
                                        ).first()
                                        
                                        if existing_slot:
                                            if existing_slot.is_deleted:
                                                # Восстанавливаем удаленный слот
                                                existing_slot.is_deleted = False
                                                existing_slot.is_available = True
                                                existing_slot.save()
                                                restored_count += 1
                                            else:
                                                skipped_count += 1
                                        else:
                                            # Создаем новый слот
                                            TimeSlot.objects.create(
                                                doctor=doctor,
                                                date=current_date,
                                                start_time=current_time.time(),
                                                slot_type='consultation',
                                                is_available=True,
                                                is_deleted=False,
                                                template=template
                                            )
                                            created_count += 1
                                    
                                    current_time += timedelta(hours=1)
                            
                            elif slot_type == 'treatment':
                                # Для лечения (XX:00 каждого часа)
                                current_time = datetime.combine(current_date, template.start_time)
                                current_time = current_time.replace(minute=0)
                                end_time = datetime.combine(current_date, template.end_time)
                                
                                while current_time + timedelta(minutes=40) <= end_time:
                                    # Проверяем, не попадает ли слот на перерыв
                                    slot_end_time = current_time + timedelta(minutes=40)
                                    is_break_time = False
                                    
                                    if template.break_start and template.break_end:
                                        break_start = datetime.combine(current_date, template.break_start)
                                        break_end = datetime.combine(current_date, template.break_end)
                                        
                                        if (current_time >= break_start and current_time < break_end) or \
                                           (slot_end_time > break_start and slot_end_time <= break_end):
                                            is_break_time = True
                                    
                                    if not is_break_time:
                                        # Проверяем существование слота с учетом удаленных
                                        existing_slot = TimeSlot.objects.with_deleted().filter(
                                            doctor=doctor,
                                            date=current_date,
                                            start_time=current_time.time()
                                        ).first()
                                        
                                        if existing_slot:
                                            if existing_slot.is_deleted:
                                                # Восстанавливаем удаленный слот
                                                existing_slot.is_deleted = False
                                                existing_slot.is_available = True
                                                existing_slot.save()
                                                restored_count += 1
                                            else:
                                                skipped_count += 1
                                        else:
                                            # Создаем новый слот
                                            TimeSlot.objects.create(
                                                doctor=doctor,
                                                date=current_date,
                                                start_time=current_time.time(),
                                                slot_type='treatment',
                                                is_available=True,
                                                is_deleted=False,
                                                template=template
                                            )
                                            created_count += 1
                                    
                                    current_time += timedelta(hours=1)
                        
                        current_date += timedelta(days=1)
                
                self.message_user(
                    request,
                    f'Создано {created_count} новых слотов, восстановлено {restored_count} удаленных слотов. '
                    f'Пропущено {skipped_count} существующих слотов.',
                    level='success'
                )
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = GenerateTimeSlotsForm(initial={
                'start_date': timezone.now().date(),
                'end_date': timezone.now().date() + timedelta(days=30)
            })

        return render(
            request,
            'admin/generate_time_slots.html',
            context={
                'form': form,
                'title': 'Генерация временных слотов',
                'queryset': queryset
            }
        )
    generate_time_slots.short_description = "Сгенерировать временные слоты"

class TemplateTimeSlotInline(admin.TabularInline):
    model = TemplateTimeSlot
    extra = 1
    fields = ['start_time', 'duration', 'slot_type']
    template = 'admin/doctor/template_timeslot_inline.html'

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form
        
        # Добавляем подсказки для полей
        form.base_fields['start_time'].help_text = 'Консультации: XX:40, Лечение: XX:00'
        form.base_fields['duration'].help_text = 'Консультации: 15 минут, Лечение: 40 минут'
        form.base_fields['slot_type'].help_text = 'Выберите тип слота'
        
        # Отключаем валидацию для нового шаблона
        if obj is None:  # Если создаем новый шаблон
            form.clean = lambda self: self.cleaned_data
        
        return formset

class ScheduleTemplateAdminForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplate
        fields = '__all__'

@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    form = ScheduleTemplateAdminForm
    list_display = ('get_doctor_name', 'get_day_name', 'start_time', 'end_time', 'is_active', 'get_slots_count')
    list_filter = ('is_active', 'doctor')
    search_fields = ('doctor__user__first_name', 'doctor__user__last_name')
    inlines = [TemplateTimeSlotInline]
    
    def get_slots_count(self, obj):
        return obj.template_slots.count()
    get_slots_count.short_description = 'Количество слотов'
    
    def get_doctor_name(self, obj):
        try:
            if obj and obj.doctor:
                return str(obj.doctor)
            return "Не указан"
        except Exception:
            return "Не указан"
    get_doctor_name.short_description = 'Врач'
    
    def get_day_name(self, obj):
        try:
            days_dict = dict(Schedule.DAYS_OF_WEEK)
            return days_dict.get(obj.day_of_week, 'Не указан')
        except Exception:
            return 'Не указан'
    get_day_name.short_description = 'День недели'

    fieldsets = (
        (None, {
            'fields': ('doctor',),
            'description': 'Выберите врача для создания шаблона расписания'
        }),
        ('Рабочее время', {
            'fields': (('day_of_week', 'start_time', 'end_time'),),
            'description': 'Укажите день недели и время работы'
        }),
        ('Перерыв', {
            'classes': ('collapse',),
            'fields': (('break_start', 'break_end'),),
            'description': 'При необходимости укажите время перерыва'
        }),
        ('Настройки', {
            'fields': ('is_active', 'generation_period_days'),
            'description': 'Дополнительные настройки шаблона'
        })
    )

    class Media:
        css = {
            'all': ('admin/doctor/css/schedule_template.css',)
        }
        js = ('admin/doctor/js/schedule_template.js',)

    def save_formset(self, request, form, formset, change):
        """
        Сохранение inline-формсетов с дополнительной валидацией
        """
        if formset.model == TemplateTimeSlot:
            instances = formset.save(commit=False)
            for instance in instances:
                instance.template = form.instance
                instance.save()
            formset.save_m2m()
        else:
            formset.save()

    def save_model(self, request, obj, form, change):
        """
        Сохранение модели с дополнительной логикой генерации слотов
        """
        try:
            # Проверяем уникальность до сохранения
            if obj.is_active:
                conflicts = ScheduleTemplate.objects.filter(
                    doctor_id=form.cleaned_data['doctor'].id,
                    day_of_week=form.cleaned_data['day_of_week'],
                    is_active=True
                )
                if obj.pk:
                    conflicts = conflicts.exclude(pk=obj.pk)
                
                if conflicts.exists():
                    raise ValidationError('У врача уже есть активный шаблон для этого дня недели')

            if not obj.doctor_id and 'doctor' in form.cleaned_data:
                obj.doctor = form.cleaned_data['doctor']

            # Сначала сохраняем шаблон
            super().save_model(request, obj, form, change)

            if obj.is_active:  # Генерируем слоты только для активных шаблонов
                if not obj.template_slots.exists():
                    self.message_user(
                        request,
                        'Внимание: шаблон не содержит временных слотов. Добавьте слоты для корректной работы.',
                        level='warning'
                    )
                else:
                    # Создаем временные слоты на месяц вперед
                    start_date = timezone.now().date()
                    end_date = start_date + timedelta(days=obj.generation_period_days or 30)
                    
                    logger.info(f"Запуск генерации слотов для шаблона {obj}")
                    slots_created = obj.create_time_slots(start_date, end_date)
                    
                    if slots_created > 0:
                        self.message_user(
                            request,
                            f'Шаблон успешно сохранен. Сгенерировано {slots_created} временных слотов.',
                            level='success'
                        )
                    else:
                        self.message_user(
                            request,
                            'Шаблон сохранен, но не удалось сгенерировать временные слоты. Проверьте настройки шаблона.',
                            level='warning'
                        )
            else:
                self.message_user(
                    request,
                    'Шаблон сохранен. Слоты не генерируются для неактивных шаблонов.',
                    level='info'
                )
                
        except ValidationError as e:
            self.message_user(
                request,
                f'Ошибка валидации: {"; ".join(e.messages)}',
                level='error'
            )
            raise  # Перебрасываем исключение, чтобы форма не сохранилась
        except Exception as e:
            logger.error(f"Ошибка при сохранении шаблона: {e}")
            self.message_user(
                request,
                f'Произошла ошибка при сохранении шаблона: {str(e)}',
                level='error'
            )
            raise  # Перебрасываем исключение, чтобы форма не сохранилась

    def response_add(self, request, obj, post_url_continue=None):
        """
        После создания шаблона перенаправляем на страницу со списком шаблонов
        """
        if '_addanother' not in request.POST:
            return HttpResponseRedirect(
                reverse('admin:doctor_scheduletemplate_changelist')
            )
        return super().response_add(request, obj, post_url_continue)

    def get_form(self, request, obj=None, **kwargs):
        """
        Настройка формы для создания/редактирования шаблона
        """
        form = super().get_form(request, obj, **kwargs)
        if not obj:  # Если создаем новый шаблон
            form.base_fields['generation_period_days'].initial = 30
            form.base_fields['is_active'].initial = True
            
            # Добавляем подсказки для полей
            form.base_fields['doctor'].help_text = 'Выберите врача из списка'
            form.base_fields['day_of_week'].help_text = 'Выберите день недели для расписания'
            form.base_fields['start_time'].help_text = 'Время начала рабочего дня'
            form.base_fields['end_time'].help_text = 'Время окончания рабочего дня'
            
        return form

@admin.register(DoctorPhoto)
class DoctorPhotoAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'order', 'image_preview']
    list_filter = ['doctor']
    ordering = ['doctor', 'order']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px;"/>', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Preview'

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'last_name', 'first_name', 'get_patronymic', 'is_staff')
    search_fields = ('username', 'last_name',  'first_name', 'email')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('last_name', 'first_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    readonly_fields = ('get_patronymic',)

    def get_patronymic(self, obj):
        try:
            return obj.doctor.patronymic
        except Doctor.DoesNotExist:
            return '-'
    get_patronymic.short_description = 'Отчество'

# Перерегистрируем модель User с нашим CustomUserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

class TreatmentPhotoInline(admin.TabularInline):
    model = TreatmentPhoto
    extra = 1
    fields = ['image', 'description', 'uploaded_at']
    readonly_fields = ['uploaded_at']

class TreatmentSessionInline(admin.TabularInline):
    model = TreatmentSession
    extra = 1
    fields = ['appointment', 'notes', 'created_at']
    readonly_fields = ['created_at']
    inlines = [TreatmentPhotoInline]     

@admin.register(Treatment)    
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'status', 'diagnosis', 'created_at']
    list_filter = ['status', 'doctor']
    search_fields = ['patient__full_name', 'doctor__user__last_name', 'diagnosis']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [TreatmentSessionInline]

    fieldsets = (
        (None, {
            'fields': ('patient', 'doctor', 'initial_appointment', 'status')
        }),
        ('Медицинская информация', {
            'fields': ('diagnosis', 'treatment_plan')
        } ),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(TreatmentSession)
class TreatmentSessionAdmin(admin.ModelAdmin):
    list_display = ['treatment', 'appointment', 'created_at']
    list_filter = ['treatment__doctor', 'treatment__patient']    
    search_fields = ['treatment__patient__full_name', 'treatment__doctor__user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [TreatmentPhotoInline]

    fieldsets = (
        (None, {
            'fields': ('treatment', 'appointment', 'notes')
        }),
        ('Информация о сессии', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
@admin.register(TreatmentPhoto)
class TreatmentPhotoAdmin(admin.ModelAdmin):
    list_display = ['session', 'image_preview', 'description', 'uploaded_at']
    list_filter = ['session__treatment__doctor', 'session__treatment__patient']
    search_fields = ['session__treatment__patient__full_name', 'description']
    readonly_fields = ['uploaded_at', 'image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" heigth="100" style="object-fit: cover;"/>', obj.image.url)
        return "Нет изображений"
    image_preview.short_description = 'Предосмотр'        

