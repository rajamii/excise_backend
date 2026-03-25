from django.contrib import admin

from .models import LiquorData, MasterLiquorType, MasterLiquorCategory

admin.site.register(LiquorData)
admin.site.register(MasterLiquorType)
admin.site.register(MasterLiquorCategory)
