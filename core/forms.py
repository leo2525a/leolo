# core/forms.py

from django import forms
from .models import LeaveRequest,OvertimeRequest,Candidate, Employee
from datetime import date
from django.contrib.auth.models import User

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

class TaxReportForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status='Active'),
        label="選擇員工",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tax_year = forms.IntegerField(
        label="稅務年度 (開始年份)",
        initial=date.today().year - 1, # Default to the previous year
        help_text="請輸入課稅年度的開始年份，例如 2024 代表 2024/25 年度。",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class EmployeeUpdateForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'gender', 'date_of_birth', 'nationality', 'id_number',
            'marital_status', 'phone_number', 'emergency_contact_name',
            'emergency_contact_phone', 'residential_address', 'correspondence_address'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }