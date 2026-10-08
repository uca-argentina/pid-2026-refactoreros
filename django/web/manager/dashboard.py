import math
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from domain.screenings.models import Funcion
from domain.seats.models import Seat
from domain.tickets.models import CompraAsiento, CompraEntrada


PERIODOS = (
    ("7", "7 días", 7),
    ("30", "30 días", 30),
    ("90", "90 días", 90),
    ("todo", "Todo", None),
)
PERIODO_POR_DEFECTO = "30"
# Solo las funciones publicadas pueden vender; las finalizadas conservan sus ventas.
ESTADOS_CON_VENTA = (Funcion.Estado.PUBLICADA, Funcion.Estado.FINALIZADA)
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DIAS_SEMANA_CORTOS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TOP_PELICULAS = 5
TOP_FRANJAS = 3
ETIQUETAS_EJE_X = 8


def construir_dashboard(periodo=None, ahora=None):
    ahora = ahora or timezone.now()
    clave, dias = resolver_periodo(periodo)
    hoy = timezone.localdate(ahora)
    desde = inicio_del_dia(hoy - timedelta(days=dias - 1)) if dias else None

    filas = filas_de_funciones(funciones_realizadas(desde, ahora))
    resumen = resumir(filas)
    anterior = None
    if desde is not None:
        desde_anterior = inicio_del_dia(hoy - timedelta(days=dias * 2 - 1))
        anterior = resumir(filas_de_funciones(funciones_realizadas(desde_anterior, desde)))

    return {
        "periodos": [
            {"clave": valor, "etiqueta": etiqueta, "activo": valor == clave}
            for valor, etiqueta, _dias in PERIODOS
        ],
        "periodo": clave,
        "desde": timezone.localdate(desde) if desde else primera_fecha(filas),
        "hasta": hoy,
        "resumen": resumen,
        "variaciones": variaciones(resumen, anterior),
        "recaudacion": serie_recaudacion(filas, desde, hoy),
        "peliculas": peliculas_mas_vistas(filas),
        "salas": ocupacion_por_sala(filas),
        "horarios": demanda_por_horario(filas),
        "preventa": preventa(ahora),
    }


def resolver_periodo(periodo):
    for valor, _etiqueta, dias in PERIODOS:
        if valor == periodo:
            return valor, dias
    return resolver_periodo(PERIODO_POR_DEFECTO)


def inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def funciones_realizadas(desde, hasta):
    funciones = Funcion.objects.filter(
        estado__in=ESTADOS_CON_VENTA,
        fecha_horario__lt=hasta,
    )
    if desde is not None:
        funciones = funciones.filter(fecha_horario__gte=desde)
    return funciones


def filas_de_funciones(funciones):
    ids = funciones.values("pk")
    ventas = {
        venta["funcion_id"]: venta
        for venta in CompraEntrada.objects.filter(funcion__in=ids)
        .order_by()
        .values("funcion_id")
        .annotate(vendidas=Sum("cantidad"), recaudacion=Sum("total"))
    }
    utilizadas = dict(
        CompraAsiento.objects.filter(funcion__in=ids, utilizada_en__isnull=False)
        .order_by()
        .values("funcion_id")
        .annotate(total=Count("pk"))
        .values_list("funcion_id", "total")
    )
    capacidades = dict(
        Seat.objects.order_by()
        .values("sala_id")
        .annotate(total=Count("pk"))
        .values_list("sala_id", "total")
    )

    filas = []
    for funcion in funciones.select_related("pelicula", "sala").order_by("fecha_horario"):
        venta = ventas.get(funcion.pk, {})
        vendidas = venta.get("vendidas") or 0
        filas.append(
            {
                "funcion": funcion,
                "inicio": timezone.localtime(funcion.fecha_horario),
                "vendidas": vendidas,
                "recaudacion": venta.get("recaudacion") or Decimal("0"),
                "utilizadas": min(utilizadas.get(funcion.pk, 0), vendidas),
                "capacidad": funcion.capacidad_snapshot or capacidades.get(funcion.sala_id, 0),
            }
        )
    return filas


def porcentaje(parte, total):
    return float(parte) * 100 / float(total) if total else 0


def resumir(filas):
    vendidas = sum(fila["vendidas"] for fila in filas)
    utilizadas = sum(fila["utilizadas"] for fila in filas)
    capacidad = sum(fila["capacidad"] for fila in filas)
    recaudacion = sum((fila["recaudacion"] for fila in filas), Decimal("0"))
    return {
        "funciones": len(filas),
        "vendidas": vendidas,
        "utilizadas": utilizadas,
        "no_utilizadas": vendidas - utilizadas,
        "capacidad": capacidad,
        "recaudacion": recaudacion,
        "ticket_promedio": recaudacion / vendidas if vendidas else Decimal("0"),
        "ocupacion": porcentaje(vendidas, capacidad),
        "asistencia": porcentaje(utilizadas, vendidas),
        "asistencia_css": css_porcentaje(porcentaje(utilizadas, vendidas)),
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


def variacion_porcentual(actual, previo):
    if not previo:
        return None
    return float(actual - previo) * 100 / float(previo)


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


def serie_recaudacion(filas, desde, hoy):
    if not filas:
        return None
    inicio = timezone.localdate(desde) if desde else primera_fecha(filas)
    total_dias = (hoy - inicio).days + 1
    if total_dias <= 31:
        granularidad, avanzar = "dia", lambda fecha: fecha + timedelta(days=1)
    elif total_dias <= 26 * 7:
        granularidad, avanzar = "semana", lambda fecha: fecha + timedelta(days=7)
    else:
        granularidad, avanzar = "mes", sumar_mes

    claves = []
    clave = clave_de_agrupacion(inicio, granularidad)
    while clave <= hoy:
        claves.append(clave)
        clave = avanzar(clave)

    acumulado = {
        clave: {"recaudacion": Decimal("0"), "vendidas": 0, "funciones": 0}
        for clave in claves
    }
    for fila in filas:
        datos = acumulado[clave_de_agrupacion(fila["inicio"].date(), granularidad)]
        datos["recaudacion"] += fila["recaudacion"]
        datos["vendidas"] += fila["vendidas"]
        datos["funciones"] += 1

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
    for fila in filas:
        pelicula = fila["funcion"].pelicula
        datos = por_pelicula.setdefault(
            pelicula.pk,
            {
                "pelicula": pelicula,
                "vendidas": 0,
                "utilizadas": 0,
                "recaudacion": Decimal("0"),
                "funciones": 0,
            },
        )
        datos["vendidas"] += fila["vendidas"]
        datos["utilizadas"] += fila["utilizadas"]
        datos["recaudacion"] += fila["recaudacion"]
        datos["funciones"] += 1

    ranking = sorted(
        (datos for datos in por_pelicula.values() if datos["vendidas"]),
        key=lambda datos: (-datos["vendidas"], -datos["recaudacion"], datos["pelicula"].titulo),
    )[:TOP_PELICULAS]
    for datos in ranking:
        datos["ancho_css"] = css_porcentaje(porcentaje(datos["vendidas"], ranking[0]["vendidas"]))
    return ranking


def ocupacion_por_sala(filas):
    por_sala = {}
    for fila in filas:
        sala = fila["funcion"].sala
        datos = por_sala.setdefault(
            sala.pk, {"sala": sala, "vendidas": 0, "capacidad": 0, "funciones": 0}
        )
        datos["vendidas"] += fila["vendidas"]
        datos["capacidad"] += fila["capacidad"]
        datos["funciones"] += 1

    salas = list(por_sala.values())
    for datos in salas:
        datos["ocupacion"] = porcentaje(datos["vendidas"], datos["capacidad"])
        datos["ancho_css"] = css_porcentaje(datos["ocupacion"])
    return sorted(salas, key=lambda datos: (-datos["ocupacion"], datos["sala"].nombre))


def demanda_por_horario(filas):
    if not filas:
        return None
    franjas = {}
    for fila in filas:
        dia, hora = fila["inicio"].weekday(), fila["inicio"].hour
        datos = franjas.setdefault(
            (dia, hora),
            {
                "dia": DIAS_SEMANA[dia],
                "dia_corto": DIAS_SEMANA_CORTOS[dia],
                "hora": hora,
                "vendidas": 0,
                "capacidad": 0,
                "funciones": 0,
            },
        )
        datos["vendidas"] += fila["vendidas"]
        datos["capacidad"] += fila["capacidad"]
        datos["funciones"] += 1

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
                        {"dia": DIAS_SEMANA[dia], "hora": hora, "funciones": 0},
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


def preventa(ahora):
    funciones = Funcion.objects.filter(
        estado=Funcion.Estado.PUBLICADA,
        fecha_horario__gte=ahora,
    )
    ventas = CompraEntrada.objects.filter(funcion__in=funciones.values("pk")).aggregate(
        vendidas=Sum("cantidad"),
        recaudacion=Sum("total"),
    )
    return {
        "funciones": funciones.count(),
        "vendidas": ventas["vendidas"] or 0,
        "recaudacion": ventas["recaudacion"] or Decimal("0"),
    }
