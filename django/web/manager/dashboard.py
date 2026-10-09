import math
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.tickets.models import SeatPurchase, TicketPurchase


PERIODOS = (
    ("7", "7 días", 7),
    ("30", "30 días", 30),
    ("90", "90 días", 90),
    ("todo", "Todo", None),
)
PERIODO_POR_DEFECTO = "30"
# Solo las funciones publicadas pueden vender; las finalizadas conservan sus ventas.
ESTADOS_CON_VENTA = (Screening.Status.PUBLISHED, Screening.Status.FINISHED)
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DIAS_SEMANA_CORTOS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TOP_PELICULAS = 5
TOP_FRANJAS = 3
ETIQUETAS_EJE_X = 8


def build_dashboard(periodo=None, now=None):
    now = now or timezone.now()
    clave, dias = resolver_periodo(periodo)
    today = timezone.localdate(now)
    desde = inicio_del_dia(today - timedelta(days=dias - 1)) if dias else None

    filas = filas_de_funciones(funciones_realizadas(desde, now))
    resumen = resumir(filas)
    anterior = None
    if desde is not None:
        desde_anterior = inicio_del_dia(today - timedelta(days=dias * 2 - 1))
        anterior = resumir(filas_de_funciones(funciones_realizadas(desde_anterior, desde)))

    return {
        "periodos": [
            {"clave": valor, "etiqueta": etiqueta, "activo": valor == clave}
            for valor, etiqueta, _dias in PERIODOS
        ],
        "periodo": clave,
        "desde": timezone.localdate(desde) if desde else primera_fecha(filas),
        "hasta": today,
        "resumen": resumen,
        "variaciones": variaciones(resumen, anterior),
        "recaudacion": serie_recaudacion(filas, desde, today),
        "movies": peliculas_mas_vistas(filas),
        "salas": ocupacion_por_sala(filas),
        "horarios": demanda_por_horario(filas),
        "preventa": preventa(now),
    }


def resolver_periodo(periodo):
    for valor, _etiqueta, dias in PERIODOS:
        if valor == periodo:
            return valor, dias
    return resolver_periodo(PERIODO_POR_DEFECTO)


def inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def funciones_realizadas(desde, hasta):
    screenings = Screening.objects.filter(
        status__in=ESTADOS_CON_VENTA,
        starts_at__lt=hasta,
    )
    if desde is not None:
        screenings = screenings.filter(starts_at__gte=desde)
    return screenings


def filas_de_funciones(screenings):
    ids = screenings.values("pk")
    ventas = {
        venta["screening_id"]: venta
        for venta in TicketPurchase.objects.filter(screening__in=ids)
        .order_by()
        .values("screening_id")
        .annotate(sold=Sum("quantity"), recaudacion=Sum("total"))
    }
    utilizadas = dict(
        SeatPurchase.objects.filter(screening__in=ids, used_at__isnull=False)
        .order_by()
        .values("screening_id")
        .annotate(total=Count("pk"))
        .values_list("screening_id", "total")
    )
    capacidades = dict(
        Seat.objects.order_by()
        .values("room_id")
        .annotate(total=Count("pk"))
        .values_list("room_id", "total")
    )

    filas = []
    for screening in screenings.select_related("movie", "room").order_by("starts_at"):
        venta = ventas.get(screening.pk, {})
        sold = venta.get("sold") or 0
        filas.append(
            {
                "screening": screening,
                "inicio": timezone.localtime(screening.starts_at),
                "vendidas": sold,
                "recaudacion": venta.get("recaudacion") or Decimal("0"),
                "utilizadas": min(utilizadas.get(screening.pk, 0), sold),
                "capacidad": screening.capacity_snapshot or capacidades.get(screening.room_id, 0),
            }
        )
    return filas


def porcentaje(parte, total):
    return float(parte) * 100 / float(total) if total else 0


def resumir(filas):
    sold = sum(row["vendidas"] for row in filas)
    utilizadas = sum(row["utilizadas"] for row in filas)
    capacity = sum(row["capacidad"] for row in filas)
    recaudacion = sum((row["recaudacion"] for row in filas), Decimal("0"))
    return {
        "screenings": len(filas),
        "vendidas": sold,
        "utilizadas": utilizadas,
        "no_utilizadas": sold - utilizadas,
        "capacidad": capacity,
        "recaudacion": recaudacion,
        "ticket_promedio": recaudacion / sold if sold else Decimal("0"),
        "ocupacion": porcentaje(sold, capacity),
        "asistencia": porcentaje(utilizadas, sold),
        "asistencia_css": css_porcentaje(porcentaje(utilizadas, sold)),
    }


def primera_fecha(filas):
    return filas[0]["inicio"].date() if filas else None


def css_porcentaje(valor):
    # Se formatea acá para que la localización de la plantilla no use coma decimal en el CSS.
    return f"{max(min(valor, 100), 0):.2f}%"


def variacion(valor, unidad):
    if valor is None:
        return None
    if abs(valor) < 0.05:
        direccion = "flat"
    else:
        direccion = "up" if valor > 0 else "down"
    return {
        "valor": abs(valor),
        "signo": {"up": "+", "down": "−", "flat": ""}[direccion],
        "direccion": direccion,
        "unidad": unidad,
    }


def variacion_porcentual(current, previo):
    if not previo:
        return None
    return float(current - previo) * 100 / float(previo)


def variaciones(resumen, anterior):
    if anterior is None:
        return {}
    ocupacion = None
    if anterior["capacidad"]:
        ocupacion = resumen["ocupacion"] - anterior["ocupacion"]
    return {
        "recaudacion": variacion(
            variacion_porcentual(resumen["recaudacion"], anterior["recaudacion"]), "%"
        ),
        "vendidas": variacion(
            variacion_porcentual(resumen["vendidas"], anterior["vendidas"]), "%"
        ),
        "ocupacion": variacion(ocupacion, " p. p."),
    }


def escala(maximo, divisiones=4):
    if maximo <= 0:
        return 0, []
    paso_crudo = maximo / divisiones
    magnitud = 10 ** math.floor(math.log10(paso_crudo))
    paso = next(m * magnitud for m in (1, 2, 5, 10) if m * magnitud >= paso_crudo)
    tope = paso * math.ceil(maximo / paso)
    return tope, [paso * indice for indice in range(round(tope / paso) + 1)]


def sumar_mes(fecha):
    return (fecha.replace(day=28) + timedelta(days=4)).replace(day=1)


def clave_de_agrupacion(fecha, granularidad):
    if granularidad == "semana":
        return fecha - timedelta(days=fecha.weekday())
    if granularidad == "mes":
        return fecha.replace(day=1)
    return fecha


def serie_recaudacion(filas, desde, today):
    if not filas:
        return None
    start = timezone.localdate(desde) if desde else primera_fecha(filas)
    total_dias = (today - start).days + 1
    if total_dias <= 31:
        granularidad, avanzar = "dia", lambda fecha: fecha + timedelta(days=1)
    elif total_dias <= 26 * 7:
        granularidad, avanzar = "semana", lambda fecha: fecha + timedelta(days=7)
    else:
        granularidad, avanzar = "mes", sumar_mes

    claves = []
    clave = clave_de_agrupacion(start, granularidad)
    while clave <= today:
        claves.append(clave)
        clave = avanzar(clave)

    acumulado = {
        clave: {"recaudacion": Decimal("0"), "vendidas": 0, "screenings": 0}
        for clave in claves
    }
    for row in filas:
        datos = acumulado[clave_de_agrupacion(row["inicio"].date(), granularidad)]
        datos["recaudacion"] += row["recaudacion"]
        datos["vendidas"] += row["vendidas"]
        datos["screenings"] += 1

    maximo = max(datos["recaudacion"] for datos in acumulado.values())
    tope, ticks = escala(float(maximo))
    salto = math.ceil(len(claves) / ETIQUETAS_EJE_X)
    columnas = []
    marcado_maximo = False
    for indice, clave in enumerate(claves):
        datos = acumulado[clave]
        es_maximo = bool(maximo) and not marcado_maximo and datos["recaudacion"] == maximo
        marcado_maximo = marcado_maximo or es_maximo
        columnas.append(
            {
                "fecha": clave,
                **datos,
                "altura_css": css_porcentaje(porcentaje(datos["recaudacion"], tope)),
                "mostrar_etiqueta": indice % salto == 0,
                # En pantallas chicas se oculta una de cada dos etiquetas del eje.
                "etiqueta_secundaria": indice % salto == 0 and (indice // salto) % 2 == 1,
                "es_maximo": es_maximo,
            }
        )
    return {
        "granularidad": granularidad,
        "columnas": columnas,
        "ticks": [
            {"valor": tick, "posicion_css": css_porcentaje(porcentaje(tick, tope))}
            for tick in ticks
        ],
    }


def peliculas_mas_vistas(filas):
    por_pelicula = {}
    for row in filas:
        movie = row["screening"].movie
        datos = por_pelicula.setdefault(
            movie.pk,
            {
                "movie": movie,
                "vendidas": 0,
                "utilizadas": 0,
                "recaudacion": Decimal("0"),
                "screenings": 0,
            },
        )
        datos["vendidas"] += row["vendidas"]
        datos["utilizadas"] += row["utilizadas"]
        datos["recaudacion"] += row["recaudacion"]
        datos["screenings"] += 1

    ranking = sorted(
        (datos for datos in por_pelicula.values() if datos["vendidas"]),
        key=lambda datos: (-datos["vendidas"], -datos["recaudacion"], datos["movie"].title),
    )[:TOP_PELICULAS]
    for datos in ranking:
        datos["ancho_css"] = css_porcentaje(porcentaje(datos["vendidas"], ranking[0]["vendidas"]))
    return ranking


def ocupacion_por_sala(filas):
    por_sala = {}
    for row in filas:
        room = row["screening"].room
        datos = por_sala.setdefault(
            room.pk, {"room": room, "vendidas": 0, "capacidad": 0, "screenings": 0}
        )
        datos["vendidas"] += row["vendidas"]
        datos["capacidad"] += row["capacidad"]
        datos["screenings"] += 1

    rooms = list(por_sala.values())
    for datos in rooms:
        datos["ocupacion"] = porcentaje(datos["vendidas"], datos["capacidad"])
        datos["ancho_css"] = css_porcentaje(datos["ocupacion"])
    return sorted(rooms, key=lambda datos: (-datos["ocupacion"], datos["room"].name))


def demanda_por_horario(filas):
    if not filas:
        return None
    franjas = {}
    for row in filas:
        dia, hora = row["inicio"].weekday(), row["inicio"].hour
        datos = franjas.setdefault(
            (dia, hora),
            {
                "dia": DIAS_SEMANA[dia],
                "dia_corto": DIAS_SEMANA_CORTOS[dia],
                "hora": hora,
                "vendidas": 0,
                "capacidad": 0,
                "screenings": 0,
            },
        )
        datos["vendidas"] += row["vendidas"]
        datos["capacidad"] += row["capacidad"]
        datos["screenings"] += 1

    maximo = max(datos["vendidas"] for datos in franjas.values())
    for datos in franjas.values():
        datos["ocupacion"] = porcentaje(datos["vendidas"], datos["capacidad"])
        # Las franjas con ventas arrancan en 18% para no confundirse con las vacías.
        intensidad = 18 + 82 * datos["vendidas"] / maximo if datos["vendidas"] else 0
        datos["intensidad_css"] = css_porcentaje(intensidad)

    horas = range(min(hora for _dia, hora in franjas), max(hora for _dia, hora in franjas) + 1)
    return {
        "horas": list(horas),
        "dias": [
            {
                "dia": DIAS_SEMANA[dia],
                "dia_corto": DIAS_SEMANA_CORTOS[dia],
                "franjas": [
                    franjas.get(
                        (dia, hora),
                        {"dia": DIAS_SEMANA[dia], "hora": hora, "screenings": 0},
                    )
                    for hora in horas
                ],
            }
            for dia in range(7)
        ],
        "top": sorted(
            (datos for datos in franjas.values() if datos["vendidas"]),
            key=lambda datos: (-datos["vendidas"], -datos["ocupacion"]),
        )[:TOP_FRANJAS],
        "detalle": [franjas[clave] for clave in sorted(franjas)],
    }


def preventa(now):
    screenings = Screening.objects.filter(
        status=Screening.Status.PUBLISHED,
        starts_at__gte=now,
    )
    ventas = TicketPurchase.objects.filter(screening__in=screenings.values("pk")).aggregate(
        sold=Sum("quantity"),
        recaudacion=Sum("total"),
    )
    return {
        "screenings": screenings.count(),
        "vendidas": ventas["sold"] or 0,
        "recaudacion": ventas["recaudacion"] or Decimal("0"),
    }
