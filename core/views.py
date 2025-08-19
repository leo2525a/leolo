# core/views.py

from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404 # <-- 在這裡加上 get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import modelformset_factory 
from .models import (Employee, LeaveRequest, LeaveType, LeaveBalance,
                     EmployeeDocument, ReviewCycle, PerformanceReview, Goal, Announcement,
                     OnboardingChecklist, EmployeeTask, SiteConfiguration, Department,Employee, OvertimeRequest, DutyShift, PublicHoliday,
                     JobOpening, Candidate, Application, AttendanceRecord, PayslipItem) # <-- Make sure Department is in this list
from .forms import LeaveRequestForm, OvertimeRequestForm,CandidateApplicationForm, TaxReportForm, UserUpdateForm, EmployeeUpdateForm
from django.core.mail import send_mail, get_connection
from django.template.loader import render_to_string
from django.urls import reverse
import calendar
import pandas as pd # 👈 1. 在頂部新增
from django.db.models import Count, Sum, Q # 👈 1. 在頂部新增
from django.http import JsonResponse, HttpResponse # 
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone
import json
import holidays
from weasyprint import HTML
from decimal import Decimal
import os # 👈 2. 匯入 os 模組
from django.conf import settings # 👈 3. 匯入 settings
from docx import Document
import io
from pypdf import PdfReader, PdfWriter

@login_required
def profile_view(request):
    """
    Displays the user's main profile/dashboard if their profile is complete.
    If not, it redirects them to the profile edit page.
    """
    try:
        employee = request.user.employee_profile
    except Employee.DoesNotExist:
        messages.error(request, '無法找到您的員工資料。超級使用者請使用管理後台。')
        return redirect('admin:index')

    # 1. 檢查個人資料是否完整
    if not employee.is_profile_complete():
        return redirect('core:profile_edit')

    # --- 2. 抓取儀表板所需的全部數據 ---

    # (A) 頂部四個統計卡片的數據
    today = date.today()
    total_employees = Employee.objects.filter(status='Active').count()
    on_leave_today = LeaveRequest.objects.filter(
        status='Approved',
        start_datetime__date__lte=today,
        end_datetime__date__gte=today
    ).count()
    pending_requests = LeaveRequest.objects.filter(employee=employee, status='Pending').count()
    open_positions = JobOpening.objects.filter(status='Open').count()

    # (B) 最近的休假申請 (與之前相同)
    leave_requests = LeaveRequest.objects.filter(employee=employee).order_by('-start_datetime')[:5]

    # (C) 假期餘額數據 (與之前相同，用於圖表)
    leave_balances_data = []
    balances = employee.leave_balances.all().select_related('leave_type')
    for balance in balances:
        used_hours = LeaveRequest.objects.filter(
            employee=employee,
            leave_type=balance.leave_type,
            status='Approved'
        ).aggregate(total=Sum('duration_hours'))['total'] or 0

        leave_balances_data.append({
            'name': balance.leave_type.name,
            'total': float(balance.balance_hours),
            'used': float(used_hours),
            'remaining': float(balance.balance_hours - used_hours)
        })

    # (D) 最新公告 (與之前相同)
    latest_announcements = Announcement.objects.filter(is_published=True).order_by('-created_at')[:3]

    context = {
        'employee': employee,
        # 新增的統計數據
        'total_employees': total_employees,
        'on_leave_today': on_leave_today,
        'pending_requests': pending_requests,
        'open_positions': open_positions,
        # 原有的數據
        'leave_requests': leave_requests,
        'latest_announcements': latest_announcements,
        'leave_balances_data': leave_balances_data,
    }
    return render(request, 'core/profile.html', context)

@login_required
def profile_edit_view(request):
    """
    Handles the form for editing user and employee profile information.
    """
    try:
        employee = request.user.employee_profile
    except Employee.DoesNotExist:
        messages.error(request, '無法找到您的員工資料。')
        return redirect('admin:index')

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        employee_form = EmployeeUpdateForm(request.POST, instance=employee)
        if user_form.is_valid() and employee_form.is_valid():
            user_form.save()
            employee_form.save()
            messages.success(request, '您的個人資料已成功更新。')
            # After saving, redirect back to the main profile view.
            # The middleware or the view itself will then allow access to the dashboard.
            return redirect('core:profile')
        else:
            messages.error(request, '資料更新失敗，請檢查您輸入的內容。')
    else:
        user_form = UserUpdateForm(instance=request.user)
        employee_form = EmployeeUpdateForm(instance=employee)

    # Add a warning message if the profile is still incomplete
    if not employee.is_profile_complete():
        messages.warning(request, '為了啟用所有功能，請您先填寫完整的個人資料。')

    context = {
        'user_form': user_form,
        'employee_form': employee_form
    }
    return render(request, 'core/profile_edit.html', context)

# core/views.py

@login_required
def leave_apply_view(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "您的員工個人資料找不到，請聯繫 HR。")
        return redirect('core:profile')

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = employee
            leave_request.save()

            if employee.manager and employee.manager.user.email:
                config = SiteConfiguration.load()
                if config.email_host_user and config.email_host_password:
                    connection = get_connection(
                        host=config.email_host, port=config.email_port,
                        username=config.email_host_user, password=config.email_host_password,
                        use_tls=config.email_use_tls
                    )
                    dashboard_url = request.build_absolute_uri(reverse('core:manager_dashboard'))
                    mail_subject = f"[待審批] {employee.user.get_full_name()} 的休假申請"
                    # 👇 修正這裡的 mail_context
                    mail_context = {
                        'employee_name': employee.user.get_full_name(),
                        'manager_name': employee.manager.user.get_full_name(),
                        'leave_type': leave_request.leave_type.name,
                        'start_datetime': leave_request.start_datetime,
                        'end_datetime': leave_request.end_datetime,
                        'reason': leave_request.reason,
                        'dashboard_url': dashboard_url,
                    }
                    message = render_to_string('core/emails/notify_manager_new_leave.txt', mail_context)
                    send_mail(
                        subject=mail_subject, message=message, from_email=config.email_host_user,
                        recipient_list=[employee.manager.user.email], fail_silently=False,
                        connection=connection
                    )

            messages.success(request, '您的休假申請已成功提交！')
            return redirect('core:profile')
    else:
        form = LeaveRequestForm()

    context = {'form': form, 'employee': employee}
    return render(request, 'core/leave_apply.html', context)

def login_view(request):
    # 如果使用者已經登入，就直接導向到個人資料頁
    if request.user.is_authenticated:
        return redirect('core:profile')
    
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            # 表單驗證成功，登入使用者
            user = form.get_user()
            login(request, user)
            return redirect('core:profile') # 登入後導向到個人資料頁
    else:
        form = AuthenticationForm()
        
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('core:login') # 登出後導向到新的登入頁

@login_required
def manager_dashboard_view(request):
    try:
        manager_employee = Employee.objects.get(user=request.user)
        is_manager = Employee.objects.filter(manager=manager_employee).exists()
    except Employee.DoesNotExist:
        is_manager = False

    if not is_manager:
        messages.error(request, '您沒有權限訪問此頁面。')
        return redirect('core:profile')

    # --- Fetch pending leave requests (this part is fine) ---
    pending_leaves = LeaveRequest.objects.filter(
        employee__manager=manager_employee,
        status='Pending'
    ).order_by('created_at')
    
    # --- Fetch pending performance reviews (this part is fine) ---
    pending_reviews = PerformanceReview.objects.filter(
        employee__manager=manager_employee
    ).exclude(status='Completed').order_by('cycle__end_date')

    # --- 👇 新增：抓取待審批的加班申請 ---
    pending_overtime = OvertimeRequest.objects.filter(
        employee__manager=manager_employee,
        status='Pending'
    ).order_by('created_at')
    # --- 🔼 新增邏輯結束 🔼 ---


    # --- Corrected Calendar Logic ---
    today = datetime.now()
    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdatescalendar(today.year, today.month)

    approved_leaves = LeaveRequest.objects.filter(
        employee__manager=manager_employee,
        status='Approved'
    )
    
    leave_dates = {}
    for leave in approved_leaves:
        # 👇 Corrected lines: use .start_datetime.date() and .end_datetime.date()
        current_date = leave.start_datetime.date()
        while current_date <= leave.end_datetime.date():
            display_name = leave.employee.user.get_full_name() or leave.employee.user.username
            leave_dates.setdefault(current_date.toordinal(), []).append(display_name)
            current_date += timedelta(days=1)
    
    context = {
        'pending_leaves': pending_leaves,
        'pending_reviews': pending_reviews,
        'pending_overtime': pending_overtime,
        'month_days': month_days,
        'leave_dates': leave_dates,
        'today_ordinal': datetime.now().date().toordinal(),
    }
    return render(request, 'core/manager_dashboard.html', context)


@login_required
def leave_approve_view(request, request_id):
    leave_request = get_object_or_404(LeaveRequest, id=request_id)
    if request.user == leave_request.employee.manager.user:
        leave_request.status = 'Approved'
        leave_request.save()
        
        # This block must be correctly indented
        if leave_request.employee.user.email:
            config = SiteConfiguration.load()
            if config.email_host_user and config.email_host_password:
                connection = get_connection(
                    host=config.email_host, port=config.email_port,
                    username=config.email_host_user, password=config.email_host_password,
                    use_tls=config.email_use_tls
                )
                mail_subject = f"Your leave request has been updated to [Approved]"
                message = render_to_string('core/emails/notify_employee_status_update.txt', {
                    'employee_name': leave_request.employee.user.get_full_name(),
                    'leave_type': leave_request.leave_type.name,
                    'start_datetime': leave_request.start_datetime,
                    'end_datetime': leave_request.end_datetime,
                    'status': 'Approved'
                })
                send_mail(mail_subject, message, config.email_host_user, [leave_request.employee.user.email], fail_silently=False, connection=connection)
        
        messages.success(request, 'Request has been approved.')
    else:
        messages.error(request, 'You do not have permission to perform this action.')
    return redirect('core:manager_dashboard')

@login_required
def leave_reject_view(request, request_id):
    leave_request = get_object_or_404(LeaveRequest, id=request_id)
    if request.user == leave_request.employee.manager.user:
        leave_request.status = 'Rejected'
        leave_request.save()
        
        # This block must be correctly indented
        if leave_request.employee.user.email:
            config = SiteConfiguration.load()
            if config.email_host_user and config.email_host_password:
                connection = get_connection(
                    host=config.email_host, port=config.email_port,
                    username=config.email_host_user, password=config.email_host_password,
                    use_tls=config.email_use_tls
                )
                mail_subject = f"您的休假申請狀態已更新為 [已拒絕]"
                # 👇 修正這裡的 mail_context
                message = render_to_string('core/emails/notify_employee_status_update.txt', {
                    'employee_name': leave_request.employee.user.get_full_name(),
                    'leave_type': leave_request.leave_type.name,
                    'start_datetime': leave_request.start_datetime,
                    'end_datetime': leave_request.end_datetime,
                    'status': '已拒絕'
                })
                send_mail(mail_subject, message, config.email_host_user, [leave_request.employee.user.email], fail_silently=False, connection=connection)

        messages.success(request, '申請已拒絕。')
    else:
        messages.error(request, '您沒有權限執行此操作。')
    return redirect('core:manager_dashboard')

@login_required
def employee_directory_view(request):
    # 篩選出所有狀態為 "Active" (在職) 的員工
    # select_related('user', 'department', 'position') 是一個效能優化技巧
    # 它會一次性地將關聯的 User, Department, Position 資料都抓取出來，避免後續的重複查詢
    employees = Employee.objects.filter(status='Active').select_related('user', 'department', 'position').order_by('user__first_name')

    context = {
        'employees': employees
    }
    return render(request, 'core/employee_directory.html', context)

@login_required
def my_reviews_view(request):
    try:
        employee = Employee.objects.get(user=request.user)
        # 找出所有指派給這位員工的評估，按最新的週期排序
        reviews = PerformanceReview.objects.filter(employee=employee).order_by('-cycle__start_date')
    except Employee.DoesNotExist:
        reviews = []

    context = {
        'reviews': reviews
    }
    return render(request, 'core/my_reviews.html', context)

# 2. 評估詳情與填寫 View
@login_required
def review_detail_view(request, review_id):
    review = get_object_or_404(PerformanceReview, id=review_id, employee__user=request.user)

    # 使用 Formset 來處理多個 Goal 的新增/編輯
    GoalFormSet = modelformset_factory(Goal, fields=('description',), extra=1, can_delete=True)

    if request.method == 'POST':
        # 處理目標的儲存
        formset = GoalFormSet(request.POST, queryset=Goal.objects.filter(review=review))
        if formset.is_valid():
            goals = formset.save(commit=False)
            for goal in goals:
                goal.review = review
                goal.save()

            # 處理自評的儲存
            review.employee_self_assessment = request.POST.get('employee_self_assessment')
            review.status = 'In Progress' # 更新狀態為進行中
            review.save()

            messages.success(request, '您的績效評估已成功儲存。')
            return redirect('core:my_reviews')

    else:
        # 顯示現有的目標
        formset = GoalFormSet(queryset=Goal.objects.filter(review=review))

    context = {
        'review': review,
        'formset': formset
    }
    return render(request, 'core/review_detail.html', context)

@login_required
def manager_review_detail_view(request, review_id):
    review = get_object_or_404(PerformanceReview, id=review_id, employee__manager__user=request.user)

    if request.method == 'POST':
        review.manager_assessment = request.POST.get('manager_assessment')
        
        # 👇 Replace the original line with this logic block 👇
        rating = request.POST.get('overall_rating')
        if rating: # Check if a rating was actually selected
            review.overall_rating = int(rating)
        else:
            review.overall_rating = None # If not, save None
        # 🔼 End of logic block 🔼
            
        review.status = 'Completed'
        review.save()
        
        messages.success(request, f"{review.employee.user.get_full_name()} 的績效評估已完成。")
        return redirect('core:manager_dashboard')

    context = {
        'review': review
    }
    return render(request, 'core/manager_review_detail.html', context)

@login_required
def analytics_view(request):
    # 權限檢查：只允許員工/經理訪問
    if not (request.user.is_staff or hasattr(request.user, 'employee')):
        messages.error(request, '您沒有權限訪問此頁面。')
        return redirect('core:profile')

    # --- 2. 數據聚合 ---
    # 總在職員工數
    total_employees = Employee.objects.filter(status='Active').count()

    # 各部門員工人數
    department_distribution = Employee.objects.filter(status='Active').values('department__name').annotate(count=Count('id')).order_by('-count')

    # 性別比例
    gender_distribution = Employee.objects.filter(status='Active').values('gender').annotate(count=Count('id'))

    # 當年度休假類型統計
    current_year = datetime.now().year
    leave_type_distribution = LeaveRequest.objects.filter(
    status='Approved', 
    start_datetime__year=current_year
    ).values('leave_type__name').annotate(count=Count('id'))

    context = {
        'total_employees': total_employees,
        'department_distribution_json': json.dumps(list(department_distribution)),
        'gender_distribution_json': json.dumps(list(gender_distribution)),
        'leave_type_distribution_json': json.dumps(list(leave_type_distribution)),
    }

    return render(request, 'core/analytics_dashboard.html', context)

@login_required
def onboarding_view(request):
    try:
        employee = Employee.objects.get(user=request.user)
        tasks = EmployeeTask.objects.filter(employee=employee)
    except Employee.DoesNotExist:
        tasks = []

    context = {
        'tasks': tasks,
        'all_completed': all(t.is_completed for t in tasks) if tasks else False
    }
    return render(request, 'core/onboarding_checklist.html', context)

@login_required
def complete_task_view(request, task_id):
    # 確保只有員工本人才能修改自己的任務
    task = get_object_or_404(EmployeeTask, id=task_id, employee__user=request.user)
    # 切換完成狀態
    task.is_completed = not task.is_completed
    task.save()
    # 操作完成後，導向回清單頁
    return redirect('core:onboarding')

@login_required
def reporting_view(request):
    # 權限檢查：只允許 staff (HR/Admin) 訪問
    if not request.user.is_staff:
        messages.error(request, '您沒有權限訪問此頁面。')
        return redirect('core:profile')

    # 準備篩選器所需的選項
    departments = Department.objects.all()

    # 如果是 POST 請求，表示使用者點擊了「匯出」按鈕
    if request.method == 'POST':
        # 獲取前端傳來的篩選條件
        department_id = request.POST.get('department')
        status = request.POST.get('status')

        # 開始查詢員工數據
        employees = Employee.objects.select_related('user', 'department', 'position', 'manager__user').all()

        if department_id:
            employees = employees.filter(department_id=department_id)
        if status:
            employees = employees.filter(status=status)

        # 將查詢結果轉換為可供 pandas 使用的格式
        data = []
        for emp in employees:
            data.append({
                "員工編號": emp.employee_number,
                "姓名": emp.user.get_full_name() or emp.user.username,
                "Email": emp.user.email,
                "性別": emp.get_gender_display(),
                "部門": emp.department.name if emp.department else '',
                "職位": emp.position.title if emp.position else '',
                "直屬經理": emp.manager.user.get_full_name() if emp.manager else '',
                "入職日期": emp.hire_date,
                "狀態": emp.get_status_display(),
            })

        if not data:
            messages.error(request, "沒有找到符合條件的資料可供匯出。")
            return redirect('core:reporting')

        # 使用 pandas 建立 DataFrame
        df = pd.DataFrame(data)

        # 準備 HTTP 回應，讓瀏覽器知道這是一個 Excel 檔案
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="employee_roster_report.xlsx"'

        # 將 DataFrame 寫入回應中
        df.to_excel(response, index=False)

        return response

    # 如果是 GET 請求，就只顯示頁面
    context = {
        'departments': departments,
    }
    return render(request, 'core/reporting_hub.html', context)

@login_required
def team_schedule_view(request, year=None, month=None):
    # 1. 日期處理
    if year is None or month is None:
        target_date = date.today()
    else:
        target_date = date(year, month, 1)

    prev_month = target_date - relativedelta(months=1)
    next_month = target_date + relativedelta(months=1)

    cal = calendar.Calendar(firstweekday=6) # 星期日為第一天
    month_days = cal.monthdatescalendar(target_date.year, target_date.month)

    first_day_of_calendar = month_days[0][0]
    last_day_of_calendar = month_days[-1][-1]

    # 2. 一次性高效抓取所有需要的資料
    departments = Department.objects.all()
    department_map = {
        dept.id: {'name': dept.name, 'color': dept.color} 
        for dept in departments
    }
    department_map[None] = {'name': '其他', 'color': '#A9A9A9'}

    # 使用 prefetch_related 一次性抓取所有員工及其關聯的班表規則
    active_employees = Employee.objects.filter(status='Active').select_related(
        'user', 'department'
    ).prefetch_related('work_schedule__rules')

    # 為每位員工預先建立好他們的工作日字典 {員工ID: {0, 1, 2, 3, 4}} (0=週一)
    employee_workdays_map = {}
    for emp in active_employees:
        if emp.work_schedule:
            employee_workdays_map[emp.id] = {rule.day_of_week for rule in emp.work_schedule.rules.all()}
        else:
            employee_workdays_map[emp.id] = set()

    # 抓取日曆範圍內所有已批准的休假
    approved_leaves = LeaveRequest.objects.filter(
        status='Approved',
        start_datetime__date__lte=last_day_of_calendar,
        end_datetime__date__gte=first_day_of_calendar
    ).values_list('employee_id', 'start_datetime', 'end_datetime')
    
    leave_dates_map = {}
    for emp_id, start_dt, end_dt in approved_leaves:
        current_date = start_dt.date()
        while current_date <= end_dt.date():
            leave_dates_map.setdefault(emp_id, set()).add(current_date)
            current_date += timedelta(days=1)

    # 抓取日曆範圍內所有國定假日
    public_holidays = PublicHoliday.objects.filter(date__range=[first_day_of_calendar, last_day_of_calendar])
    public_holidays_map = {h.date: h.name for h in public_holidays}


    # 3. 產生每一天的排班數據
    schedule_data = {}

    for week in month_days:
        for day in week:
            is_holiday = day in public_holidays_map
            schedule_data[day] = {
                'employees': [],
                'summary': {},
                'is_holiday': is_holiday,
                'holiday_name': public_holidays_map.get(day)
            }
            
            if is_holiday:
                continue

            department_counts = {}
            
            for emp in active_employees:
                is_on_leave = emp.id in leave_dates_map and day in leave_dates_map.get(emp.id, set())
                if is_on_leave:
                    continue

                if day.weekday() in employee_workdays_map.get(emp.id, set()):
                    schedule_data[day]['employees'].append({
                        'full_name': emp.user.get_full_name() or emp.user.username,
                        'department_name': department_map.get(emp.department_id, department_map[None])['name'],
                        'department_color': department_map.get(emp.department_id, department_map[None])['color']
                    })
                    department_counts[emp.department_id] = department_counts.get(emp.department_id, 0) + 1

            summary_list = []
            for dept_id, count in department_counts.items():
                summary_list.append({
                    'name': department_map.get(dept_id, department_map[None])['name'],
                    'color': department_map.get(dept_id, department_map[None])['color'],
                    'count': count
                })
            schedule_data[day]['summary'] = sorted(summary_list, key=lambda x: x['name'])

    context = {
        'month_days': month_days,
        'schedule_data': schedule_data,
        'target_date': target_date,
        'prev_month': prev_month,
        'next_month': next_month,
        'today': date.today()
    }
    return render(request, 'core/team_schedule.html', context)

# core/views.py

@login_required
def duty_schedule_view(request):
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]

    active_employees = Employee.objects.filter(status='Active').select_related('user', 'work_schedule')

    # 為了提高效率，預先抓取所有員工的預設班表規則
    for emp in active_employees:
        if emp.work_schedule:
            emp.work_schedule_rules = {rule.day_of_week: rule for rule in emp.work_schedule.rules.all()}
        else:
            emp.work_schedule_rules = {}
            
    # 1. 獲取本週所有已批准的休假 (最高優先級)
    approved_leaves = LeaveRequest.objects.filter(
        status='Approved',
        start_datetime__date__lte=week_dates[-1],
        end_datetime__date__gte=week_dates[0]
    ).select_related('employee')
    
    leave_map = {}
    for leave in approved_leaves:
        current_date = leave.start_datetime.date()
        while current_date <= leave.end_datetime.date():
            if week_dates[0] <= current_date <= week_dates[-1]:
                leave_map.setdefault(leave.employee_id, {})[current_date] = "On Leave"
            current_date += timedelta(days=1)

    # 2. 獲取本週所有手動設定的班次 (次高優先級)
    shifts = DutyShift.objects.filter(date__in=week_dates)
    shift_map = {(s.employee_id, s.date): f"{s.start_time.strftime('%H:%M')}-{s.end_time.strftime('%H:%M')}" for s in shifts}

    # 3. 組合最終的排班數據
    schedule_data = []
    for emp in active_employees:
        employee_schedule = {
            'name': emp.user.get_full_name() or emp.user.username,
            'weekly_status': []
        }
        for day in week_dates:
            status = "Rest Day" # a. 預設為休息日

            # b. 檢查預設班表
            rule = emp.work_schedule_rules.get(day.weekday())
            if rule:
                status = f"{rule.start_time.strftime('%H:%M')}-{rule.end_time.strftime('%H:%M')}"
            
            # c. 檢查手動排班 (會覆蓋預設班表)
            if (emp.id, day) in shift_map:
                status = shift_map[(emp.id, day)]
            
            # d. 檢查休假 (會覆蓋所有其他狀態)
            if emp.id in leave_map and day in leave_map[emp.id]:
                status = leave_map[emp.id][day]
                
            employee_schedule['weekly_status'].append(status)
        
        schedule_data.append(employee_schedule)

    context = {
        'week_dates': week_dates,
        'schedule_data': schedule_data,
    }
    return render(request, 'core/duty_schedule.html', context)

@login_required
def overtime_apply_view(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "您的員工個人資料找不到，無法申請加班。")
        return redirect('core:profile')

    if request.method == 'POST':
        form = OvertimeRequestForm(request.POST)
        if form.is_valid():
            overtime_request = form.save(commit=False)
            overtime_request.employee = employee
            overtime_request.save()
            messages.success(request, '您的加班申請已成功提交！')
            # 可以在這裡加入通知經理的郵件邏輯
            return redirect('core:profile')
    else:
        form = OvertimeRequestForm()

    context = {'form': form}
    return render(request, 'core/overtime_apply.html', context)

# 2. 經理批准加班 View (核心邏輯)
@login_required
def overtime_approve_view(request, request_id):
    # 權限檢查：確保只有該員工的直屬經理才能批准
    ot_request = get_object_or_404(OvertimeRequest, id=request_id, employee__manager__user=request.user)

    if ot_request.status == 'Pending':
        ot_request.status = 'Approved'
        ot_request.save()

        # --- 關鍵：將加班時數轉換為補休，直接加到員工的假期餘額中 ---
        employee = ot_request.employee
        comp_type, _ = LeaveType.objects.get_or_create(name='Compensatory')
        balance, created = LeaveBalance.objects.get_or_create(employee=employee, leave_type=comp_type)
        balance.balance_hours += ot_request.hours
        balance.save()

        messages.success(request, f"{employee.user.username} 的加班申請已批准，{ot_request.hours} 小時已轉為補休。")
        # 可以在這裡加入通知員工的郵件邏輯
    else:
        messages.warning(request, "此申請已被處理過。")

    return redirect('core:manager_dashboard')

# 3. 經理拒絕加班 View
@login_required
def overtime_reject_view(request, request_id):
    ot_request = get_object_or_404(OvertimeRequest, id=request_id, employee__manager__user=request.user)

    if ot_request.status == 'Pending':
        ot_request.status = 'Rejected'
        ot_request.save()
        messages.success(request, f"{ot_request.employee.user.username} 的加班申請已拒絕。")
        # 可以在這裡加入通知員工的郵件邏輯
    else:
        messages.warning(request, "此申請已被處理過。")

    return redirect('core:manager_dashboard')

@login_required
def edit_team_schedule_view(request):
    try:
        manager_employee = Employee.objects.get(user=request.user)
        team_members = Employee.objects.filter(manager=manager_employee, status='Active')
        if not team_members.exists():
            messages.error(request, '您沒有團隊成員可以排班。')
            return redirect('core:manager_dashboard')
    except Employee.DoesNotExist:
        messages.error(request, '您的員工個人資料找不到。')
        return redirect('core:profile')

    # 計算下一週的日期
    today = date.today()
    start_of_next_week = today + timedelta(days=(7 - today.weekday()))
    next_week_dates = [start_of_next_week + timedelta(days=i) for i in range(7)]

    if request.method == 'POST':
        for employee in team_members:
            for day in next_week_dates:
                start_time_str = request.POST.get(f'start_time_{employee.id}_{day.isoformat()}')
                end_time_str = request.POST.get(f'end_time_{employee.id}_{day.isoformat()}')

                # 只有當 start_time 和 end_time 都有值時，才更新或建立班次
                if start_time_str and end_time_str:
                    DutyShift.objects.update_or_create(
                        employee=employee,
                        date=day,
                        defaults={'start_time': start_time_str, 'end_time': end_time_str}
                    )
                else:
                    # 如果輸入框是空的，則刪除該班次
                    DutyShift.objects.filter(employee=employee, date=day).delete()

        messages.success(request, '團隊班表已成功更新！')
        return redirect('core:duty_schedule') # 儲存後導向到值日表查看頁面

    # GET 請求：準備要顯示在表單中的現有數據
    existing_shifts = DutyShift.objects.filter(
        employee__in=team_members,
        date__in=next_week_dates
    )
    # 建立一個方便在樣板中查找的字典
    schedule_map = {(shift.employee_id, shift.date): (shift.start_time, shift.end_time) for shift in existing_shifts}

    context = {
        'team_members': team_members,
        'week_dates': next_week_dates,
        'schedule_map': schedule_map,
    }
    return render(request, 'core/edit_team_schedule.html', context)

def job_board_view(request):
        # 只顯示狀態為 "開放中" 的職缺
        job_openings = JobOpening.objects.filter(status='Open')
        context = {
            'job_openings': job_openings
        }
        return render(request, 'core/job_board.html', context)

    # 2. 職缺詳情與應徵 View
def job_detail_view(request, job_id):
    job = get_object_or_404(JobOpening, id=job_id, status='Open')

    if request.method == 'POST':
        form = CandidateApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            # 檢查此 email 的候選人是否已存在
            candidate, created = Candidate.objects.get_or_create(
                email=form.cleaned_data['email'],
                defaults={
                    'first_name': form.cleaned_data['first_name'],
                    'last_name': form.cleaned_data['last_name'],
                    'phone': form.cleaned_data['phone'],
                    'resume': form.cleaned_data['resume'],
                }
            )
                
            # 檢查是否已應徵過此職位
            if Application.objects.filter(job=job, candidate=candidate).exists():
                messages.warning(request, '您已經應徵過此職位。')
            else:
                Application.objects.create(job=job, candidate=candidate)
                messages.success(request, '您的應徵已成功提交，感謝您！')
                
            return redirect('core:job_board')
    else:
        form = CandidateApplicationForm()

    context = {
        'job': job,
        'form': form,
    }
    return render(request, 'core/job_detail.html', context)
    
# Helper function to get the user's IP address
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# 1. Employee's main attendance page
@login_required
def attendance_view(request):
    employee = get_object_or_404(Employee, user=request.user)
    today = timezone.now().date()
    last_record = AttendanceRecord.objects.filter(employee=employee, clock_in__date=today, clock_out__isnull=True).first()
    todays_records = AttendanceRecord.objects.filter(employee=employee, clock_in__date=today)
    context = {
        'last_record': last_record,
        'todays_records': todays_records,
    }
    return render(request, 'core/attendance.html', context)

# 2. View to handle the clock-in/out action
@login_required
def clock_in_out_view(request):
    if request.method == 'POST':
        employee = get_object_or_404(Employee, user=request.user)
        config = SiteConfiguration.load()
        client_ip = get_client_ip(request)

        allowed_ips = [ip.strip() for ip in config.allowed_ip_addresses.split(',') if ip.strip()]
        if allowed_ips and client_ip not in allowed_ips:
            messages.error(request, f"Error: Your IP address ({client_ip}) is not in the allowed range.")
            return redirect('core:attendance')

        last_record = AttendanceRecord.objects.filter(employee=employee, clock_out__isnull=True).order_by('-clock_in').first()

        if last_record:
            last_record.clock_out = timezone.now()
            last_record.save()
            messages.success(request, 'You have successfully clocked out!')
        else:
            AttendanceRecord.objects.create(
                employee=employee,
                clock_in=timezone.now(),
                ip_address=client_ip
            )
            messages.success(request, 'You have successfully clocked in!')
    return redirect('core:attendance')

# 3. Manager's page for manual attendance entry
@login_required
def manual_attendance_view(request):
    manager = get_object_or_404(Employee, user=request.user)
    team_members = Employee.objects.filter(manager=manager, status='Active')

    if request.method == 'POST':
        employee_id = request.POST.get('employee')
        date_str = request.POST.get('date')
        clock_in_str = request.POST.get('clock_in')
        clock_out_str = request.POST.get('clock_out')
        notes = request.POST.get('notes')

        employee = get_object_or_404(Employee, id=employee_id, manager=manager)

        clock_in_dt = timezone.make_aware(datetime.strptime(f"{date_str} {clock_in_str}", "%Y-%m-%d %H:%M"))
        clock_out_dt = timezone.make_aware(datetime.strptime(f"{date_str} {clock_out_str}", "%Y-%m-%d %H:%M")) if clock_out_str else None

        AttendanceRecord.objects.create(
            employee=employee,
            clock_in=clock_in_dt,
            clock_out=clock_out_dt,
            is_manual_entry=True,
            notes=f"Manually added by manager {manager.user.username}: {notes}"
        )
        messages.success(request, f"Successfully added attendance record for {employee.user.username}.")
        return redirect('core:manual_attendance')

    context = {
        'team_members': team_members
    }
    return render(request, 'core/manual_attendance.html', context)

def is_staff_user(user):
    return user.is_staff

@user_passes_test(is_staff_user)
@login_required
def recruitment_pipeline_view(request, job_id):
    job = get_object_or_404(JobOpening, id=job_id)
    applications = job.applications.all().select_related('candidate').order_by('-applied_at')

    status_choices = Application._meta.get_field('status').choices

    context = {
        'job': job,
        'applications': applications,
        'status_choices': status_choices,
    }
    return render(request, 'core/recruitment_pipeline.html', context)

@user_passes_test(is_staff_user)
@login_required
def update_application_status_view(request, app_id):
    if request.method == 'POST':
        application = get_object_or_404(Application, id=app_id)
        new_status = request.POST.get('status')

        valid_statuses = [choice[0] for choice in Application._meta.get_field('status').choices]
        if new_status in valid_statuses:
            application.status = new_status
            application.save()
            messages.success(request, f"Successfully updated {application.candidate.get_full_name()}'s status to {application.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")

        return redirect('core:recruitment_pipeline', job_id=application.job.id)

    return redirect('core:job_board')

# core/views.py

from .forms import TaxReportForm
from django.db.models import Sum, Q
from decimal import Decimal
import io
from pypdf import PdfReader, PdfWriter
from django.conf import settings
from django.http import HttpResponse

@login_required
def tax_report_view(request):
    if not request.user.is_staff:
        messages.error(request, "您沒有權限訪問此頁面。")
        return redirect('core:profile')

    if request.method == 'POST':
        form = TaxReportForm(request.POST)
        if form.is_valid():
            employee = form.cleaned_data['employee']
            tax_year_start = form.cleaned_data['tax_year']
            tax_year_end = tax_year_start + 1

            # --- 1. Gather Data (Logic remains the same) ---
            start_date = date(tax_year_start, 4, 1)
            end_date = date(tax_year_end, 3, 31)
            config = SiteConfiguration.load()
            
            payslip_items = PayslipItem.objects.filter(
                payslip__employee=employee, item_type='Earning',
                payslip__payroll_run__year__gte=tax_year_start,
                payslip__payroll_run__year__lte=tax_year_end,
            ).filter(
                Q(payslip__payroll_run__year=tax_year_start, payslip__payroll_run__month__gte=4) |
                Q(payslip__payroll_run__year=tax_year_end, payslip__payroll_run__month__lte=3)
            ).values('description').annotate(total=Sum('amount'))

            income = {
                'salary': Decimal('0.00'), 'leave_pay': Decimal('0.00'),
                'bonus': Decimal('0.00'), 'back_pay_etc': Decimal('0.00'),
                'other_allowances': Decimal('0.00'),
            }
            for item in payslip_items:
                desc = item['description'].lower()
                total = item['total'] or Decimal('0.00')
                if 'salary' in desc or '基本薪資' in desc: income['salary'] += total
                elif 'bonus' in desc or '花紅' in desc or 'commission' in desc: income['bonus'] += total
                elif 'leave pay' in desc or '假期薪酬' in desc: income['leave_pay'] += total
                elif 'lieu of notice' in desc or '代通知金' in desc or 'gratuity' in desc or '約滿酬金' in desc:
                    income['back_pay_etc'] += total
                else: income['other_allowances'] += total
            total_income = sum(income.values())
            
            emp_start_in_period = max(employee.hire_date, start_date)
            period_start_str = emp_start_in_period.strftime('%d-%m-%Y')
            period_end_str = end_date.strftime('%d-%m-%Y')

            # --- 2. Build the data dictionary with CORRECT field names ---
            template_path = settings.BASE_DIR / 'core' / 'pdf_templates' / 'ir56b_ay.pdf'
            
            # The keys are now the exact names you provided
            data_to_fill = {
                'Reporting Year': str(tax_year_end),
                'Employer\'s File Number': config.employer_file_number,
                'Name of Employer': config.company_name,
                'Sheet Number': '1',
                'English Surname': employee.user.last_name,
                'English Given Name': employee.user.first_name,
                'HKID Number - Digits': employee.employee_number, # Assumes full HKID is stored here
                'Indicator - Sex': employee.gender[:1] if employee.gender else '', # M or F
                'Indicator - Marital Status': '2' if employee.marital_status == '已婚' else '1',
                'Name of Employee\'s Spouse': employee.spouse_name,
                'Spouse\'s HKID Number or Passport Details': employee.spouse_id_number,
                'Residential Address': employee.residential_address,
                'Postal Address': employee.correspondence_address or employee.residential_address,
                'Capacity Engaged': employee.position.title if employee.position else '',
                
                # Main Employment Period
                'Start Date': period_start_str,
                'End Date': period_end_str,

                # Income Details
                'Amount - Salary / Wages': f"{income['salary']:.2f}",
                'Amount - Leave Pay': f"{income['leave_pay']:.2f}",
                'Amount - Bonus': f"{income['bonus']:.2f}",
                'Amount - Back Pay, Payment in Lieu of Notice, Terminal Awards or Gratuities': f"{income['back_pay_etc']:.2f}",
                'Amount - Other Rewards, Allowances or Perquisites': f"{income['other_allowances']:.2f}",
                'Amount - Total Incomes': f"{total_income:.2f}",

                # Signer Details (can be hardcoded or moved to SiteConfiguration later)
                'Name of Signer': "HR Department",
                'Designation': "Manager",
                'Date of Signing': date.today().strftime('%d-%m-%Y'),
            }
            
            # --- 3. Fill and serve the PDF (Logic remains the same) ---
            try:
                reader = PdfReader(template_path)
                writer = PdfWriter()
                writer.append(reader)
                
                writer.update_page_form_field_values(
                    writer.pages[0], data_to_fill
                )
                
                with io.BytesIO() as bytes_stream:
                    writer.write(bytes_stream)
                    bytes_stream.seek(0)
                    
                    response = HttpResponse(bytes_stream.read(), content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="IR56B_filled_{employee.user.username}_{tax_year_start}.pdf"'
                    return response

            except FileNotFoundError:
                messages.error(request, f"Error: PDF template not found at '{template_path}'.")
                return redirect('core:tax_report')
            except Exception as e:
                messages.error(request, f"An unknown error occurred while generating the PDF: {e}")
                return redirect('core:tax_report')

    else:
        form = TaxReportForm()

    return render(request, 'core/tax_report_form.html', {'form': form})


@login_required
def profile(request):
    try:
        employee = request.user.employee_profile
    except AttributeError:
        # 如果使用者沒有 employee_profile (例如超級使用者)，可以導向到後台或顯示錯誤訊息
        messages.error(request, '無法找到您的員工資料。')
        return redirect('admin:index')

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        employee_form = EmployeeUpdateForm(request.POST, request.FILES, instance=employee)
        if user_form.is_valid() and employee_form.is_valid():
            user_form.save()
            employee_form.save()
            messages.success(request, '您的個人資料已成功更新。')
            # 重新導向回 profile 頁面，以顯示更新後的資料和清除 POST 請求
            return redirect('profile')
        else:
            messages.error(request, '資料更新失敗，請檢查您輸入的內容。')

    else:
        user_form = UserUpdateForm(instance=request.user)
        employee_form = EmployeeUpdateForm(instance=employee)

    # 檢查員工資料是否完整，並顯示提示訊息
    if not employee.is_profile_complete():
        messages.warning(request, '為了啟用所有功能，請您先填寫完整的個人資料。')

    context = {
        'user_form': user_form,
        'employee_form': employee_form
    }
    return render(request, 'core/profile.html', context)

def candidate_data_form_view(request, token):
    # 透過 token 安全地獲取應徵記錄，如果 token 無效則顯示 404
    application = get_object_or_404(Application, token=token)
    candidate = application.candidate

    # 如果已經提交過，直接導向感謝頁面
    if application.personal_data_submitted_at:
        return render(request, 'core/candidate_data_thanks.html')

    if request.method == 'POST':
        form = CandidateDataForm(request.POST, instance=candidate)
        if form.is_valid():
            form.save()
            application.personal_data_submitted_at = timezone.now()
            application.save()
            return render(request, 'core/candidate_data_thanks.html')
    else:
        form = CandidateDataForm(instance=candidate)

    context = {
        'form': form,
        'candidate_name': candidate.get_full_name(),
        'job_title': application.job.title
    }
    return render(request, 'core/candidate_data_form.html', context)