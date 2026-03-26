from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered

from .models import LiquorData, MasterLiquorType, MasterLiquorCategory, MasterBottleType, MasterBrandList


def _safe_register(model):
    try:
        admin.site.register(model)
    except AlreadyRegistered:
        pass


_safe_register(LiquorData)
_safe_register(MasterLiquorType)
_safe_register(MasterLiquorCategory)
_safe_register(MasterBottleType)
_safe_register(MasterBrandList)
