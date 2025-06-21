from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta
from .models import TimeSlot
import logging

logger = logging.getLogger(__name__)

@shared_task
def update_time_slots_availability():
    """
    Обновляет статус доступности временных слотов.
    Слоты, время которых уже прошло, помечаются как недоступные.
    """
    now = timezone.now()
    current_date = now.date()
    current_time = now.time()

    # Получаем все слоты на текущую дату, которые все еще доступны
    outdated_slots = TimeSlot.objects.filter(
        date=current_date,
        start_time__lt=current_time,
        is_available=True,
        is_deleted=False
    )

    # Помечаем прошедшие слоты как недоступные
    updated_count = outdated_slots.update(is_available=False)
    
    logger.info(f"Обновлено {updated_count} устаревших слотов")
    
    # Также проверяем и обновляем слоты на прошедшие даты
    past_slots = TimeSlot.objects.filter(
        date__lt=current_date,
        is_available=True,
        is_deleted=False
    )
    
    past_updated_count = past_slots.update(is_available=False)
    logger.info(f"Обновлено {past_updated_count} слотов за прошедшие даты")
    
    return updated_count + past_updated_count 