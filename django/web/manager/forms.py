from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import json

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.seat_types.models import SeatType

User = get_user_model()
MAX_MOVIE_IMAGE_SIZE_MB = 2
MAX_MOVIE_IMAGE_SIZE_BYTES = MAX_MOVIE_IMAGE_SIZE_MB * 1024 * 1024


class CinemaSettingsForm(forms.ModelForm):
    seat_reservation_minutes = forms.IntegerField(
        min_value=1,
        label="Reserva temporal de butacas (minutos)",
        help_text="Tiempo durante el checkout antes de liberar butacas no confirmadas.",
    )
    seat_refresh_seconds = forms.IntegerField(
        min_value=1,
        label="Recarga automática de butacas (segundos)",
        help_text="Frecuencia con la que el cliente vuelve a consultar disponibilidad.",
    )

    class Meta:
        model = CinemaSettings
        fields = ("seat_reservation_minutes", "seat_refresh_seconds")


class UserManagementForm(forms.ModelForm):
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
        users = User.objects.exclude(pk=self.instance.pk)
        if users.filter(username__iexact=email).exists() or users.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError("Ya existe un usuario con ese email.")
        return email


class RoomForm(forms.ModelForm):

    MAX_ROW, MAX_COLUMN = 100,100

    room_layout = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_room_layout"}),
    )
    class Meta:
        model = Room
        fields = ("name", "room_layout")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound or not self.instance.pk:
            return

        seats = list(
            Seat.objects.filter(room=self.instance)
            .select_related("seat_type")
            .order_by("row", "column")
        )
        if self.instance.layout_configuration:
            self.initial["room_layout"] = json.dumps(
                self._normalize_initial_layout(self.instance.layout_configuration, seats)
            )
            return

        if seats:
            self.initial["room_layout"] = json.dumps(self._layout_from_seats(seats))

    def _layout_from_seats(self, seats):
        return {
            "rows": max(seat.row for seat in seats) + 1,
            "columns": max(seat.column for seat in seats) + 1,
            "seats": [
                {
                    "row": seat.row,
                    "column": seat.column,
                    "type": seat.seat_type.name,
                }
                for seat in seats
            ],
        }

    def _normalize_initial_layout(self, layout, seats):
        if not isinstance(layout, dict):
            return self._layout_from_seats(seats) if seats else {}

        seats_by_position = {(seat.row, seat.column): seat for seat in seats}
        seat_type_names = set(SeatType.objects.values_list("name", flat=True))
        seat_type_names_by_id = {
            str(pk): name
            for pk, name in SeatType.objects.values_list("pk", "name")
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
                seat_type_name = seats_by_position[(row, column)].seat_type.name

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

    def clean_room_layout(self):
        data_as_string = self.cleaned_data.get("room_layout")
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
        exsisting_seat_types = dict(SeatType.objects.values_list("name", "pk"))

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
        room_layout = cleaned_data.get("room_layout")

        if room_layout and room_layout["seats"]:
            cleaned_data["layout_configuration"] = room_layout["display"]
        elif room_layout:
            self.add_error("room_layout", "Dibujá al menos un asiento.")
        else:
            self.add_error("room_layout", "DibujÃ¡ al menos un asiento.")

        return cleaned_data


class MovieForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = (
            "title",
            "synopsis",
            "genre",
            "rating",
            "duration_minutes",
            "image",
        )
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {
            "image": f"Peso maximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and getattr(image, "size", 0) > MAX_MOVIE_IMAGE_SIZE_BYTES:
            raise forms.ValidationError(
                f"La imagen no puede superar los {MAX_MOVIE_IMAGE_SIZE_MB} MB."
            )
        return image


class SeatTypeForm(forms.ModelForm):
    class Meta:
        model = SeatType
        fields = ("name", "base_price", "color", "icon")
        labels = {
            "name": "Nombre",
            "base_price": "Precio",
            "color": "Color",
            "icon": "Icono",
        }
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "icon": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price <= 0:
            raise forms.ValidationError("El precio debe ser mayor a cero.")
        return price


class ScreeningForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    class Meta:
        model = Screening
        fields = ("movie", "room", "starts_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["movie"].empty_label = "Seleccioná una película"
        self.fields["room"].empty_label = "Seleccioná una sala"
        if self.instance.pk:
            self.fields["room"].disabled = True
            self.fields["room"].help_text = (
                "La sala queda bloqueada al crear la función para conservar la configuración de butacas publicada."
            )
            self.fields["room"].widget.attrs.update({
                "class": "is-locked-field",
                "data-locked": "true",
            })
    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("La fecha y horario deben ser futuros.")
        return starts_at

    def clean(self):
        cleaned_data = super().clean()
        room = cleaned_data.get("room")
        if not room:
            return cleaned_data

        required_type_ids = set(
            str(type_id)
            for type_id in Seat.objects.filter(room=room)
            .values_list("seat_type_id", flat=True)
            .distinct()
        )
        if not required_type_ids:
            required_type_ids = set(str(pk) for pk in SeatType.objects.values_list("pk", flat=True))

        base_prices = {
            str(pk): str(price)
            for pk, price in SeatType.objects.values_list("pk", "base_price")
        }
        completed_prices = {}
        missing = []
        for type_id in required_type_ids:
            price = base_prices.get(type_id)
            if price is None:
                missing.append(type_id)
            else:
                completed_prices[type_id] = str(Decimal(str(price)))

        if missing:
            raise forms.ValidationError("Indica el precio para cada tipo de butaca.")

        cleaned_data["prices_by_type"] = completed_prices
        cleaned_data["ticket_price"] = min(Decimal(str(price)) for price in completed_prices.values())
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        prices = self.cleaned_data.get("prices_by_type") or {}
        instance.prices_by_type = prices
        if prices:
            instance.ticket_price = min(Decimal(str(price)) for price in prices.values())
        if commit:
            instance.save()
            self.save_m2m()
        return instance
