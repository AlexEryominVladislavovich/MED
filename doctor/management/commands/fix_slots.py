from django.core.management.base import BaseCommand
from doctor.models import TimeSlot
from patient.models import Appointment
from django.db.models import Exists, OuterRef
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Исправляет статус доступности временных слотов'

    def handle(self, *args, **options):
        # Получаем все слоты
        slots = TimeSlot.objects.all()
        total_slots = slots.count()
        fixed_slots = 0

        self.stdout.write(f"Всего слотов: {total_slots}")

        # Обновляем статус доступности для каждого слота
        for slot in slots:
            has_appointment = Appointment.objects.filter(
                time_slot=slot,
                status__in=['scheduled', 'visited', 'no_show', 'completed_with_treatment']
            ).exists()

            if has_appointment and slot.is_available:
                slot.is_available = False
                slot.save()
                fixed_slots += 1
                logger.info(f"Слот {slot.id} помечен как недоступный")
            elif not has_appointment and not slot.is_available:
                slot.is_available = True
                slot.save()
                fixed_slots += 1
                logger.info(f"Слот {slot.id} помечен как доступный")

        self.stdout.write(
            self.style.SUCCESS(
                f'Исправлено {fixed_slots} слотов из {total_slots}'
            )
        )