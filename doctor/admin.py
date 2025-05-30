from django.contrib import admin
from .models import Doctor, Schedule, Specialization, DoctorPhoto
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ['name_specialization', 'description_specialization']
    search_fields = ['name_specialization']

class DoctorPhotoInline(admin.TabularInline):
    model = DoctorPhoto
    extra = 1
    fields = ['image', 'order']

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'patronymic', 'room_number', 'phone_number', 'is_active']
    list_filter = ['is_active', 'specialization']
    search_fields = ['user__first_name', 'user__last_name', 'patronymic', 'room_number']
    filter_horizontal = ['specialization']
    autocomplete_fields = ['user']
    fields = ['user', 'patronymic', 'room_number', 'phone_number', 'bio', 'photo', 'specialization', 'is_active']
    inlines = [DoctorPhotoInline]

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
    get_full_name.short_description = "ФИО"

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'get_day_name', 'start_time', 'end_time', 'break_start', 'break_end']
    list_filter = ['day_of_week', 'doctor']
    search_fields = ['doctor__user__first_name', 'doctor__user__last_name']

    def get_day_name(self, obj):
        return obj.get_day_of_week_display()
    get_day_name.short_description = "День недели"

# Кастомизация UserAdmin с отображением отчества, если оно есть у врача
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
        # Показываем отчество, если есть связанный врач
        doctor = getattr(obj, 'doctor', None)
        return doctor.patronymic if doctor else ''
    get_patronymic.short_description = 'Отчество'

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
