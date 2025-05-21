from django.contrib import admin
from .models import Profile, Appointment, Review, Notification

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone_number', 'user']
    search_fields = ['full_name', 'phone_number', 'user__username']
    list_filter = ['user__is_active']

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'time_slot', 'status']
    list_filter = ['status', 'doctor']
    search_fields = ['patient__full_name', 'doctor__user__first_name', 'doctor__user__last_name']
    date_hierarchy = 'created_at'

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
