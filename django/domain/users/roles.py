def staff_role(user):
    if not user.is_authenticated or not user.is_active:
        return ""
    if hasattr(user, "manager_profile"):
        return "manager"
    if hasattr(user, "operator_profile"):
        return "operator"
    if hasattr(user, "usher_profile"):
        return "usher"
    return ""


def can_validate_tickets(user):
    return staff_role(user) in {"manager", "operator"}
