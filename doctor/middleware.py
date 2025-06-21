import logging
from django.urls import resolve
from django.utils import timezone
from datetime import timedelta
from .models import ScheduleTemplate, Doctor, TemplateTimeSlot
from django.db.models import Q
from django.utils.translation import activate, get_language
from django.conf import settings

logger = logging.getLogger(__name__)

class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Получаем язык из заголовка Accept-Language
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        
        # Парсим заголовок Accept-Language
        if accept_language:
            # Берем первый язык из списка
            primary_lang = accept_language.split(',')[0].split(';')[0].strip().lower()
            
            # Проверяем, поддерживается ли этот язык
            if primary_lang in ['ru', 'ky']:
                activate(primary_lang)
            else:
                # Если язык не поддерживается (например, en), используем русский
                activate('ru')
        else:
            # Если заголовок отсутствует, используем русский
            activate('ru')
        
        return self.get_response(request)

class SlotGenerationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Проверяем только API запросы к врачам и слотам
            if any(path in request.path for path in ['/api/doctors', '/api/time-slots']):
                logger.info("Запуск генерации слотов через middleware")
                self.generate_slots()
        except Exception as e:
            logger.error(f"Ошибка в SlotGenerationMiddleware.__call__: {e}")

        return self.get_response(request)

    def generate_slots(self):
        """
        Генерация слотов для всех активных шаблонов
        """
        try:
            today = timezone.now().date()
            logger.info(f"Начало генерации слотов на дату: {today}")
            
            # Получаем всех активных врачей
            active_doctors = Doctor.objects.filter(is_active=True)
            logger.info(f"Найдено активных врачей: {active_doctors.count()}")
            
            if not active_doctors.exists():
                logger.warning("Нет активных врачей в системе")
                return

            # Получаем все активные шаблоны для активных врачей
            templates = ScheduleTemplate.objects.filter(
                is_active=True,
                doctor__in=active_doctors
            ).select_related('doctor').distinct()

            logger.info(f"Найдено активных шаблонов: {templates.count()}")

            for template in templates:
                try:
                    doctor_name = f"{template.doctor.user.first_name} {template.doctor.user.last_name}"
                    logger.info(f"Обработка шаблона {template.id} для врача: {doctor_name}")

                    # Проверяем наличие слотов шаблона
                    template_slots = TemplateTimeSlot.objects.filter(template=template)
                    if not template_slots.exists():
                        logger.warning(f"У шаблона {template.id} нет определенных слотов")
                        continue

                    # Проверяем необходимость генерации
                    should_generate = (
                        not template.last_slot_generation or
                        template.last_slot_generation < today or
                        not template.time_slots.filter(
                            date__gte=today,
                            is_available=True
                        ).exists()
                    )

                    if should_generate:
                        logger.info(f"Генерация слотов для шаблона {template.id}")
                        
                        # Генерируем слоты на ближайшие дни
                        generation_days = template.generation_period_days or 30
                        end_date = today + timedelta(days=generation_days)
                        
                        # Генерируем слоты
                        slots_created = template.create_time_slots(
                            start_date=today,
                            end_date=end_date
                        )
                        
                        if slots_created > 0:
                            template.last_slot_generation = today
                            template.save(update_fields=['last_slot_generation'])
                            logger.info(f"Успешно создано {slots_created} слотов для шаблона {template.id}")
                        else:
                            logger.warning(f"Не удалось создать слоты для шаблона {template.id}")
                    else:
                        logger.info(f"Генерация слотов не требуется для шаблона {template.id}")
                        
                except Exception as e:
                    logger.error(f"Ошибка при генерации слотов для шаблона {template.id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка в процессе генерации слотов: {e}") 