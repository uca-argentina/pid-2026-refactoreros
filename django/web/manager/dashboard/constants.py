"""Dashboard: constants."""

from domain.screenings.models import Screening

PERIODS = (
    ("7", "7 días", 7),
    ("30", "30 días", 30),
    ("90", "90 días", 90),
    ("todo", "Todo", None),
)


DEFAULT_PERIOD = "30"


ACCOUNTED_STATUSES = (Screening.Status.FINISHED,)


PURCHASED_STATUSES = (
    Screening.Status.PUBLISHED,
    Screening.Status.IN_PROGRESS,
    Screening.Status.FINISHED,
)


WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


SHORT_WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


TOP_MOVIES = 5


TOP_TIME_SLOTS = 3


X_AXIS_LABELS = 8


TIME_SLOT_MINUTES = 30
