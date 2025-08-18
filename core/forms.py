# core/forms.py

from django import forms
from .models import LeaveRequest,OvertimeRequest,Candidate

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        # Update the fields to use the new datetime fields
        fields = ['leave_type', 'start_datetime', 'end_datetime', 'reason'] 
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'reason': forms.Textarea(attrs={'rows': 4}),
        }

class OvertimeRequestForm(forms.ModelForm):
    class Meta:
        model = OvertimeRequest
        fields = ['date', 'hours', 'reason']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class CandidateApplicationForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['first_name', 'last_name', 'email', 'phone', 'resume']
        labels = {
            'first_name': '名字 (First Name)',
            'last_name': '姓氏 (Last Name)',
            'email': 'Email 地址',
            'phone': '電話 (Phone)',
            'resume': '履歷檔案 (Resume)',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'resume': forms.FileInput(attrs={'class': 'form-control'}),
        }