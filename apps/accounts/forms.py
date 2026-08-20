from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import Profile, UserPreference, Interest

User = get_user_model()

class UserRegisterForm(forms.ModelForm):
    """
    Standard registration form with password confirmation and optional interest selection.
    """
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': '••••••••', 'autocomplete': 'new-password'}),
        min_length=8
    )
    confirm_password = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': '••••••••', 'autocomplete': 'new-password'}),
        min_length=8
    )
    display_name = forms.CharField(
        label=_('Display Name'),
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('Your Name')})
    )
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'display_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('username')}),
            'email': forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'you@example.com'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', _('Passwords do not match.'))
        return cleaned_data


class UserLoginForm(AuthenticationForm):
    """
    User login form with styled inputs.
    """
    username = forms.CharField(
        label=_('Username or Email'),
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('username or email'), 'autofocus': True})
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': '••••••••'})
    )


class ProfileEditForm(forms.ModelForm):
    """
    Profile update form for avatar, bio, interests, location and presence preferences.
    """
    class Meta:
        model = Profile
        fields = ['display_name', 'avatar', 'avatar_preset', 'interests', 'bio', 'gender', 'date_of_birth', 'location_name', 'show_online_status', 'allow_random_chat']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('Public Display Name')}),
            'avatar_preset': forms.HiddenInput(),
            'interests': forms.CheckboxSelectMultiple(),
            'bio': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': _('Tell others about yourself...')}),
            'gender': forms.Select(attrs={'class': 'input-field select-field'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'input-field', 'type': 'date'}),
            'location_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('e.g. Mumbai, New Delhi, Bengaluru')}),
            'show_online_status': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
            'allow_random_chat': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
        }


class UserPreferenceForm(forms.ModelForm):
    """
    User settings / preferences form.
    """
    class Meta:
        model = UserPreference
        fields = ['language', 'sound_enabled', 'notifications_enabled', 'email_notifications', 'dark_mode']
        widgets = {
            'language': forms.Select(attrs={'class': 'input-field select-field'}),
            'sound_enabled': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
            'notifications_enabled': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
            'dark_mode': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
        }
