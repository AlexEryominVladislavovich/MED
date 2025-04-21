from django.shortcuts import render
from rest_framework import viewsets
from .models import Profile

class RegistrationViewSet(viewsets.ModelViewSet):
    queryset = Profile.objectd.all()
    serializer_class = ProfileSerializer
