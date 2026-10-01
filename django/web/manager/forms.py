from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import json

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion
from domain.seats.models import Seat
from domain.seat_types.models import SeatType

User = get_user_model()
MAX_MOVIE_IMAGE_SIZE_MB = 2
MAX_MOVIE_IMAGE_SIZE_BYTES = MAX_MOVIE_IMAGE_SIZE_MB * 1024 * 1024


class UsuarioGestionForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Email",
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("El email es obligatorio.")
        usuarios = User.objects.exclude(pk=self.instance.pk)
        if usuarios.filter(username__iexact=email).exists() or usuarios.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError("Ya existe un usuario con ese email.")
        return email


class SalaForm(forms.ModelForm):

    MAX_ROW, MAX_COLUMN = 100,100

    capacidad = forms.IntegerField(
        min_value=1,
        required=False,
        widget=forms.HiddenInput(),
    )
    layout_sala = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_layout_sala"}),
    )
    precio_configuracion = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_precio_configuracion"}),
    )

    class Meta:
        model = Sala
        fields = ("nombre", "capacidad", "precio_configuracion")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound or not self.instance.pk:
            return

        seats = list(
            Seat.objects.filter(sala=self.instance)
            .select_related("tipo")
            .order_by("fila", "columna")
        )
        if self.instance.precio_configuracion:
            self.initial["precio_configuracion"] = json.dumps(self.instance.precio_configuracion)

        if self.instance.layout_configuracion:
            self.initial["layout_sala"] = json.dumps(
                self._normalize_initial_layout(self.instance.layout_configuracion, seats)
            )
            return

        if seats:
            self.initial["layout_sala"] = json.dumps(self._layout_from_seats(seats))

    def _layout_from_seats(self, seats):
        return {
            "rows": max(seat.fila for seat in seats) + 1,
            "columns": max(seat.columna for seat in seats) + 1,
            "seats": [
                {
                    "row": seat.fila,
                    "column": seat.columna,
                    "type": seat.tipo.nombre,
                }
                for seat in seats
            ],
        }

    def _normalize_initial_layout(self, layout, seats):
        if not isinstance(layout, dict):
            return self._layout_from_seats(seats) if seats else {}

        seats_by_position = {(seat.fila, seat.columna): seat for seat in seats}
        seat_type_names = set(SeatType.objects.values_list("nombre", flat=True))
        seat_type_names_by_id = {
            str(pk): name
            for pk, name in SeatType.objects.values_list("pk", "nombre")
        }

        normalized_seats = []
        for seat_data in layout.get("seats", []):
            try:
                row = self._to_int(seat_data["row"])
                column = self._to_int(seat_data["column"])
            except (KeyError, TypeError, ValueError):
                continue

            seat_type = seat_data.get("type")
            seat_type_name = None
            if seat_type in seat_type_names:
                seat_type_name = seat_type
            elif str(seat_type) in seat_type_names_by_id:
                seat_type_name = seat_type_names_by_id[str(seat_type)]
            elif str(seat_data.get("type_id")) in seat_type_names_by_id:
                seat_type_name = seat_type_names_by_id[str(seat_data.get("type_id"))]
            elif (row, column) in seats_by_position:
                seat_type_name = seats_by_position[(row, column)].tipo.nombre

            if seat_type_name:
                normalized_seats.append({"row": row, "column": column, "type": seat_type_name})

        if not normalized_seats and seats:
            return self._layout_from_seats(seats)

        inferred_rows = max((seat["row"] for seat in normalized_seats), default=-1) + 1
        inferred_columns = max((seat["column"] for seat in normalized_seats), default=-1) + 1
        try:
            rows = self._to_int(layout.get("rows") or inferred_rows)
            columns = self._to_int(layout.get("columns") or inferred_columns)
        except (TypeError, ValueError):
            rows = inferred_rows
            columns = inferred_columns
        rows = max(rows, inferred_rows, 1)
        columns = max(columns, inferred_columns, 1)

        return {
            "rows": rows,
            "columns": columns,
            "seats": normalized_seats,
        }

    def _to_int(self,value):
        return int(value)

    def _parse_price_map(self, value):
        if not value:
            return {}
        try:
            data = json.loads(value)
        except ValueError:
            raise forms.ValidationError("La configuración de precios no es válida.")
        if not isinstance(data, dict):
            raise forms.ValidationError("La configuración de precios no es válida.")

        valid_type_ids = set(str(pk) for pk in SeatType.objects.values_list("pk", flat=True))
        prices = {}
        for type_id, price in data.items():
            if str(type_id) not in valid_type_ids:
                continue
            try:
                normalized_price = Decimal(str(price))
            except (InvalidOperation, TypeError, ValueError):
                raise forms.ValidationError("Los precios deben ser numéricos.")
            if normalized_price <= 0:
                raise forms.ValidationError("Todos los precios deben ser mayores a cero.")
            prices[str(type_id)] = str(normalized_price)
        return prices

    def clean_precio_configuracion(self):
        return self._parse_price_map(self.cleaned_data.get("precio_configuracion"))
    
    def clean_layout_sala(self):
        data_as_string = self.cleaned_data.get("layout_sala")
        if not data_as_string:
            return []

        try:
            data = json.loads(data_as_string)
        except ValueError:
            raise forms.ValidationError("El plano enviado no es válido.")

        rows = None
        columns = None
        if isinstance(data, dict):
            try:
                rows = self._to_int(data.get("rows", 0))
                columns = self._to_int(data.get("columns", 0))
            except (TypeError, ValueError):
                raise forms.ValidationError("El tamaño del plano contiene datos incorrectos.")
            data = data.get("seats", [])

        if rows is not None and (rows < 1 or rows > self.MAX_ROW):
            raise forms.ValidationError(f"La cantidad de filas debe estar entre 1 y {self.MAX_ROW}.")
        if columns is not None and (columns < 1 or columns > self.MAX_COLUMN):
            raise forms.ValidationError(f"La cantidad de asientos por fila debe estar entre 1 y {self.MAX_COLUMN}.")

        if not isinstance(data, list):
            raise forms.ValidationError("Dibujá al menos un asiento.")
        if len(data) > (self.MAX_ROW*self.MAX_COLUMN):
            raise forms.ValidationError(f"Máximo {self.MAX_ROW*self.MAX_COLUMN} asientos por sala.")

        seats_data, display_seats_data, positions = [] , [] , set()
        exsisting_seat_types = dict(SeatType.objects.values_list("nombre", "pk"))

        for seat_data in data:
            try:
                row,column = self._to_int(seat_data["row"]) , self._to_int(seat_data["column"])
                seat_type  = seat_data["type"]
            except(KeyError, TypeError,ValueError):
                raise forms.ValidationError(f"El plano de la sala contiene datos incorrectos.")

            if(row < 0 or column < 0 or row > self.MAX_ROW or column > self.MAX_COLUMN):
                raise forms.ValidationError(f"Hay asientos fuera del limite (máximo de filas {self.MAX_ROW} y máximo de columnas {self.MAX_COLUMN}).")

            if((row,column) in positions):
                raise forms.ValidationError("Hay asientos duplicados.")

            if(seat_type not in exsisting_seat_types):
                raise forms.ValidationError(f"No existen asientos de tipo {seat_type}.")
            
            positions.add((row,column))
            seats_data.append({"row":row,"column":column,"type":exsisting_seat_types[seat_type]})
            display_seats_data.append({"row": row, "column": column, "type": seat_type})

        inferred_rows = max((seat["row"] for seat in seats_data), default=-1) + 1
        inferred_columns = max((seat["column"] for seat in seats_data), default=-1) + 1
        rows = rows or inferred_rows
        columns = columns or inferred_columns

        if any(seat["row"] >= rows or seat["column"] >= columns for seat in seats_data):
            raise forms.ValidationError("Hay asientos fuera del tamaño declarado para la sala.")

        return {
            "rows": rows,
            "columns": columns,
            "seats": seats_data,
            "display": {
                "rows": rows,
                "columns": columns,
                "seats": display_seats_data,
            },
        }

    def clean(self):
        cleaned_data = super().clean()
        layout_sala = cleaned_data.get("layout_sala")
        capacidad = cleaned_data.get("capacidad")

        if layout_sala and layout_sala["seats"]:
            cleaned_data["capacidad"] = len(layout_sala["seats"])
            cleaned_data["layout_configuracion"] = layout_sala["display"]
        elif layout_sala:
            self.add_error("layout_sala", "Dibujá al menos un asiento.")
        elif capacidad is None:
            self.add_error("capacidad", "Indica la capacidad o dibuja al menos un asiento.")

        return cleaned_data


class PeliculaForm(forms.ModelForm):
    class Meta:
        model = Pelicula
        fields = (
            "titulo",
            "sinopsis",
            "genero",
            "clasificacion",
            "duracion_minutos",
            "imagen",
        )
        widgets = {
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {
            "imagen": f"Peso maximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if imagen and getattr(imagen, "size", 0) > MAX_MOVIE_IMAGE_SIZE_BYTES:
            raise forms.ValidationError(
                f"La imagen no puede superar los {MAX_MOVIE_IMAGE_SIZE_MB} MB."
            )
        return imagen


class FuncionForm(forms.ModelForm):
    fecha_horario = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    precios_por_tipo = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_precios_por_tipo"}),
    )

    class Meta:
        model = Funcion
        fields = ("pelicula", "sala", "fecha_horario", "precios_por_tipo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pelicula"].empty_label = "Seleccioná una película"
        self.fields["sala"].empty_label = "Seleccioná una sala"
        if self.instance.pk:
            self.fields["sala"].disabled = True
            self.fields["sala"].help_text = (
                "La sala queda bloqueada al crear la función para conservar la configuración de butacas publicada."
            )
            self.fields["sala"].widget.attrs.update({
                "class": "is-locked-field",
                "data-locked": "true",
            })
        if self.instance.pk and self.instance.precios_por_tipo:
            self.initial["precios_por_tipo"] = json.dumps(self.instance.precios_por_tipo)

    def clean_fecha_horario(self):
        fecha_horario = self.cleaned_data["fecha_horario"]
        if fecha_horario <= timezone.now():
            raise forms.ValidationError("La fecha y horario deben ser futuros.")
        return fecha_horario

    def clean_precios_por_tipo(self):
        value = self.cleaned_data.get("precios_por_tipo")
        if not value:
            return {}
        try:
            data = json.loads(value)
        except ValueError:
            raise forms.ValidationError("La configuración de precios no es válida.")
        if not isinstance(data, dict):
            raise forms.ValidationError("La configuración de precios no es válida.")
        prices = {}
        for type_id, price in data.items():
            try:
                normalized_price = Decimal(str(price))
            except (InvalidOperation, TypeError, ValueError):
                raise forms.ValidationError("Los precios deben ser numéricos.")
            if normalized_price <= 0:
                raise forms.ValidationError("Todos los precios deben ser mayores a cero.")
            prices[str(type_id)] = str(normalized_price)
        return prices

    def clean(self):
        cleaned_data = super().clean()
        sala = cleaned_data.get("sala")
        prices = cleaned_data.get("precios_por_tipo") or {}
        if not sala:
            return cleaned_data

        required_type_ids = set(
            str(type_id)
            for type_id in Seat.objects.filter(sala=sala)
            .values_list("tipo_id", flat=True)
            .distinct()
        )
        if not required_type_ids:
            required_type_ids = set(str(pk) for pk in SeatType.objects.values_list("pk", flat=True))

        fallback_prices = {
            str(type_id): str(price)
            for type_id, price in (sala.precio_configuracion or {}).items()
        }
        base_prices = {
            str(pk): str(price)
            for pk, price in SeatType.objects.values_list("pk", "precio_base")
        }
        completed_prices = {}
        missing = []
        for type_id in required_type_ids:
            price = prices.get(type_id) or fallback_prices.get(type_id) or base_prices.get(type_id)
            if price is None:
                missing.append(type_id)
            else:
                completed_prices[type_id] = str(Decimal(str(price)))

        if missing:
            self.add_error("precios_por_tipo", "Indicá el precio para cada tipo de asiento de la sala.")
            return cleaned_data

        cleaned_data["precios_por_tipo"] = completed_prices
        cleaned_data["precio_entrada"] = min(Decimal(str(price)) for price in completed_prices.values())
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        prices = self.cleaned_data.get("precios_por_tipo") or {}
        instance.precios_por_tipo = prices
        if prices:
            instance.precio_entrada = min(Decimal(str(price)) for price in prices.values())
        if commit:
            instance.save()
            self.save_m2m()
        return instance
