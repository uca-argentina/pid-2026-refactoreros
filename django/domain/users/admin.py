from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import AdminUsuarioChangeForm, AdminUsuarioCreationForm
from .models import Acomodador, Cliente, Gerente

User = get_user_model()


class ClienteInline(admin.StackedInline):
    model = Cliente
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("id_cliente",)


class AcomodadorInline(admin.StackedInline):
    model = Acomodador
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("id_acomodador",)


class GerenteInline(admin.StackedInline):
    model = Gerente
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("id_gerente",)


class UserAdmin(DjangoUserAdmin):
    form = AdminUsuarioChangeForm
    add_form = AdminUsuarioCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    inlines = (ClienteInline, AcomodadorInline, GerenteInline)


try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, UserAdmin)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("id_cliente", "usuario", "email", "is_active")
    search_fields = (
        "usuario__username",
        "usuario__email",
        "usuario__first_name",
        "usuario__last_name",
    )
    list_select_related = ("usuario",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.usuario.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.usuario.is_active


@admin.register(Acomodador)
class AcomodadorAdmin(admin.ModelAdmin):
    list_display = ("id_acomodador", "usuario", "email", "is_active")
    search_fields = (
        "usuario__username",
        "usuario__email",
        "usuario__first_name",
        "usuario__last_name",
    )
    list_select_related = ("usuario",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.usuario.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.usuario.is_active


@admin.register(Gerente)
class GerenteAdmin(admin.ModelAdmin):
    list_display = ("id_gerente", "usuario", "email", "is_active")
    search_fields = (
        "usuario__username",
        "usuario__email",
        "usuario__first_name",
        "usuario__last_name",
    )
    list_select_related = ("usuario",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.usuario.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.usuario.is_active
