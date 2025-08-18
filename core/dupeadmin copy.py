# core/admin.py
from django.contrib import admin, messages
from .models import (Department, Position, Employee, LeaveType, LeaveRequest, 
                     EmployeeDocument, ReviewCycle, PerformanceReview, Goal, Announcement,
                     OnboardingChecklist, EmployeeTask, SiteConfiguration, LeavePolicy, 
                     PolicyRule, WorkSchedule, ScheduleRule, DutyShift, ContractTemplate)
from django.urls import reverse
from django.core.files.base import ContentFile
from django.utils.html import format_html
from django.shortcuts import redirect
from weasyprint import HTML
from django.template import Context, Template
from datetime import date,datetime
import json
import pprint

# --- INLINE CLASSES ---

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

    # --- 👇 這是我們的終極偵錯方法 👇 ---
    # 將 context 字典格式化為一個易於閱讀的字串
    debug_string = pprint.pformat(context_data)
    # 使用 messages.INFO 在網頁頂部顯示這個字串
    modeladmin.message_user(request, f"偵錯資訊：{debug_string}", messages.INFO)
    # --- 🔼 偵錯結束 🔼 ---

    # 為了避免重複生成文件，我們先暫時退出，只做偵錯
    return # <--- 暫時在這裡退出，先不生成 PDF


def generate_contract_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "請只選擇一位員工來生成合約。", messages.ERROR)
        return

    employee = queryset.first()
    template = ContractTemplate.objects.first() # 簡單起見，先抓取第一個樣板
    config = SiteConfiguration.load()

    if not template:
        modeladmin.message_user(request, "錯誤：找不到任何合約樣板，請先建立一個。", messages.ERROR)
        return

    # 1. 準備動態資料 (Context)
    logo_url = request.build_absolute_uri(config.company_logo.url) if config.company_logo else ''
    context_data = {
        'employee_name': employee.user.get_full_name(),
        'employee_id': employee.employee_number,
        'hire_date': employee.hire_date.strftime('%Y年%m月%d日'),
        'position': employee.position.title if employee.position else '',
        'department': employee.department.name if employee.department else '',
        'company_logo_url': logo_url,
        # 您可以繼續新增更多變數，例如薪資
        # 'salary': employee.salary, 
    }

    # 2. 渲染 HTML 樣板
    template_engine = Template(template.body)
    context_engine = Context(context_data)
    rendered_html = template_engine.render(context_engine)

    # 3. 使用 WeasyPrint 生成 PDF
    pdf_file = HTML(string=rendered_html, base_url=request.build_absolute_uri()).write_pdf()

    # 4. 儲存 PDF 並建立 EmployeeDocument 記錄
    file_name = f"contract_{employee.employee_number}_{date.today()}.pdf"

    # 檢查是否已存在同名文件，避免重複
    if not employee.documents.filter(title=f"Employment Contract {date.today()}").exists():
        document = EmployeeDocument(
            employee=employee,
            title=f"Employment Contract {date.today()}"
        )
        document.file.save(file_name, ContentFile(pdf_file), save=True)
        modeladmin.message_user(request, f"已成功為 {employee.user.username} 生成合約。")
    else:
        modeladmin.message_user(request, f"合約已存在。", messages.WARNING)

generate_contract_action.short_description = "為選中員工生成合約"

class ScheduleRuleInline(admin.TabularInline):
    model = ScheduleRule
    extra = 1

@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    inlines = [ScheduleRuleInline]

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

# --- ACTION FUNCTIONS ---
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

# --- MODEL ADMIN CLASSES ---
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'user', 'department', 'position', 'status', 'leave_policy','work_schedule')
    list_filter = ('department', 'position', 'status')
    search_fields = ('employee_number', 'user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'manager')
    inlines = [EmployeeDocumentInline]
    actions = [assign_onboarding_checklist, generate_contract_action] # 👈 加入新的 Action

@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    change_form_template = "admin/core/contracttemplate/change_form.html"

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        # 這是提供給前端按鈕的完整 placeholder 列表
        placeholders = [
            # 員工基本資料
            {'group': '員工基本資料', 'name': '全名', 'value': '{{ employee_full_name }}'},
            {'group': '員工基本資料', 'name': '姓氏', 'value': '{{ employee_last_name }}'},
            {'group': '員工基本資料', 'name': '名字', 'value': '{{ employee_first_name }}'},
            {'group': '員工基本資料', 'name': '員工編號', 'value': '{{ employee_id }}'},
            {'group': '員工基本資料', 'name': '公司電郵', 'value': '{{ employee_email }}'},
            {'group': '員工基本資料', 'name': '電話', 'value': '{{ employee_phone }}'},

            # 職位相關
            {'group': '職位相關', 'name': '入職日期', 'value': '{{ hire_date }}'},
            {'group': '職位相關', 'name': '職位', 'value': '{{ position }}'},
            {'group': '職位相關', 'name': '部門', 'value': '{{ department }}'},
            {'group': '職位相關', 'name': '直屬經理', 'value': '{{ manager_name }}'},

            # 政策與其他
            {'group': '政策與其他', 'name': '預設班表', 'value': '{{ work_schedule }}'},
            {'group': '政策與其他', 'name': '年假策略', 'value': '{{ annual_leave_policy }}'},

            # 公司與日期
            {'group': '公司與日期', 'name': '公司Logo', 'value': '<img src="{{ company_logo_url }}" width="150">' },
            {'group': '公司與日期', 'name': '簽署日期 (今日)', 'value': '{{ today_date }}'},
        ]
        context['placeholders_json'] = json.dumps(placeholders)
        
        return super().render_change_form(request, context, add, change, form_url, obj)

# 請確保您的 EmployeeAdmin 也被正確註冊，並加入了新的 Action

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

@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    fieldsets = (
        ('郵件設定', {
            'fields': ('email_host', 'email_port', 'email_use_tls', 'email_host_user', 'email_host_password')
        }),
        ('公司資訊', {
            'fields': ('company_logo',)
        }),
    )

    # 當使用者點擊列表頁時，自動導向到唯一的編輯頁面
    def changelist_view(self, request, extra_context=None):
        # 取得或建立唯一的設定實例
        config, created = SiteConfiguration.objects.get_or_create(pk=1)
        # 取得該實例的編輯頁面 URL
        url = reverse('admin:core_siteconfiguration_change', args=[config.pk])
        return redirect(url)

    # 隱藏「新增」按鈕
    def has_add_permission(self, request):
        return False

    # 隱藏「刪除」按鈕
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(DutyShift)
class DutyShiftAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'start_time', 'end_time')
    list_filter = ('date', 'employee')

class PolicyRuleInline(admin.TabularInline):
    model = PolicyRule
    extra = 1

@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    inlines = [PolicyRuleInline]

    fieldsets = (
        ('基本資訊', {
            'fields': ('name', 'description')
        }),
        ('等待期設定', {
            'fields': ('waiting_period_amount', 'waiting_period_unit')
        }),
        ('權責發生制規則 (基礎)', {
            'fields': ('accrual_frequency', 'accrual_amount', 'accrual_unit')
        }),
        ('年度結算規則 (Year-End)', {
            'fields': ('fiscal_year_start_month', 'allow_carry_over', 'max_carry_over_amount')
        }),
    )



# --- SIMPLE REGISTRATIONS (for models without custom Admins) ---
admin.site.register(Department)
admin.site.register(Position)
admin.site.register(LeaveType)
admin.site.register(LeaveRequest)
admin.site.register(EmployeeDocument)
admin.site.register(Goal)
admin.site.register(EmployeeTask)