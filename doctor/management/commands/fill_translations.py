from django.core.management.base import BaseCommand
from doctor.models import Specialization, Doctor

class Command(BaseCommand):
    help = 'Заполняет переводы для специализаций и врачей'

    def handle(self, *args, **options):
        self.stdout.write('Начинаем заполнение переводов...')

        # Заполняем переводы специализаций
        specializations_data = [
            {
                'name_specialization': 'Терапевт',
                'name_specialization_ky': 'Терапевт',
                'description_specialization': 'Врач общей практики, занимающийся диагностикой и лечением внутренних болезней',
                'description_specialization_ky': 'Ички органдардын ооруларын диагноздоо жана дарылоо менен алектенген жалпы дарыгер',
            },
            {
                'name_specialization': 'Кардиолог',
                'name_specialization_ky': 'Кардиолог',
                'description_specialization': 'Врач, специализирующийся на заболеваниях сердечно-сосудистой системы',
                'description_specialization_ky': 'Жүрөк-кан тамыр системасынын оорулары боюнча адистешкен дарыгер',
            },
            {
                'name_specialization': 'Невролог',
                'name_specialization_ky': 'Невролог',
                'description_specialization': 'Врач, специализирующийся на заболеваниях нервной системы',
                'description_specialization_ky': 'Нерв системасынын оорулары боюнча адистешкен дарыгер',
            },
            {
                'name_specialization': 'Офтальмолог',
                'name_specialization_ky': 'Офтальмолог',
                'description_specialization': 'Врач, специализирующийся на заболеваниях глаз',
                'description_specialization_ky': 'Көз оорулары боюнча адистешкен дарыгер',
            },
            {
                'name_specialization': 'Стоматолог',
                'name_specialization_ky': 'Стоматолог',
                'description_specialization': 'Врач, специализирующийся на заболеваниях зубов и полости рта',
                'description_specialization_ky': 'Тиш жана ооз көңдөйүнүн оорулары боюнча адистешкен дарыгер',
            },
        ]

        for spec_data in specializations_data:
            spec, created = Specialization.objects.get_or_create(
                name_specialization=spec_data['name_specialization'],
                defaults=spec_data
            )
            if not created:
                # Обновляем переводы для существующих специализаций
                for field, value in spec_data.items():
                    setattr(spec, field, value)
                spec.save()
            
            action = 'создана' if created else 'обновлена'
            self.stdout.write(f'Специализация "{spec.name_specialization}" {action}')

        # Заполняем переводы для врачей (если есть)
        doctors = Doctor.objects.all()
        for doctor in doctors:
            if doctor.bio and not hasattr(doctor, 'bio_ky'):
                # Копируем русский текст как кыргызский (временное решение)
                doctor.bio_ky = doctor.bio
                doctor.save()
                self.stdout.write(f'Перевод биографии добавлен для врача {doctor.user.first_name} {doctor.user.last_name}')

        self.stdout.write(self.style.SUCCESS('Переводы успешно заполнены!')) 