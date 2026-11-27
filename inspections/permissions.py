from rest_framework.permissions import BasePermission

ADMINISTRATOR = "Administrator"
ENGINEER = "Engineer"
SUPERVISOR = "Supervisor"


def has_role(user, role):
    return user.is_authenticated and user.groups.filter(name=role).exists()


class IsAdministrator(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        return has_role(request.user, ADMINISTRATOR)


class IsEngineerOrSupervisor(BasePermission):
    message = "Engineer or Supervisor role required."

    def has_permission(self, request, view):
        return has_role(request.user, ENGINEER) or has_role(
            request.user, SUPERVISOR
        )


class CanViewInspections(BasePermission):
    message = "An inspection role is required."

    def has_permission(self, request, view):
        return any(
            has_role(request.user, role)
            for role in (ADMINISTRATOR, ENGINEER, SUPERVISOR)
        )


class IsSupervisor(BasePermission):
    message = "Supervisor role required."

    def has_permission(self, request, view):
        return has_role(request.user, SUPERVISOR)
