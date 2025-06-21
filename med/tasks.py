from celery import shared_task
from .notifications import NotificationService
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_appointment_notifications():
    """Задача Celery для обработки уведомлений о предстоящих записях"""
    try:
        NotificationService.process_upcoming_appointments()
        logger.info("Успешно обработаны уведомления о предстоящих записях")
    except Exception as e:
        logger.error(f"Ошибка при обработке уведомлений: {str(e)}")
        raise

@shared_task
def send_appointment_reminder(appointment_id):
    """Отправка уведомления о конкретной записи"""
    from patient.models import Appointment
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        NotificationService.send_appointment_reminder(appointment)
        logger.info(f"Успешно отправлено напоминание для записи {appointment_id}")
    except Appointment.DoesNotExist:
        logger.error(f"Запись {appointment_id} не найдена")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания для записи {appointment_id}: {str(e)}")
        raise 