from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from accounts.models import User


@admin.register(User)
class AccountsUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (_('Profile'), {'fields': ('phone_number',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_('Profile'), {'fields': ('phone_number', 'email')}),
    )
    list_display = ('username', 'email', 'phone_number', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'phone_number')
    ordering = ('username',)