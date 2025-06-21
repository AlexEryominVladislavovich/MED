from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import TimeBlock
from .serializers import TimeBlockSerializer
from datetime import datetime, timedelta

class TimeBlockViewSet(viewsets.ModelViewSet):
    serializer_class = TimeBlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return TimeBlock.objects.all()
        elif hasattr(user, 'doctor'):
            return TimeBlock.objects.filter(doctor=user.doctor)
        return TimeBlock.objects.none()

    @action(detail=False, methods=['get'])
    def available_slots(self, request):
        doctor_id = request.query_params.get('doctor_id')
        date = request.query_params.get('date')
        
        if not doctor_id or not date:
            return Response({"error": "Требуются параметры doctor_id и date"}, status=400)
            
        try:
            date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Неверный формат даты"}, status=400)
            
        start_datetime = datetime.combine(date, datetime.min.time())
        end_datetime = start_datetime + timedelta(days=1)
        
        blocks = TimeBlock.objects.filter(
            doctor_id=doctor_id,
            start_time__gte=start_datetime,
            end_time__lt=end_datetime,
            is_active=True
        ).order_by('start_time')
        
        serializer = self.get_serializer(blocks, many=True)
        return Response(serializer.data) 