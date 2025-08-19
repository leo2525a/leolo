# core/admin.py
from django.contrib import admin, messages
from django.db import transaction, models
from django.utils.html import format_html
from .models import (Department, Position, Employee, LeaveType, LeaveRequest, 
                     EmployeeDocument, ReviewCycle, PerformanceReview, Goal, Announcement,
                     OnboardingChecklist, EmployeeTask, SiteConfiguration, LeavePolicy, 
                     PolicyRule, WorkSchedule, ScheduleRule, DutyShift, ContractTemplate,SalaryHistory,
                     PublicHoliday, LeaveBalanceAdjustment,JobOpening, Candidate, Application, EmailTemplate
                     ,PayrollRun, Payslip, PayslipItem, SalaryHistory,PayrollConfiguration, LeaveBalance) # 確保所有模型都已匯入
from django.urls import reverse
from django.core.files.base import ContentFile
from django.utils.html import format_html
from django.shortcuts import redirect
from weasyprint import HTML
from django.template import Context, Template
from decimal import Decimal
from datetime import date,datetime
import json
import pprint # 👈 確保 pprint 已匯入

# --- INLINE CLASSES ---
class ScheduleRuleInline(admin.TabularInline):
    model = ScheduleRule
    extra = 1

class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 1

class GoalInline(admin.TabularInline):
    model = Goal
    extra = 1

class PerformanceReviewInline(admin.TabularInline):
    model = PerformanceReview
    extra = 0
    fields = ('employee', 'status', 'overall_rating')
    readonly_fields = ('employee',)
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False

class SalaryHistoryInline(admin.TabularInline):
    model = SalaryHistory
    extra = 1 # 預設顯示一個空白的新增欄位
    verbose_name = "薪資歷史記錄"
    verbose_name_plural = "薪資歷史記錄"


class PolicyRuleInline(admin.TabularInline):
    model = PolicyRule
    extra = 1

# 👇 2. 新增 ApplicationInline
class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0
    fields = ('candidate', 'status', 'applied_at')
    readonly_fields = ('applied_at',)
    raw_id_fields = ('candidate',)
    verbose_name = "應徵記錄"
    verbose_name_plural = "應徵記錄"


# --- ACTION FUNCTIONS ---

def send_interview_invitation_action(modeladmin, request, queryset):
    template = EmailTemplate.objects.first()
    if not template:
        modeladmin.message_user(request, "錯誤：找不到任何 Email 樣板，請先建立一個。", messages.ERROR)
        return

    sent_count = 0
    for application in queryset:
        # 建立專屬連結
        form_url = request.build_absolute_uri(
            reverse('core:candidate_data_form', args=[application.token])
        )

        context_data = {
            'candidate_full_name': application.candidate.get_full_name(),
            'candidate_email': application.candidate.email,
            'job_title': application.job.title,
            'interview_form_url': form_url,
        }
        
        # 渲染樣板
        subject = Template(template.subject).render(Context(context_data))
        body = Template(template.body).render(Context(context_data))

        # 發送郵件
        try:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [application.candidate.email],
                fail_silently=False,
            )
            sent_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"發送給 {application.candidate.email} 失敗: {e}", messages.ERROR)

    if sent_count > 0:
        modeladmin.message_user(request, f"已成功為 {sent_count} 個應徵記錄發送面試邀請。", messages.SUCCESS)

send_interview_invitation_action.short_description = "發送面試邀請及資料填寫連結"

@transaction.atomic
def generate_payslips_action(modeladmin, request, queryset):
    processed_runs = 0
    for payroll_run in queryset:
        if payroll_run.status != 'Draft':
            modeladmin.message_user(request, f"發薪週期 '{payroll_run}' 不是草稿狀態，已跳過。", messages.WARNING)
            continue

        # 1. 找出所有在職員工
        active_employees = Employee.objects.filter(status='Active')
        
        # 2. 清除舊的薪資單 (如果有的話)，讓這個動作可以安全地重複執行
        payroll_run.payslips.all().delete()

        for emp in active_employees:
            # 3. 獲取員工最新的薪資記錄
            latest_salary = emp.get_current_salary()
            if not latest_salary:
                continue # 如果員工沒有薪資記錄，則跳過

            # 4. 建立空的薪資單
            payslip = Payslip.objects.create(payroll_run=payroll_run, employee=emp)
            
            # 5. 新增薪資項目 (Earnings)
            base_salary = latest_salary.base_salary
            PayslipItem.objects.create(
                payslip=payslip, item_type='Earning',
                description='基本薪資 (Base Salary)', amount=base_salary
            )
            # 未來可在此處加入其他收入項目，例如從 OvertimeRequest 抓取加班費

            # 6. 計算並新增扣款項目 (Deductions) - 簡化版馬來西亞規則
            payroll_config = PayrollConfiguration.load() # 從新的模型讀取組態

            # 從 payroll_config 中獲取費率和數值
            epf_employee = base_salary * payroll_config.epf_employee_rate
            socso_employee = payroll_config.socso_employee_amount
            
            PayslipItem.objects.create(
                payslip=payslip, item_type='Deduction', 
                description='公積金 (EPF)', amount=epf_employee.quantize(Decimal('0.01'))
            )
            PayslipItem.objects.create(
                payslip=payslip, item_type='Deduction', 
                description='社會保險 (SOCSO)', amount=socso_employee
            )

            # 7. 匯總計算
            gross_salary = payslip.items.filter(item_type='Earning').aggregate(total=models.Sum('amount'))['total'] or 0
            total_deductions = payslip.items.filter(item_type='Deduction').aggregate(total=models.Sum('amount'))['total'] or 0
            net_salary = gross_salary - total_deductions

            # 8. 更新薪資單的匯總欄位
            payslip.gross_salary = gross_salary
            payslip.total_deductions = total_deductions
            payslip.net_salary = net_salary
            payslip.save()

        # 9. 更新發薪週期的狀態
        payroll_run.status = 'Generated'
        payroll_run.save()
        processed_runs += 1

    if processed_runs > 0:
        modeladmin.message_user(request, f"已成功為 {processed_runs} 個發薪週期，共 {active_employees.count()} 位員工生成薪資單。", messages.SUCCESS)

generate_payslips_action.short_description = "為選中的週期生成薪資單 (Generate Payslips)"


def assign_onboarding_checklist(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Please select only one employee to assign a checklist.", messages.ERROR)
        return
    
    employee = queryset.first()
    try:
        checklist = OnboardingChecklist.objects.first()
        if not checklist:
            raise OnboardingChecklist.DoesNotExist
        
        EmployeeTask.objects.filter(employee=employee).delete()
        tasks = checklist.tasks.strip().split('\n')
        for task_str in tasks:
            if task_str.strip():
                EmployeeTask.objects.create(employee=employee, task_description=task_str.strip())
        
        modeladmin.message_user(request, f"Successfully assigned '{checklist.name}' to {employee.user.username}.")
    
    except OnboardingChecklist.DoesNotExist:
        modeladmin.message_user(request, "Error: No Onboarding Checklist Template found. Please create one first.", messages.ERROR)

assign_onboarding_checklist.short_description = "Assign Onboarding Checklist"


# --- 👇 這是唯一的、正確的 generate_contract_action 函數 ---
def generate_contract_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "請只選擇一位員工來生成合約。", messages.ERROR)
        return

    employee_to_process = queryset.first()
    try:
        employee = Employee.objects.select_related(
            'user', 'department', 'position', 'manager__user', 
            'work_schedule', 'leave_policy'
        ).get(pk=employee_to_process.pk)
    except Employee.DoesNotExist:
        modeladmin.message_user(request, "找不到該員工的完整資料。", messages.ERROR)
        return

    template = ContractTemplate.objects.first()
    config = SiteConfiguration.load()

    if not template:
        modeladmin.message_user(request, "錯誤：找不到任何合約樣板，請先建立一個。", messages.ERROR)
        return

    logo_url = request.build_absolute_uri(config.company_logo.url) if config.company_logo else ''
    
    context_data = {
        'employee_full_name': f"{employee.user.first_name} {employee.user.last_name}".strip() or employee.user.username,
        'employee_first_name': employee.user.first_name or '',
        'employee_last_name': employee.user.last_name or '',
        'employee_id': employee.employee_number or 'N/A',
        'employee_email': employee.user.email or 'N/A',
        'employee_phone': employee.phone_number or 'N/A',
        'hire_date': employee.hire_date.strftime('%Y年%m月%d日') if employee.hire_date else 'N/A',
        'position': employee.position.title if employee.position else 'N/A',
        'department': employee.department.name if employee.department else 'N/A',
        'manager_name': employee.manager.user.get_full_name() if employee.manager and employee.manager.user else 'N/A',
        'work_schedule': employee.work_schedule.name if employee.work_schedule else 'N/A',
        'annual_leave_policy': employee.leave_policy.name if employee.leave_policy else 'N/A',
        'company_logo_url': logo_url,
        'today_date': date.today().strftime('%Y年%m月%d日'),
    }

    template_engine = Template(template.body)
    context_engine = Context(context_data)
    rendered_html = template_engine.render(context_engine)
    pdf_file = HTML(string=rendered_html, base_url=request.build_absolute_uri()).write_pdf()
    file_name = f"contract_{employee.employee_number}_{date.today()}.pdf"
    
    if not employee.documents.filter(title=f"Employment Contract {date.today()}").exists():
         document = employee.documents.create(title=f"Employment Contract {date.today()}")
         document.file.save(file_name, ContentFile(pdf_file), save=True)
         modeladmin.message_user(request, f"已成功為 {employee.user.username} 生成合約。")
    else:
         modeladmin.message_user(request, f"今日的合約已存在。", messages.WARNING)

generate_contract_action.short_description = "為選中員工生成合約"

class PayslipItemInline(admin.TabularInline):
    model = PayslipItem
    extra = 0
    readonly_fields = ('item_type', 'description', 'amount')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False

class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0
    fields = ('employee', 'gross_salary', 'total_deductions', 'net_salary')
    readonly_fields = ('employee', 'gross_salary', 'total_deductions', 'net_salary')
    can_delete = False
    show_change_link = True # 允許點擊進入薪資單詳情
    def has_add_permission(self, request, obj=None):
        return False

# --- MODEL ADMIN CLASSES ---
@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'created_at')
    change_form_template = "admin/core/contracttemplate/change_form.html" # 重用合約的樣板

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        placeholders = [
            {'group': '應聘者資料', 'name': '全名', 'value': '{{ candidate_full_name }}'},
            {'group': '應聘者資料', 'name': 'Email', 'value': '{{ candidate_email }}'},
            {'group': '職位資料', 'name': '應徵職位', 'value': '{{ job_title }}'},
            {'group': '系統生成', 'name': '個人資料填寫連結', 'value': '{{ interview_form_url }}'},
        ]
        context['placeholders_json'] = json.dumps(placeholders)
        context['title'] = "編輯 Email 樣板" # 改變頁面標題
        return super().render_change_form(request, context, add, change, form_url, obj)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'user', 'department', 'position', 'status', 'leave_policy','work_schedule')
    list_filter = ('department', 'position', 'status')
    search_fields = ('employee_number', 'user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'manager')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('user', 'gender', 'date_of_birth', 'nationality', 'id_number', 'marital_status')
        }),
        ('Job Details', {
            'fields': ('employee_number', 'department', 'position', 'manager', 'hire_date', 'termination_date')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'emergency_contact_name', 'emergency_contact_phone', 'residential_address', 'correspondence_address','email_original')
        }),
        ('Employment Status', {
            'fields': ('status', 'employment_type', 'work_schedule', 'leave_policy')
        }),
    )

    inlines = [EmployeeDocumentInline, SalaryHistoryInline]
    actions = [assign_onboarding_checklist, generate_contract_action]

@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    change_form_template = "admin/core/contracttemplate/change_form.html"

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        placeholders = [
            {'group': '員工基本資料', 'name': '全名', 'value': '{{ employee_full_name }}'},
            {'group': '員工基本資料', 'name': '姓氏', 'value': '{{ employee_last_name }}'},
            {'group': '員工基本資料', 'name': '名字', 'value': '{{ employee_first_name }}'},
            {'group': '員工基本資料', 'name': '員工編號', 'value': '{{ employee_id }}'},
            {'group': '員工基本資料', 'name': '公司電郵', 'value': '{{ employee_email }}'},
            {'group': '員工基本資料', 'name': '電話', 'value': '{{ employee_phone }}'},
            {'group': '職位相關', 'name': '入職日期', 'value': '{{ hire_date }}'},
            {'group': '職位相關', 'name': '職位', 'value': '{{ position }}'},
            {'group': '職位相關', 'name': '部門', 'value': '{{ department }}'},
            {'group': '職位相關', 'name': '直屬經理', 'value': '{{ manager_name }}'},
            {'group': '政策與其他', 'name': '預設班表', 'value': '{{ work_schedule }}'},
            {'group': '政策與其他', 'name': '年假策略', 'value': '{{ annual_leave_policy }}'},
            {'group': '公司與日期', 'name': '公司Logo', 'value': '<img src="{{ company_logo_url }}" width="150">' },
            {'group': '公司與日期', 'name': '簽署日期 (今日)', 'value': '{{ today_date }}'},
        ]
        context['placeholders_json'] = json.dumps(placeholders)
        return super().render_change_form(request, context, add, change, form_url, obj)

@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    inlines = [ScheduleRuleInline]

@admin.register(ReviewCycle)
class ReviewCycleAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_active')
    inlines = [PerformanceReviewInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            active_employees = Employee.objects.filter(status='Active')
            for emp in active_employees:
                PerformanceReview.objects.get_or_create(employee=emp, cycle=obj)
            self.message_user(request, f"Successfully created reviews for {len(active_employees)} active employees.")

@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'cycle', 'status', 'overall_rating')
    list_filter = ('cycle', 'status', 'overall_rating')
    search_fields = ('employee__user__username',)
    inlines = [GoalInline]

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at', 'is_published')
    list_filter = ('is_published', 'created_at')
    search_fields = ('title', 'content')
    
    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'author') or not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(OnboardingChecklist)
class OnboardingChecklistAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(PayrollConfiguration)
class PayrollConfigurationAdmin(admin.ModelAdmin):
    fieldsets = (
        ('法定繳款率', {
            'fields': ('epf_employee_rate', 'epf_employer_rate', 'socso_employee_amount')
        }),
    )

    def changelist_view(self, request, extra_context=None):
        config, created = self.model.objects.get_or_create(pk=1)
        url = reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change', args=[config.pk])
        return redirect(url)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    # 👇 我們將在這裡新增「出勤設定」的區塊
    fieldsets = (
        ('郵件設定', {
            'fields': ('email_host', 'email_port', 'email_use_tls', 'email_host_user', 'email_host_password')
        }),
        ('公司資訊', {
            'fields': ('company_logo', 'employer_file_number',) # 👈 加入僱主檔案號碼
        }),
        ('出勤設定', {
            'fields': ('allowed_ip_addresses',)
        }),

    )

    # 當使用者點擊列表頁時，自動導向到唯一的編輯頁面
    def changelist_view(self, request, extra_context=None):
        config, created = SiteConfiguration.objects.get_or_create(pk=1)
        url = reverse('admin:core_siteconfiguration_change', args=[config.pk])
        return redirect(url)

    # 隱藏「新增」按鈕
    def has_add_permission(self, request):
        return False

    # 隱藏「刪除」按鈕
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'color')
    # 為了讓顏色選擇更直覺，可以在 Django 後台整合一個顏色選擇器套件
    # 但最簡單的方式就是直接讓管理者輸入顏色碼

@admin.register(DutyShift)
class DutyShiftAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'start_time', 'end_time')
    list_filter = ('date', 'employee')

@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'accrual_frequency', 'accrual_amount', 'accrual_unit', 'enable_holiday_compensation') # 啟用節假日補償
    inlines = [PolicyRuleInline]
    
    # 透過 fieldsets 來美化編輯頁面的排版
    fieldsets = (
        ('基本資訊', {
            'fields': ('name', 'description')
        }),
        ('權責發生設定', {
            'fields': ('accrual_frequency', 'accrual_amount', 'accrual_unit')
        }),
        ('年度結算設定', {
            'fields': ('fiscal_year_start_month', 'allow_carry_over', 'max_carry_over_amount')
        }),
        ('到職等待期', {
            'fields': ('waiting_period_amount', 'waiting_period_unit')
        }),
        # 【↓↓↓ 新增這個區塊 ↓↓↓】
        ('其他設定', {
            'fields': ('enable_holiday_compensation',)
        }),
    )

@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    # 在 list_display 中加入 'application_count' 和 'view_pipeline_link'
    list_display = ('title', 'department', 'status', 'application_count', 'view_pipeline_link', 'created_at')
    list_filter = ('status', 'department')
    search_fields = ('title', 'description')
    inlines = [ApplicationInline]

    # 新增方法：計算該職缺的應徵人數
    def application_count(self, obj):
        return obj.applications.count()
    application_count.short_description = "應徵人數"

    # 新增方法：生成一個可點擊的 HTML 連結
    def view_pipeline_link(self, obj):
        # 使用 reverse 函數來動態地找到對應的 URL
        url = reverse("core:recruitment_pipeline", args=[obj.id])
        # 使用 format_html 來安全地產生 HTML
        return format_html(f'<a href="{url}" target="_blank">查看管道</a>')
    view_pipeline_link.short_description = "管理管道"

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'email', 'phone', 'created_at')
    search_fields = ('first_name', 'last_name', 'email')
    # 為了避免循環參照，我們不在這裡也加入 ApplicationInline

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('job', 'candidate', 'status', 'applied_at')
    list_filter = ('status', 'job')
    search_fields = ('candidate__first_name', 'candidate__last_name', 'job__title')
    raw_id_fields = ('job', 'candidate')
    actions = [send_interview_invitation_action]

@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'created_at')
    list_filter = ('status', 'year')
    inlines = [PayslipInline]
    actions = [generate_payslips_action] # 👈 將 Action 加入

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll_run', 'gross_salary', 'total_deductions', 'net_salary')
    list_filter = ('payroll_run',)
    search_fields = ('employee__user__username',)
    inlines = [PayslipItemInline]
    raw_id_fields = ['employee'] # Changed from autocomplete_fields

@admin.register(LeaveBalanceAdjustment)
class LeaveBalanceAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'hours_changed', 'reason', 'created_at')
    list_filter = ('employee', 'leave_type')
    raw_id_fields = ['employee'] # Changed from autocomplete_fields
    list_per_page = 20
    search_fields = ('employee__user__username', 'reason')
    ordering = ('-created_at',)

    def save_model(self, request, obj, form, change):
        """
        當儲存一筆調整記錄時，自動更新對應的 LeaveBalance。
        """
        # 使用資料庫交易確保資料一致性
        with transaction.atomic():
            # 首先儲存調整記錄物件本身
            super().save_model(request, obj, form, change)

            # 尋找或建立對應的假期餘額記錄
            balance, created = LeaveBalance.objects.get_or_create(
                employee=obj.employee,
                leave_type=obj.leave_type
            )

            # 更新餘額
            balance.balance_hours += obj.hours_changed
            balance.save()

            # 在後台顯示成功訊息
            messages.success(request, f"成功為 {obj.employee.user.get_full_name()} 的 {obj.leave_type.name} 調整了 {obj.hours_changed} 小時。新的餘額為 {balance.balance_hours} 小時。")


# --- SIMPLE REGISTRATIONS ---
admin.site.register(Position)
admin.site.register(LeaveType)
admin.site.register(LeaveRequest)
admin.site.register(EmployeeDocument)
admin.site.register(Goal)
admin.site.register(EmployeeTask)
admin.site.register(PublicHoliday)
admin.site.register(SalaryHistory)