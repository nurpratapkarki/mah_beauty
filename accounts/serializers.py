from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from allauth.account.utils import user_pk_to_url_str
from dj_rest_auth.forms import AllAuthPasswordResetForm
from dj_rest_auth.registration.serializers import (
    RegisterSerializer as DJRegisterSerializer,
)
from dj_rest_auth.serializers import (
    LoginSerializer as DJLoginSerializer,
)
from dj_rest_auth.serializers import (
    PasswordResetSerializer as DJPasswordResetSerializer,
)
from dj_rest_auth.serializers import (
    UserDetailsSerializer as DJUserDetailsSerializer,
)

from accounts.validators import normalize_phone

UserModel = get_user_model()

_DUMMY_EMAIL = 'noaccount@invalid.local'


class LoginSerializer(serializers.Serializer):
    """Single-identifier login: username | email | phone + password (FR-001/FR-002)."""

    username = serializers.CharField(
        help_text=_('Username, email address, or phone number.'),
    )
    password = serializers.CharField(
        style={'input_type': 'password'},
        trim_whitespace=False,
    )

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            username=attrs.get('username'),
            password=attrs.get('password'),
        )
        if not user:
            raise serializers.ValidationError(
                _('Unable to log in with provided credentials.'),
            )
        attrs['user'] = user
        return attrs


class RegisterSerializer(DJRegisterSerializer):
    """Registration with an optional, normalized phone_number (FR-003/FR-004)."""

    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text=_('Phone number, normalized to E.164, e.g. +9779811000000.'),
    )

    def validate_email(self, email):
        email = super().validate_email(email)
        if UserModel.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                _('User is already registered with this e-mail address.'),
            )
        return email

    def validate_phone_number(self, value):
        if value in (None, ''):
            return None
        phone = normalize_phone(value)
        if phone is None:
            raise serializers.ValidationError(_('Enter a valid phone number.'))
        if UserModel.objects.filter(phone_number__iexact=phone).exists():
            raise serializers.ValidationError(
                _('A user with that phone number already exists.'),
            )
        return phone

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data['phone_number'] = self.validated_data.get('phone_number')
        return data

    def custom_signup(self, request, user):
        phone = self.validated_data.get('phone_number')
        if phone:
            user.phone_number = phone
            user.save(update_fields=['phone_number'])


class UserDetailsSerializer(DJUserDetailsSerializer):
    """Exact ``User`` shape for the frontend schema (FR-014); no password fields."""

    # Declared explicitly so the raw model-field E.164 regex validator does not
    # reject un-normalized input before validate_phone_number runs.
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[],
        help_text=_('Phone number, normalized to E.164, e.g. +9779811000000.'),
    )

    class Meta(DJUserDetailsSerializer.Meta):
        model = UserModel
        fields = (
            'id',
            'username',
            'email',
            'phone_number',
            'first_name',
            'last_name',
        )
        read_only_fields = ('id',)

    def validate_email(self, value):
        email = str(value).strip().lower()
        if UserModel.objects.exclude(pk=self.instance.pk).filter(
            email__iexact=email,
        ).exists():
            raise serializers.ValidationError(
                _('A user with that email already exists.'),
            )
        return email

    def validate_phone_number(self, value):
        if value in (None, ''):
            return None
        phone = normalize_phone(value)
        if phone is None:
            raise serializers.ValidationError(_('Enter a valid phone number.'))
        if UserModel.objects.exclude(pk=self.instance.pk).filter(
            phone_number__iexact=phone,
        ).exists():
            raise serializers.ValidationError(
                _('A user with that phone number already exists.'),
            )
        return phone


class PasswordResetSerializer(DJPasswordResetSerializer):
    """Reset request accepts email **or** phone; never reveals existence (FR-010)."""

    email = serializers.CharField(
        help_text=_('Email address or phone number.'),
    )
    password_reset_form_class = AllAuthPasswordResetForm

    def get_email_options(self):
        """Deliver a link to the SPA reset page rather than an API route.

        allauth's default generator reverses ``account_reset_password_from_key``,
        which is not mounted in this API-only project.
        """
        base = getattr(settings, 'SPA_PASSWORD_RESET_URL', '')

        def url_generator(request, user, temp_key):
            return f'{base}/{user_pk_to_url_str(user)}/{temp_key}'

        return {'url_generator': url_generator}

    def validate_email(self, value):
        identifier = (value or '').strip()
        account_email = self._resolve_account_email(identifier)
        self.reset_form = self.password_reset_form_class(
            data={'email': account_email},
        )
        if not self.reset_form.is_valid():
            raise serializers.ValidationError(self.reset_form.errors)
        return value

    def _resolve_account_email(self, value):
        """Return the account email to mail, or a non-resolving dummy address.

        Every un-resolvable identifier maps to the same dummy so the response
        body is byte-for-byte identical for known/unknown input (no enumeration).
        """
        if not value:
            return _DUMMY_EMAIL

        phone = normalize_phone(value)
        if phone:
            user = UserModel.objects.filter(phone_number__iexact=phone).first()
            if user and user.email:
                return user.email
            return _DUMMY_EMAIL

        candidate = value.strip().lower()
        try:
            validate_email(candidate)
        except DjangoValidationError:
            return _DUMMY_EMAIL
        return candidate