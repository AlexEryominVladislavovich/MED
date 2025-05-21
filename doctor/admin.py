from django.contrib import admin
from .models import Doctor, Schedule, Specialization

@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ['name_specialization', 'description_specialization']
    search_fields = ['name_specialization']

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'room_number', 'phone_number', 'is_active']
    list_filter = ['is_active', 'specialization']
    search_fields = ['user__first_name', 'user__last_name', 'room_number']
    filter_horizontal = ['specialization']

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
