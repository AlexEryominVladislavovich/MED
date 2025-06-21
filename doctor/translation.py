from modeltranslation.translator import translator, TranslationOptions
from .models import Specialization, Doctor

class SpecializationTranslationOptions(TranslationOptions):
    fields = ('name_specialization', 'description_specialization',)

class DoctorTranslationOptions(TranslationOptions):
    fields = ('bio', 'full_bio',)

translator.register(Specialization, SpecializationTranslationOptions)
translator.register(Doctor, DoctorTranslationOptions) 