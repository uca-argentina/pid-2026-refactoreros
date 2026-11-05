import json
import csv
import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError, transaction
from django.db.models import OuterRef, Q, Subquery, Sum
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from domain.cinema.models import CinemaSettings
from domain.candy.models import CandyOrder
from . import services
from .forms import GameSettingsForm, GrantForm, ImportForm, QuestionForm, SlotForm
from .models import GameAccount, GameEvent, PrizeCoupon, Question, QuestionUse, TriviaRun, WheelConfig, WheelSlot, WheelSpin


def manager_only(view):
    @wraps(view)
    @login_required
    @never_cache
    def wrapped(request, *args, **kwargs):
        services.require_manager(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def context(**kwargs):
    return {"section": "Juegos", "cinema": CinemaSettings.current(), **kwargs}


@never_cache
@require_GET
def home(request):
    return redirect("/?juegos=1")


@login_required
@never_cache
@require_GET
def game_state(request):
    return JsonResponse(services.state(request.user))


@login_required
@never_cache
@require_GET
def coupons(request):
    return render(request, "games/coupons.html", context(
        game_initial=services.state(request.user),
        coupons=PrizeCoupon.objects.filter(user=request.user, status="available", pickup_order__isnull=True).select_related("product"),
        has_pickup_orders=CandyOrder.objects.filter(reward_user=request.user).exists(), pickup_key=uuid.uuid4()))


@login_required
@never_cache
@require_POST
def pickup(request):
    try:
        ids = [int(pk) for pk in request.POST.getlist("coupons")]
        order = services.request_pickup(request.user, ids, request.POST.get("key"))
        messages.success(request, f"Tu retiro de premios #{order.pk} está listo en Candy.")
        return redirect(f"{reverse('candy_store')}#mis-retiros")
    except (ValueError, ValidationError) as error:
        services.audit(request.user, "pickup_request_rejected")
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Selección inválida.")
    except OperationalError:
        messages.error(request, "Hay otra operación en curso. Volvé a intentar.")
    return redirect("games:coupons")


@login_required
@never_cache
@require_GET
def pickup_detail(request, pk):
    order = get_object_or_404(CandyOrder, pk=pk, reward_user=request.user)
    return render(request, "candy_detail.html", context(order=order, client_nav_section="candy"))


@login_required
@never_cache
@require_POST
def action(request, action):
    try:
        if len(request.body) > 4096:
            raise ValidationError("La solicitud es demasiado grande.")
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValidationError("La solicitud no es válida.")
        if action == "start":
            result = {"run": services.start(request.user, data.get("key"))}
        elif action == "answer":
            if type(data.get("run")) is not int:
                raise ValidationError("La partida no es válida.")
            result = services.answer(request.user, data["run"], data.get("step"), data.get("choice"), data.get("key"))
        elif action == "spin":
            result = {"spin": services.spin(request.user, data.get("key"))}
        else:
            return JsonResponse({"error": "Acción desconocida."}, status=404)
        return JsonResponse({**result, "state": services.state(request.user)})
    except (ValidationError, ValueError, UnicodeDecodeError) as error:
        services.audit(request.user, "request_rejected", {"action": action})
        message = " ".join(error.messages) if isinstance(error, ValidationError) else "La solicitud no es válida."
        return JsonResponse({"error": message}, status=400)
    except OperationalError:
        # A SQLite busy conflict cannot partially commit a reward. Retry same UUID.
        return JsonResponse({"error": "Hay otra operación en curso. Reintentá.", "retry": True}, status=409)


@manager_only
def dashboard(request):
    tab = request.GET.get("tab", "questions")
    search = request.GET.get("q", "").strip()[:100]
    querysets = {
        "questions": Question.objects.annotate(last_assigned_at=Subquery(
            QuestionUse.objects.filter(question_id=OuterRef("pk")).order_by("-created_at").values("created_at")[:1]
        )).order_by("difficulty", "pk"),
        "wheel": WheelSlot.objects.filter(active=True).select_related("product"),
        "archived": WheelSlot.objects.filter(active=False).select_related("product"),
        "users": get_user_model().objects.order_by("username"),
        "events": GameEvent.objects.select_related("user", "actor"),
        "runs": TriviaRun.objects.select_related("user").prefetch_related("answers"),
        "spins": WheelSpin.objects.select_related("user"),
        "coupons": PrizeCoupon.objects.select_related("user", "redeemed_by"),
    }
    if tab not in querysets:
        tab = "questions"
    rows = querysets[tab]
    if search:
        if tab == "questions":
            rows = rows.filter(text__icontains=search)
        elif tab in ("wheel", "archived"):
            rows = rows.filter(label__icontains=search)
        elif tab == "users":
            rows = rows.filter(Q(username__icontains=search) | Q(email__icontains=search))
        elif tab == "events":
            rows = rows.filter(Q(kind__icontains=search) | Q(user__username__icontains=search))
        else:
            rows = rows.filter(user__username__icontains=search)
    dates = {name: request.GET.get(name, "") for name in ("date_from", "date_to")}
    if tab == "events":
        for name, value in dates.items():
            if value:
                try:
                    parsed = parse_date(value)
                except ValueError:
                    parsed = None
                if parsed is None:
                    return HttpResponse("Fecha inválida.", status=400)
                rows = rows.filter(**{f"created_at__date__{'gte' if name == 'date_from' else 'lte'}": parsed})
        if dates["date_from"] and dates["date_to"] and dates["date_from"] > dates["date_to"]:
            return HttpResponse("El rango de fechas es inválido.", status=400)
        if request.GET.get("export") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
            response["Content-Disposition"] = f'attachment; filename="auditoria-juegos-{timestamp}.csv"'
            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow(["ID", "Fecha", "Evento", "Usuario ID", "Administrador ID", "Detalle"])
            for event in rows.iterator(chunk_size=1000):
                kind = "'" + event.kind if event.kind.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else event.kind
                writer.writerow([event.pk, timezone.localtime(event.created_at).isoformat(), kind, event.user_id, event.actor_id, json.dumps(event.data, ensure_ascii=False)])
            return response
    return render(request, "games/dashboard.html", context(tab=tab, q=search, **dates,
        question_count=len({services.question_fingerprint(q["text"]) for level in Question.Difficulty.values for q in services.new_questions(level)}),
        slot_count=WheelSlot.objects.filter(active=True).aggregate(n=Sum("count"))["n"] or 0,
        question_seconds=WheelConfig.objects.get_or_create(pk=1)[0].question_seconds,
        rows=Paginator(rows, 30).get_page(request.GET.get("page"))))


@manager_only
def game_settings(request):
    config, _ = WheelConfig.objects.get_or_create(pk=1)
    form = GameSettingsForm(request.POST if request.method == "POST" else None, instance=config)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            services.lock_wheel()
            WheelConfig.objects.filter(pk=1).update(question_seconds=form.cleaned_data["question_seconds"])
            services.audit(None, "game_settings_saved", {"question_seconds": form.cleaned_data["question_seconds"]}, request.user)
        messages.success(request, "Tiempo por pregunta actualizado para nuevas partidas.")
        return redirect("games:dashboard")
    return render(request, "games/form.html", context(form=form, form_title="Tiempo de la trivia", submit_label="Guardar configuración"))


@manager_only
def edit(request, kind, pk=None):
    if kind not in ("question", "slot"):
        raise PermissionDenied
    model, form_class = (Question, QuestionForm) if kind == "question" else (WheelSlot, SlotForm)
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST if request.method == "POST" else None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                services.lock_wheel()
                if kind == "slot":
                    total = WheelSlot.objects.filter(active=True).exclude(pk=pk).aggregate(n=Sum("count"))["n"] or 0
                    if form.cleaned_data["active"] and total + form.cleaned_data["count"] > 24:
                        raise ValidationError("La ruleta admite hasta 24 casillas activas en total.")
                obj = form.save()
                services.audit(None, f"{kind}_saved", {"id": obj.pk}, request.user)
            return redirect(f"/juegos/gestion/?tab={'questions' if kind == 'question' else 'wheel'}")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "games/form.html", context(form=form, form_title="Pregunta" if kind == "question" else "Casilla de ruleta", submit_label="Guardar"))


@manager_only
@require_POST
def delete(request, kind, pk):
    if kind not in ("question", "slot"):
        raise PermissionDenied
    with transaction.atomic():
        services.lock_wheel()
        obj = get_object_or_404(Question if kind == "question" else WheelSlot, pk=pk)
        if kind == "slot":
            obj.active = False
            obj.save(update_fields=["active"])
            services.audit(None, "slot_archived", {"id": pk}, request.user)
            messages.info(request, "Casilla archivada. Su historial se conserva.")
            return redirect("/juegos/gestion/?tab=wheel")
        try:
            with transaction.atomic():
                obj.delete()
        except ProtectedError:
            obj.active = False
            obj.save(update_fields=["active"])
            messages.info(request, "La casilla se archivó para conservar su historial.")
        services.audit(None, f"{kind}_deleted", {"id": pk}, request.user)
    return redirect(f"/juegos/gestion/?tab={'questions' if kind == 'question' else 'wheel'}")


@manager_only
def import_questions(request):
    form = ImportForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            raw = form.cleaned_data["file"].read().decode("utf-8-sig") if form.cleaned_data.get("file") else form.cleaned_data["payload"]
            payload = json.loads(raw)
            rows = payload.get("questions") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                raise ValidationError("Se espera un objeto con una lista questions de 1 a 500 preguntas.")
            objects = []
            for index, row in enumerate(rows):
                if (not isinstance(row, dict) or set(row) - {"text", "options", "correct", "difficulty", "active"}
                        or not {"text", "options", "correct", "difficulty"} <= set(row)
                        or type(row.get("correct")) is not int or type(row.get("difficulty")) is not int
                        or ("active" in row and type(row["active"]) is not bool)):
                    raise ValidationError(f"Pregunta {index + 1}: estructura o tipos inválidos.")
                obj = Question(**row)
                obj.full_clean()
                objects.append(obj)
            with transaction.atomic():
                services.lock_wheel()
                Question.objects.bulk_create(objects)
                services.audit(None, "questions_imported", {"count": len(objects)}, request.user)
            messages.success(request, f"Se importaron {len(objects)} preguntas.")
            return redirect("games:dashboard")
        except (ValueError, UnicodeDecodeError, ValidationError) as error:
            form.add_error(None, " ".join(error.messages) if isinstance(error, ValidationError) else "JSON inválido; usá UTF-8.")
    return render(request, "games/import.html", context(form=form))


@manager_only
@require_GET
def export_questions(request):
    response = JsonResponse({"questions": list(Question.objects.order_by("pk").values("text", "options", "correct", "difficulty", "active"))}, json_dumps_params={"ensure_ascii": False, "indent": 2})
    timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="preguntas-{timestamp}.json"'
    return response


@manager_only
def user_detail(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    form = GrantForm(request.POST if request.method == "POST" else None, initial={"key": uuid.uuid4(), "amount": 1})
    if request.method == "POST" and form.is_valid():
        try:
            reward = form.cleaned_data.get("reward") or "spin"
            services.grant(request.user, user, form.cleaned_data["amount"], form.cleaned_data["reason"], form.cleaned_data["key"], reward=reward)
            messages.success(request, "Trivias adicionales otorgadas." if reward == "attempt" else "Tiradas adicionales otorgadas.")
            return redirect("games:user", pk=pk)
        except ValidationError as error:
            form.add_error(None, error)
    history = {
        "events": GameEvent.objects.filter(user=user).select_related("actor"),
        "runs": TriviaRun.objects.filter(user=user).prefetch_related("answers"),
        "spins": WheelSpin.objects.filter(user=user),
        "coupons": PrizeCoupon.objects.filter(user=user).select_related("redeemed_by"),
    }
    tab = request.GET.get("tab", "coupons")
    if tab not in history:
        tab = "coupons"
    account, _ = GameAccount.objects.get_or_create(user=user)
    return render(request, "games/user.html", context(target=user, account=account, form=form, tab=tab,
        daily_ready=account.next_daily_at is None or account.next_daily_at <= timezone.now(),
        available_prizes=history["coupons"].filter(status="available").count(),
        requested_prizes=history["coupons"].filter(status="requested").count(),
        redeemed_prizes=history["coupons"].filter(status="redeemed").count(),
        rows=Paginator(history[tab], 20).get_page(request.GET.get("page"))))
