from django import forms
from .models import Manual

class ManualForm(forms.ModelForm):
    class Meta:
        model = Manual
        fields = ['document_id', 'machine', 'revision', 'file', 'document_name']
        widgets = {
            'document_id': forms.TextInput(attrs={'class': 'form-control'}),
            'machine': forms.Select(attrs={'class': 'form-select'}),
            'revision': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'document_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
