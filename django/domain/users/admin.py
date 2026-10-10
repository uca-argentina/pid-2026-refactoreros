from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import Usher, Customer, Manager

User = get_user_model()


class CustomerInline(admin.StackedInline):
    model = Customer
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("customer_id",)


class UsherInline(admin.StackedInline):
    model = Usher
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("usher_id",)


class ManagerInline(admin.StackedInline):
    model = Manager
    extra = 1
    max_num = 1
    can_delete = True
    readonly_fields = ("manager_id",)


class UserAdmin(DjangoUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    inlines = (CustomerInline, UsherInline, ManagerInline)


try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, UserAdmin)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_id", "user", "email", "is_active")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    list_select_related = ("user",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.user.is_active


@admin.register(Usher)
class UsherAdmin(admin.ModelAdmin):
    list_display = ("usher_id", "user", "email", "is_active")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    list_select_related = ("user",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.user.is_active


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("manager_id", "user", "email", "is_active")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    list_select_related = ("user",)

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Activo", boolean=True)
    def is_active(self, obj):
        return obj.user.is_active
