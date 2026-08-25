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
    Asks ONLY for authentication details (Email or Phone + OTP + Password).
    No profile information is asked at this stage.
    """
    AUTH_TYPE_CHOICES = [
        ('email', _('Email Address')),
        ('phone', _('Phone Number')),
    ]

    auth_type = forms.ChoiceField(
        choices=AUTH_TYPE_CHOICES,
        initial='email',
        widget=forms.HiddenInput()
    )
    identifier = forms.CharField(
        label=_('Email or Phone Number'),
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': _('Enter email address or mobile number'),
            'autocomplete': 'username',
            'id': 'id_identifier',
        })
    )
    otp = forms.CharField(
        label=_('Verification Code (OTP)'),
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'input-field text-center font-mono',
            'placeholder': '123456',
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

    def clean_identifier(self):
        ident = self.cleaned_data.get('identifier', '').strip()
        auth_type = self.cleaned_data.get('auth_type', 'email')

        if not ident:
            raise forms.ValidationError(_('Please enter your email or phone number.'))

        if '@' in ident or auth_type == 'email':
            # Email validation
            ident_clean = ident.lower()
            if not re.match(r'^[\w\.\+\-]+@[\w\.\-]+\.\w+$', ident_clean):
                raise forms.ValidationError(_('Please enter a valid email address.'))
            if User.objects.filter(email__iexact=ident_clean).exists():
                raise forms.ValidationError(_('An account with this email already exists.'))
            return ident_clean
        else:
            # Phone validation
            clean_digits = re.sub(r'\D', '', ident)
            if len(clean_digits) < 10:
                raise forms.ValidationError(_('Please enter a valid 10-digit mobile number.'))
            # Standardize Indian 10-digit format
            if len(clean_digits) == 10:
                phone_std = clean_digits
            elif len(clean_digits) == 12 and clean_digits.startswith('91'):
                phone_std = clean_digits[2:]
            else:
                phone_std = clean_digits

            if User.objects.filter(phone_number=phone_std).exists():
                raise forms.ValidationError(_('An account with this phone number already exists.'))
            return phone_std

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        identifier = cleaned_data.get('identifier')
        otp = cleaned_data.get('otp')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', _('Passwords do not match.'))

        # Real OTP backend verification
        if identifier and otp:
            is_valid, err_msg = VerificationService.verify_otp_challenge(identifier, otp, purpose='signup')
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
    User login form supporting Username, Email, or Phone Number.
    """
    username = forms.CharField(
        label=_('Email, Phone or Username'),
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': _('email, phone or username'),
            'autofocus': True,
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'input-field',
            'placeholder': '••••••••',
            'autocomplete': 'current-password'
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
