ROLES = ("admin", "manager", "recruiter", "interviewer")

PERMISSIONS = {
    "admin": {
        "users:manage",
        "audit:view",
        "jobs:manage",
        "candidates:manage",
        "pipeline:move",
        "interviews:manage",
        "bi:view_all",
        "agent:write",
        "boss:manage",
    },
    "manager": {
        "audit:view",
        "jobs:manage",
        "candidates:manage",
        "pipeline:move",
        "interviews:manage",
        "bi:view_all",
        "agent:write",
        "boss:manage",
    },
    "recruiter": {
        "jobs:create",
        "candidates:create",
        "candidates:view_own",
        "pipeline:move_own",
        "interviews:manage",
        "bi:view_own",
        "boss:manage_own",
    },
    "interviewer": {
        "candidates:view_assigned",
        "interviews:feedback",
    },
}


def role_permissions(role):
    return sorted(PERMISSIONS.get(role, set()))


def has_permission(user, permission):
    return permission in PERMISSIONS.get(user.role, set())
