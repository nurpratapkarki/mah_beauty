from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView


class GoogleLogin(SocialLoginView):
    """Google Identity Services login/signup (access-token variant, FR-006–FR-009)."""

    adapter_class = GoogleOAuth2Adapter
    callback_url = None