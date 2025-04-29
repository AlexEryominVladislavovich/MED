from rest_framework import viewsets
from django.shortcuts import get_object_or_404
from .models import Profile
from .serializers import RegistrationSerializer, ProfileSerializer
from rest_frameworkresponse import Response
from django.contrib.auth.models import User

class RegistrationViewSet(viewsets.ModelViewSet):
    queryset = Profile.objectd.all()
    serializer_class = ProfileSerializer
