from django import forms
from .models import ScheduleTemplate, Doctor
from django.core.exceptions import ValidationError

class ScheduleTemplateForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplate
        fields = ['doctor', 'day_of_week', 'start_time', 'end_time', 
                 'break_start', 'break_end', 'is_active', 'generation_period_days'] 