from rest_framework import viewsets, generics
from django.shortcuts import get_object_or_404
from .models import Profile, Appointment
from .serializers import (
    ProfileSerializer,
    PatientAppointmentDetailSerializer
)
from rest_framework.permissions import IsAuthenticated

class RegistrationViewSet(viewsets.ModelViewSet):
    """
    ViewSet для регистрации пациентов.
    
    Attributes:
        queryset: Набор всех профилей пациентов
        serializer_class: Сериализатор для преобразования данных профиля
    """
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer

class PatientAppointmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для просмотра записей пациента на приём.
    
    Преимущества использования ViewSet:
    - Автоматическая генерация URL через router
    - Встроенная поддержка пагинации
    - Возможность добавления дополнительных действий через @action
    - Автоматическая документация API
    
    Attributes:
        serializer_class: Сериализатор для преобразования данных записи
        permission_classes: Список классов разрешений (только для авторизованных)
    """
    serializer_class = PatientAppointmentDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Получение списка записей текущего пациента.
        
        Returns:
            QuerySet: Отфильтрованный и оптимизированный список записей, где:
            - Записи принадлежат текущему пациенту
            - Предзагружены связанные данные врача и временного слота
            - Отсортированы от новых к старым
        """
        return Appointment.objects.filter(
            patient=self.request.user.profile  # Фильтрация по текущему пациенту
        ).select_related(
            'doctor',  # Оптимизация запроса: загрузка данных врача
            'doctor__user',  # Загрузка данных пользователя врача
            'time_slot'  # Загрузка данных временного слота
        ).order_by('-created_at')  # Сортировка от новых к старым

# Сохраняем старый view для обратной совместимости
class PatientAppointmentListView(generics.ListAPIView):
    """
    Устаревший view для просмотра записей пациента.
    
    Note:
        Этот класс сохранен для обратной совместимости.
        Рекомендуется использовать PatientAppointmentViewSet.
        
    Attributes:
        serializer_class: Сериализатор для преобразования данных записи
        permission_classes: Список классов разрешений
    """
    serializer_class = PatientAppointmentDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Получение списка записей текущего пациента.
        
        Note:
            Логика идентична PatientAppointmentViewSet.get_queryset
            для сохранения совместимости.
            
        Returns:
            QuerySet: Отфильтрованный и оптимизированный список записей
        """
        return Appointment.objects.filter(
            patient=self.request.user.profile
        ).select_related(
            'doctor', 
            'doctor__user',
            'time_slot'
        ).order_by('-created_at')
