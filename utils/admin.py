""" Admin definitions """
from django.contrib import admin
from .models import Batch, Lock

admin.site.register(Batch)
admin.site.register(Lock)
