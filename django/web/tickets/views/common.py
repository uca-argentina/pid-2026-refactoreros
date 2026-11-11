"""Common."""


def purchase_error_message(error, fallback):
    if hasattr(error, "message_dict"):
        for messages_for_field in error.message_dict.values():
            if messages_for_field:
                return messages_for_field[0]
    if isinstance(error, dict):
        for messages_for_field in error.values():
            if messages_for_field:
                return messages_for_field[0]
    if getattr(error, "messages", None):
        return error.messages[0]
    return fallback
