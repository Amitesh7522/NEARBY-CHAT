from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Room

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'topic', 'description', 'avatar', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('e.g. Technology & Startups')}),
            'topic': forms.TextInput(attrs={'class': 'input-field', 'placeholder': _('e.g. Tech, Music, Gaming')}),
            'description': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': _('What is this room about?')}),
            'is_public': forms.CheckboxInput(attrs={'class': 'checkbox-field'}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'file') and not isinstance(avatar, str):
            from apps.core.security import sanitize_and_strip_image_exif
            return sanitize_and_strip_image_exif(avatar, max_dimension=800, max_size_bytes=5 * 1024 * 1024)
        return avatar
