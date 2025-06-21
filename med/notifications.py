from django.conf import settings
from django.core.mail import send_mail
from datetime import datetime, timedelta
from patient.models import Notification
import random
import string

class NotificationService:
    @classmethod
    def create_notification(cls, notification_type, **kwargs):
        """Создание записи уведомления для ручной обработки"""
        notification_data = cls._prepare_notification_data(notification_type, **kwargs)
        return Notification.objects.create(
            message_type=notification_type,
            status='pending',
            **notification_data
        )

    @classmethod
    def _prepare_notification_data(cls, notification_type, **kwargs):
        """Подготовка данных для уведомления"""
        data = {}

            
        if notification_type == 'registration_success':
            data['profile'] = kwargs.get('profile')
            data['phone_number'] = kwargs.get('profile').phone_number
            data['message'] = "Регистрация успешно завершена"
            
        elif notification_type in ['appointment_created', 'appointment_reminder']:
            appointment = kwargs.get('appointment')
            data['appointment'] = appointment
            data['phone_number'] = appointment.patient.phone_number if hasattr(appointment.patient, 'phone_number') else kwargs.get('phone_number')
            
            if hasattr(appointment.patient, 'user'):
                data['profile'] = appointment.patient
            
            doctor_name = appointment.doctor.user.get_full_name()
            appointment_time = appointment.time_slot.start_time
            patient_name = appointment.patient.full_name if hasattr(appointment.patient, 'full_name') else 'Пациент'
            
            if notification_type == 'appointment_created':
                data['message'] = f" {patient_name}!\n\n" \
                                f"Ваша запись к врачу {doctor_name} успешно создана.\n" \
                                f"Дата и время приёма: {appointment_time.strftime('%d.%m.%Y %H:%M')}\n\n" \
                                f"Пожалуйста, придите за 10 минут до начала приёма."
            else:
                data['message'] = f"{patient_name}, напоминаем вам что завтра {appointment_time.strftime('%d.%m.%Y')} в {appointment_time.strftime('%H:%M')} у вас назначен приём в нашей клинике"
        
        return data

    @classmethod
    def get_pending_notifications(cls):
        """Получение списка ожидающих отправки уведомлений"""
        return Notification.objects.filter(status='pending').order_by('created_at')

    @classmethod
    def mark_as_sent(cls, notification_id):
        """Отметить уведомление как отправленное"""
        notification = Notification.objects.get(id=notification_id)
        notification.status = 'sent'
        notification.save()

    @classmethod
    def mark_as_failed(cls, notification_id, error_message):
        """Отметить уведомление как не отправленное"""
        notification = Notification.objects.get(id=notification_id)
        notification.status = 'failed'
        notification.error_message = error_message
        notification.save()

    # Методы для создания конкретных типов уведомлений
    @classmethod
    def create_registration_code(cls, phone_number):
        """Создание уведомления с кодом подтверждения"""
        return cls.create_notification('registration_code', phone_number=phone_number)

    @classmethod
    def create_registration_success(cls, profile):
        """Создание уведомления об успешной регистрации"""
        return cls.create_notification('registration_success', profile=profile)

    @classmethod
    def create_appointment_notification(cls, appointment, phone_number=None):
        """Создание уведомления о записи"""
        return cls.create_notification('appointment_created', appointment=appointment, phone_number=phone_number)

    @classmethod
    def create_appointment_reminder(cls, appointment):
        """Создание напоминания о предстоящей записи"""
        return cls.create_notification('appointment_reminder', appointment=appointment)

    @classmethod
    def process_upcoming_appointments(cls):
        """Отправка уведомлений о предстоящих записях"""
        from patient.models import Appointment
        
        tomorrow = datetime.now() + timedelta(days=1)
        appointments = Appointment.objects.filter(
            time_slot__date=tomorrow.date(),
            status='scheduled'
        ).select_related('doctor', 'patient', 'patient__user', 'doctor__user')
        
        for appointment in appointments:
            if not Notification.objects.filter(
                appointment=appointment,
                message_type='appointment_reminder',
                status='sent'
            ).exists():
                cls.create_notification('appointment_reminder', appointment=appointment)

    @classmethod
    def _send_email_notification(cls, notification):
        """Отправка уведомления по email"""
        if notification.email:
            send_mail(
                subject=notification.get_message_type_display(),
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.email],
                fail_silently=False
            )

    @staticmethod
    def _send_whatsapp_notification(notification):
        """Отправка уведомления через WhatsApp"""
        # TODO: Интеграция с WhatsApp Business API
        pass

    # Методы для конкретных типов уведомлений
    @classmethod
    def send_registration_code(cls, phone_number):
        """Отправка кода подтверждения при регистрации"""
        return cls.create_notification('registration_code', phone_number=phone_number)

    @classmethod
    def send_registration_success(cls, profile):
        """Уведомление об успешной регистрации"""
        return cls.create_notification('registration_success', profile=profile)

    @classmethod
    def send_appointment_created(cls, appointment, phone_number=None):
        """Уведомление о создании записи"""
        return cls.create_notification('appointment_created', appointment=appointment, phone_number=phone_number)

    @classmethod
    def send_appointment_reminder(cls, appointment):
        """Напоминание о предстоящей записи"""
        return cls.create_notification('appointment_reminder', appointment=appointment) 