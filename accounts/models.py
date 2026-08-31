from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.validators import E164RegexValidator, normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The email address must be set.'))
        email = self.normalize_email(email)
        phone = extra_fields.pop('phone_number', None)
        if phone:
            extra_fields['phone_number'] = normalize_phone(phone)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(
        _('email address'),
        unique=True,
        blank=False,
    )
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        validators=[E164RegexValidator()],
        help_text=_('Normalized E.164 form, e.g. +9779811000000.'),
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'phone_number']

    objects = UserManager()

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self):
        return self.username