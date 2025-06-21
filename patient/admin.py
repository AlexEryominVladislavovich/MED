from django.contrib import admin
from .models import Profile, Appointment, Review, Notification

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone_number', 'user']
    search_fields = ['full_name', 'phone_number', 'user__username']
    list_filter = ['user__is_active']

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['get_patient_display', 'get_doctor_info', 'get_appointment_time', 'status', 'price']
    list_filter = ['status', 'doctor', 'created_at']
    search_fields = [
        'patient__full_name', 'patient__phone_number', 'patient__username', 'patient__user__email',
        'guest_name', 'guest_phone', 'guest_comment',
        'doctor__user__first_name', 'doctor__user__last_name', 'time_slot__start_time'
    ]
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at', 'get_patient_full_info', 'get_guest_info']
    fieldsets = (
        ('Информация о пациенте', {
            'fields': ('patient', 'get_patient_full_info', 'get_guest_info'),
            'classes': ('wide',)
        }),
        ('Информация о приёме', {
            'fields': ('doctor', 'time_slot', 'status', 'price')
        }),
        ('Дополнительная информация', {
            'fields': ('description', 'diagnosis', 'treatment_appointment', 'guest_comment')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_patient_display(self, obj):
        if obj.patient and not obj.patient.is_guest:
            return f"{obj.patient.full_name} ({obj.patient.phone_number})"
        elif obj.guest_name or obj.guest_phone:
            return f"Гость: {obj.guest_name or ''} ({obj.guest_phone or ''})"
        return "-"
    get_patient_display.short_description = 'Пациент/Гость'

    def get_patient_full_info(self, obj):
        if obj.patient and not obj.patient.is_guest:
            user = obj.patient.user
            return f"""
            ФИО: {obj.patient.full_name}\nИмя пользователя: {obj.patient.username}\nEmail: {user.email if user else ''}\nТелефон: {obj.patient.phone_number}\nТип пользователя: Зарегистрированный
            """
        return "-"
    get_patient_full_info.short_description = 'Информация о пользователе'

    def get_guest_info(self, obj):
        if obj.guest_name or obj.guest_phone:
            return f"""
            Имя: {obj.guest_name or ''}\nТелефон: {obj.guest_phone or ''}
            """
        return "-"
    get_guest_info.short_description = 'Информация о госте'

    def get_doctor_info(self, obj):
        return f"{obj.doctor.user.get_full_name()} - {obj.doctor.room_number}"
    get_doctor_info.short_description = 'Врач'
    get_doctor_info.admin_order_field = 'doctor__user__last_name'

    def get_appointment_time(self, obj):
        return obj.time_slot.start_time.strftime('%d.%m.%Y %H:%M')
    get_appointment_time.short_description = 'Время приёма'
    get_appointment_time.admin_order_field = 'time_slot__start_time'

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'rating', 'create_at']
    list_filter = ['rating', 'doctor']
    search_fields = ['patient__full_name', 'doctor__user__first_name', 'comment']
    date_hierarchy = 'create_at'

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['profile', 'message_type', 'status', 'sent_at']
    list_filter = ['message_type', 'status']
    search_fields = ['profile__full_name', 'message']
    date_hierarchy = 'sent_at'
