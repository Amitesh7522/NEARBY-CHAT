from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
import re
from .models import Profile, UserPreference, Interest, PRESET_AVATARS
from .services import VerificationService

User = get_user_model()

class AccountRegisterForm(forms.Form):
    """
    Step 1 Registration Form:
    Asks for Name, Email Address, 6-digit OTP, and Password.
    Production-ready with strict validation and normalization.
    """
    name = forms.CharField(
        label=_('Your Name'),
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': _('e.g. Alex Sharma'),
            'autocomplete': 'name',
            'id': 'id_name',
        })
    )
    email = forms.EmailField(
        label=_('Email Address'),
        required=False,  # Checked in clean() to support legacy identifier
        widget=forms.EmailInput(attrs={
            'class': 'input-field',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
            'autocapitalize': 'none',
            'autocorrect': 'off',
            'spellcheck': 'false',
            'id': 'id_email',
        })
    )
    identifier = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    auth_type = forms.CharField(
        required=False,
        initial='email',
        widget=forms.HiddenInput()
    )
    otp = forms.CharField(
        label=_('Verification Code (OTP)'),
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'input-field text-center font-mono',
            'placeholder': '••••••',
            'maxlength': '6',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'id': 'id_otp',
        })
    )
    password = forms.CharField(
        label=_('Create Password'),
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'input-field',
            'placeholder': _('At least 8 characters'),
            'autocomplete': 'new-password',
            'id': 'id_password',
        })
    )
    confirm_password = forms.CharField(
        label=_('Confirm Password'),
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'input-field',
            'placeholder': _('Re-enter password'),
            'autocomplete': 'new-password',
            'id': 'id_confirm_password',
        })
    )

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_('Please enter your name.'))
        if len(name) < 2:
            raise forms.ValidationError(_('Name must be at least 2 characters.'))
        return name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            # Fallback to identifier if supplied
            ident = self.data.get('identifier', '').strip().lower()
            if ident and '@' in ident:
                email = ident

        if not email:
            raise forms.ValidationError(_('Please enter your email address.'))

        if not re.match(r'^[\w\.\+\-]+@[\w\.\-]+\.\w+$', email):
            raise forms.ValidationError(_('Please enter a valid email address.'))

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('An account with this email already exists.'))

        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        email = cleaned_data.get('email') or self.data.get('identifier', '').strip().lower()
        otp = cleaned_data.get('otp')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', _('Passwords do not match.'))

        # Real OTP backend verification
        if email and otp:
            is_valid, err_msg = VerificationService.verify_otp_challenge(email, otp, purpose='signup')
            if not is_valid:
                self.add_error('otp', err_msg)

        return cleaned_data


# Alias for backwards compatibility
UserRegisterForm = AccountRegisterForm


class OnboardingProfileForm(forms.ModelForm):
    """
    Step 2 Optional Profile Setup Form:
    Allows user to personalize Name, Avatar, Gender, and Interests (Max 5).
    """
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = Profile
        fields = ['display_name', 'avatar', 'avatar_preset', 'gender', 'interests']
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'input-field',
                'placeholder': _('e.g. Alex, Rahul, Maya'),
                'maxlength': '60'
            }),
            'avatar_preset': forms.HiddenInput(),
            'gender': forms.RadioSelect(choices=Profile.GENDER_CHOICES),
        }

    def clean_interests(self):
        interests = self.cleaned_data.get('interests')
        if interests and len(interests) > 5:
            raise forms.ValidationError(_('You can select a maximum of 5 interests.'))
        return interests


class UserLoginForm(AuthenticationForm):
    """
    User login form supporting Email or Username.
    """
    username = forms.CharField(
        label=_('Email or Username'),
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': _('Enter your email or username'),
            'autofocus': True,
            'autocomplete': 'username',
            'autocapitalize': 'none',
            'autocorrect': 'off',
            'spellcheck': 'false',
            'id': 'id_username',
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'input-field',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
            'id': 'id_password',
        })
    )


class ProfileEditForm(forms.ModelForm):
    """
    Profile update form for avatar, bio, interests, location and presence preferences.
    """
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = Profile
        fields = [
            'display_name', 'avatar', 'avatar_preset', 'interests', 'bio',
            'gender', 'date_of_birth', 'location_name', 'show_online_status',
            'allow_random_chat'
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('Public Display Name')}),
            'avatar_preset': forms.HiddenInput(),
            'bio': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': _('Tell others about yourself...')}),
            'gender': forms.Select(attrs={'class': 'input-field select-field'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'input-field', 'type': 'date'}),
            'location_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('e.g. Mumbai, New Delhi, Bengaluru')}),
            'show_online_status': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
            'allow_random_chat': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
        }

    def clean_interests(self):
        interests = self.cleaned_data.get('interests')
        if interests and len(interests) > 5:
            raise forms.ValidationError(_('You can select a maximum of 5 interests.'))
        return interests

    def save(self, commit=True):
        profile = super().save(commit=False)
        # If user changed their display name, mark that they no longer have a temporary name
        if profile.display_name and not profile.display_name.startswith('User '):
            profile.is_temporary_name = False
        elif profile.display_name and profile.is_temporary_name:
            profile.is_temporary_name = False
        if commit:
            profile.save()
            self.save_m2m()
        return profile


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
