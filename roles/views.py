from django.shortcuts import render
from django.http import HttpRequest
from roles.models import Role

def is_dev(request: HttpRequest):
    if request.user.role.name == 'dev':
        return True
    return False


def is_role_capable_of(request: HttpRequest, operation, model):
    if model == 'user':
        if request.user.role.user_access == Role.READ_WRITE:
            return True
        elif request.user.role.user_access == operation:
            return True
        else:
            return False

    if model == 'company_registration':
        if request.user.role.company_registration_access == Role.READ_WRITE:
            return True
        elif request.user.role.company_registration_access == operation:
            return True
        else:
            return False

    if model == 'contact_us':
        if request.user.role.contact_us_access == Role.READ_WRITE:
            return True
        elif request.user.role.contact_us_access == operation:
            return True
        else:
            return False

    if model == 'licenseapplication':
        if request.user.role.licenseapplication_access == Role.READ_WRITE:
            return True
        elif request.user.role.licenseapplication_access == operation:
            return True
        else:
            return False

    if model == 'masters':
        if request.user.role.masters_access == Role.READ_WRITE:
            return True
        elif request.user.role.masters_access == operation:
            return True
        else:
            return False

    if model == 'roles':
        if request.user.role.roles_access == Role.READ_WRITE:
            return True
        elif request.user.role.roles_access == operation:
            return True
        else:
            return False

    if model == 'salesman_barman':
        if request.user.role.salesman_barman_access == Role.READ_WRITE:
            return True
        elif request.user.role.salesman_barman_access == operation:
            return True
        else:
            return False
