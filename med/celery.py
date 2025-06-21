import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'med.settings')

app = Celery('med')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Настройка периодических задач
app.conf.beat_schedule = {
    'process-appointment-notifications': {
        'task': 'med.tasks.process_appointment_notifications',
        'schedule': crontab(hour=10, minute=0),  # Запуск каждый день в 10:00
    },
    'update-time-slots-availability': {
        'task': 'doctor.tasks.update_time_slots_availability',
        'schedule': crontab(minute='*/10'),  # Запуск каждые 10 минут
    },
} 