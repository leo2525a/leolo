# core/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.db import models
from decimal import Decimal
from datetime import timedelta, datetime, date
from ckeditor.fields import RichTextField
import holidays


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="部門名稱")
    description = models.TextField(blank=True, null=True, verbose_name="部門描述")

    def __str__(self):
        return self.name

class Position(models.Model):
    title = models.CharField(max_length=255, unique=True, verbose_name="職位名稱")
    description = models.TextField(blank=True, null=True, verbose_name="職位描述")

    def __str__(self):
        return self.title

# 1. 年假策略主表 (例如："正職員工年假策略", "高階主管年假策略")
# core/models.py

class LeavePolicy(models.Model):
    ACCRUAL_FREQUENCY_CHOICES = (
        ('DAILY', '每日'),
        ('WEEKLY', '每週'),
        ('MONTHLY', '每月'),
        ('YEARLY', '每年'),
    )
    UNIT_CHOICES = (
        ('HOURS', '小時'),
        ('DAYS', '天'),
    )
    WAITING_PERIOD_UNIT_CHOICES = (
        ('DAYS', '天'),
        ('MONTHS', '個月'),
    )

    MONTH_CHOICES = [(i, f"{i}月") for i in range(1, 13)]

    name = models.CharField(max_length=255, unique=True, verbose_name="策略名稱")
    description = models.TextField(blank=True, verbose_name="策略描述")

    # --- 👇 在下方新增年度結算設定 ---
    fiscal_year_start_month = models.IntegerField(
        choices=MONTH_CHOICES, 
        default=1, 
        verbose_name="假期年度起始月份"
    )
    allow_carry_over = models.BooleanField(default=False, verbose_name="允許結轉未使用假期")
    max_carry_over_amount = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0, 
        verbose_name="最大可結轉數量"
    )
    # 結轉的單位與權責發生的單位 (accrual_unit) 保持一致

    waiting_period_amount = models.PositiveIntegerField(default=0, verbose_name="等待期數量")
    waiting_period_unit = models.CharField(max_length=10, choices=WAITING_PERIOD_UNIT_CHOICES, default='DAYS', verbose_name="等待期單位")

    # 權責發生制設定
    accrual_frequency = models.CharField(max_length=10, choices=ACCRUAL_FREQUENCY_CHOICES, default='YEARLY', verbose_name="增加頻率")
    accrual_amount = models.DecimalField(max_digits=5, decimal_places=2, default=12, verbose_name="每次增加的數量")
    accrual_unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='DAYS', verbose_name="單位")

    # 其他設定 (未來可擴充)
    # max_carry_over = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="最大可結轉時數/天數")

    def __str__(self):
        return self.name

class PolicyRule(models.Model):
    RULE_TYPE_CHOICES = (
        ('ADD', '增加固定值'),
        ('SET', '設定為新總數'),
        # ('PERCENTAGE', '增加百分比'), # 百分比邏輯較複雜，先註解
    )

    policy = models.ForeignKey(LeavePolicy, on_delete=models.CASCADE, related_name='rules', verbose_name="所屬策略")
    years_of_service = models.PositiveIntegerField(verbose_name="服務年資滿 (年)")

    # 規則效果
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES, default='ADD', verbose_name="規則類型")
    adjustment_amount = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="調整的數量 (小時/天)")

    class Meta:
        ordering = ['years_of_service']

    def __str__(self):
        return f"{self.policy.name}: 滿 {self.years_of_service} 年 -> {self.get_rule_type_display()} {self.adjustment_amount} {self.policy.get_accrual_unit_display()}"

# 1. 工作班表主表 (例如："標準週一至週五班", "週末輪班")
class WorkSchedule(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="班表名稱")
    description = models.TextField(blank=True, verbose_name="描述")

    def __str__(self):
        return self.name

# 2. 班表的具體規則
class ScheduleRule(models.Model):
    WEEKDAY_CHOICES = (
        (0, '星期一'), (1, '星期二'), (2, '星期三'),
        (3, '星期四'), (4, '星期五'), (5, '星期六'), (6, '星期日'),
    )
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.CASCADE, related_name='rules')
    day_of_week = models.IntegerField(choices=WEEKDAY_CHOICES, verbose_name="星期幾")
    start_time = models.TimeField(verbose_name="上班時間")
    end_time = models.TimeField(verbose_name="下班時間")

    class Meta:
        unique_together = ('schedule', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        return f"{self.schedule.name}: {self.get_day_of_week_display()} ({self.start_time}-{self.end_time})"

class Employee(models.Model):
    STATUS_CHOICES = (
        ('Active', '在職'),
        ('Inactive', '離職'),
    )
    GENDER_CHOICES = (
        ('Male', '男性'),
        ('Female', '女性'),
        ('Other', '其他'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="登入帳號")
    employee_number = models.CharField(max_length=50, unique=True, verbose_name="員工編號")
    phone_number = models.CharField(max_length=50, blank=True, verbose_name="電話")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, verbose_name="性別")
    hire_date = models.DateField(verbose_name="入職日期")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所屬部門")
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="擔任職位")
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="直屬主管", related_name='manager_of') # <-- 加上 related_name
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', verbose_name="狀態")
    leave_policy = models.ForeignKey(LeavePolicy, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="年假策略")
    compensatory_leave_balance_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0, verbose_name="補休餘額 (小時)")
    work_schedule = models.ForeignKey(WorkSchedule, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="預設班表")
    

    
    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.employee_number})"

    def get_current_salary(self):
        """
        獲取該員工最新的、已生效的薪資記錄。
        """
        return self.salary_history.filter(effective_date__lte=date.today()).order_by('-effective_date').first()

class SalaryHistory(models.Model):
    CHANGE_REASON_CHOICES = (
        ('New Hire', '新進人員'),
        ('Promotion', '晉升'),
        ('Annual Review', '年度調薪'),
        ('Market Adjustment', '市場調整'),
        ('Other', '其他'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_history', verbose_name="員工")
    effective_date = models.DateField(verbose_name="生效日期")
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="基本薪資")
    change_reason = models.CharField(max_length=50, choices=CHANGE_REASON_CHOICES, verbose_name="變動原因")
    notes = models.TextField(blank=True, verbose_name="備註")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        verbose_name = "薪資歷史"
        verbose_name_plural = "薪資歷史"

    def __str__(self):
        return f"{self.employee.user.username} - {self.base_salary} as of {self.effective_date}"


class LeaveType(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="假別名稱")
    # 您可以未來再擴充，例如加入每年預設天數等

    def __str__(self):
        return self.name

class LeaveRequest(models.Model):
    STATUS_CHOICES = (('Pending', '待審核'), ('Approved', '已批准'), ('Rejected', '已拒絕'))

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="申請員工")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, verbose_name="假別")
    start_datetime = models.DateTimeField(verbose_name="開始時間")
    end_datetime = models.DateTimeField(verbose_name="結束時間")
    reason = models.TextField(verbose_name="事由")
    duration_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="總時數 (小時)")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending', verbose_name="審核狀態")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="申請時間")

    def calculate_work_hours(self):
        """
        Calculates the actual work hours to be deducted, skipping non-work days.
        """
        if not self.employee.work_schedule:
            time_difference = self.end_datetime - self.start_datetime
            return round(time_difference.total_seconds() / 3600, 2)

        total_hours = Decimal(0)
        
        schedule_rules = {rule.day_of_week: rule for rule in self.employee.work_schedule.rules.all()}
        public_holidays = set(PublicHoliday.objects.filter(
            date__range=[self.start_datetime.date(), self.end_datetime.date()]
        ).values_list('date', flat=True))

        current_day = self.start_datetime.date()
        while current_day <= self.end_datetime.date():
            if current_day in public_holidays:
                current_day += timedelta(days=1)
                continue

            rule = schedule_rules.get(current_day.weekday())
            if not rule:
                current_day += timedelta(days=1)
                continue

            # 👇 Corrected block: Make datetime objects timezone-aware before comparing
            shift_start = timezone.make_aware(datetime.combine(current_day, rule.start_time))
            shift_end = timezone.make_aware(datetime.combine(current_day, rule.end_time))
            
            leave_start_on_day = max(self.start_datetime, shift_start)
            leave_end_on_day = min(self.end_datetime, shift_end)

            if leave_start_on_day < leave_end_on_day:
                duration_on_day = leave_end_on_day - leave_start_on_day
                total_hours += Decimal(duration_on_day.total_seconds() / 3600)
            
            current_day += timedelta(days=1)
        
        return round(total_hours, 2)


    def save(self, *args, **kwargs):
    # 現在，所有假別都會呼叫 calculate_work_hours() 進行智慧計算
        self.duration_hours = self.calculate_work_hours()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} 的 {self.leave_type.name} 申請"

class EmployeeDocument(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents', verbose_name="所屬員工")
    title = models.CharField(max_length=255, verbose_name="文件標題")
    file = models.FileField(upload_to='employee_documents/', verbose_name="文件")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上傳時間")

    def __str__(self):
        return f"{self.employee.user.username} - {self.title}"

class ReviewCycle(models.Model):
    name = models.CharField(max_length=255, verbose_name="評估週期名稱")
    start_date = models.DateField(verbose_name="開始日期")
    end_date = models.DateField(verbose_name="結束日期")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    def __str__(self):
        return self.name

# 2. 績效評估主表 (將員工和評估週期連結起來)
class PerformanceReview(models.Model):
    RATING_CHOICES = (
        (1, '1 - 不符合期望'),
        (2, '2 - 需改進'),
        (3, '3 - 符合期望'),
        (4, '4 - 超越期望'),
        (5, '5 - 表現卓越'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='reviews', verbose_name="受評員工")
    cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name='reviews', verbose_name="評估週期")
    employee_self_assessment = models.TextField(blank=True, null=True, verbose_name="員工自評")
    manager_assessment = models.TextField(blank=True, null=True, verbose_name="經理評語")
    overall_rating = models.IntegerField(choices=RATING_CHOICES, blank=True, null=True, verbose_name="總體評分")
    status = models.CharField(max_length=20, default='Pending', verbose_name="狀態") # 例如：Pending, In Progress, Completed

    class Meta:
        # 確保同一位員工在同一個評估週期中只有一筆記錄
        unique_together = ('employee', 'cycle')

    def __str__(self):
        return f"{self.employee}'s review for {self.cycle}"

# 3. 個人目標 (與某次績效評估關聯)
class Goal(models.Model):
    review = models.ForeignKey(PerformanceReview, on_delete=models.CASCADE, related_name='goals', verbose_name="所屬評估")
    description = models.TextField(verbose_name="目標描述")
    is_achieved = models.BooleanField(default=False, verbose_name="是否達成")

    def __str__(self):
        return self.description[:50] # 顯示目標描述的前50個字


class Announcement(models.Model):
    title = models.CharField(max_length=255, verbose_name="公告標題")
    content = models.TextField(verbose_name="公告內容")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="發布者")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="發布時間")
    is_published = models.BooleanField(default=True, verbose_name="是否發布")

    class Meta:
        ordering = ['-created_at'] # 預設按發布時間倒序排列

    def __str__(self):
        return self.title

# 1. 入職清單樣板
class OnboardingChecklist(models.Model):
    name = models.CharField(max_length=255, verbose_name="清單樣板名稱")
    description = models.TextField(blank=True, verbose_name="描述")
    tasks = models.TextField(verbose_name="任務列表 (每行一項)")

    def __str__(self):
        return self.name

# 2. 指派給員工的具體任務
class EmployeeTask(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='onboarding_tasks', verbose_name="所屬員工")
    task_description = models.CharField(max_length=255, verbose_name="任務描述")
    is_completed = models.BooleanField(default=False, verbose_name="是否完成")
    due_date = models.DateField(blank=True, null=True, verbose_name="截止日期")

    class Meta:
        ordering = ['is_completed', 'id']

    def __str__(self):
        return f"{self.employee.user.username} - {self.task_description}"

class SiteConfiguration(models.Model):
    # 郵件設定
    email_host = models.CharField(max_length=255, default='smtp.gmail.com', verbose_name="郵件主機 (Host)")
    email_port = models.PositiveIntegerField(default=587, verbose_name="郵件端口 (Port)")
    email_use_tls = models.BooleanField(default=True, verbose_name="使用 TLS")
    email_host_user = models.EmailField(blank=True, verbose_name="發信人 Email")
    email_host_password = models.CharField(max_length=255, blank=True, verbose_name="發信人密碼 (應用程式密碼)")
    company_logo = models.ImageField(upload_to='logos/', blank=True, null=True, verbose_name="公司 Logo")

    allowed_ip_addresses = models.TextField(
        blank=True, 
        verbose_name="公司允許的 IP 位址",
        help_text="請輸入公司允許打卡的 IP 位址，多個位址請用逗號分隔 (例如: 192.168.1.100, 203.0.113.5)"
    )

    def __str__(self):
        return "系統組態"

    # 這裡是實現單例模式的魔法
    def save(self, *args, **kwargs):
        self.pk = 1 # 將主鍵永遠設為 1
        super(SiteConfiguration, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # 防止刪除
        pass

    @classmethod
    def load(cls):
        # 方便我們在程式中隨時取得唯一的設定實例
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

# core/models.py

class DutyShift(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='shifts')
    date = models.DateField(verbose_name="日期")
    start_time = models.TimeField(verbose_name="上班時間")
    end_time = models.TimeField(verbose_name="下班時間")

    class Meta:
        unique_together = ('employee', 'date') # 確保一位員工一天只有一筆排班

    def __str__(self):
        return f"{self.employee} on {self.date}: {self.start_time}-{self.end_time}"

# core/models.py
class OvertimeRequest(models.Model):
    STATUS_CHOICES = (('Pending', '待審核'), ('Approved', '已批准'), ('Rejected', '已拒絕'))

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField(verbose_name="加班日期")
    hours = models.DecimalField(max_digits=4, decimal_places=2, verbose_name="加班時數")
    reason = models.TextField(verbose_name="加班事由")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee} - {self.date} ({self.hours} hours)"

class PublicHoliday(models.Model):
    name = models.CharField(max_length=255, verbose_name="假期名稱")
    date = models.DateField(unique=True, verbose_name="日期")

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.date}: {self.name}"

# core/models.py
class LeaveBalanceAdjustment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    hours_changed = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee}: {self.hours_changed} hours for {self.reason}"

class ContractTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name="樣板名稱")
    # 2. Change the field type here
    body = RichTextField(verbose_name="樣板內容")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class JobOpening(models.Model):
    STATUS_CHOICES = (
        ('Draft', '草稿'),
        ('Open', '開放中'),
        ('Closed', '已關閉'),
    )
    title = models.CharField(max_length=255, verbose_name="職位名稱")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所屬部門")
    description = RichTextField(verbose_name="職位描述")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Draft', verbose_name="狀態")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

# 2. 候選人模型
class Candidate(models.Model):
    first_name = models.CharField(max_length=100, verbose_name="名字")
    last_name = models.CharField(max_length=100, verbose_name="姓氏")
    email = models.EmailField(unique=True, verbose_name="Email")
    phone = models.CharField(max_length=50, blank=True, verbose_name="電話")
    resume = models.FileField(upload_to='resumes/', verbose_name="履歷檔案")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.get_full_name()

# 3. 應徵記錄模型 (連結職缺與候選人)
class Application(models.Model):
    STATUS_CHOICES = (
        ('Applied', '已應徵'),
        ('Screening', '篩選中'),
        ('Interview', '面試'),
        ('Offered', '已提供 Offer'),
        ('Hired', '已錄用'),
        ('Rejected', '未錄取'),
    )
    job = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name='applications')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='applications')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Applied', verbose_name="應徵狀態")
    applied_at = models.DateTimeField(auto_now_add=True, verbose_name="應徵時間")
    notes = models.TextField(blank=True, verbose_name="內部備註")

    class Meta:
        unique_together = ('job', 'candidate') # 確保同一位候選人對同一個職位只能應徵一次

    def __str__(self):
        return f"{self.candidate} for {self.job}"

class AttendanceRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records', verbose_name="員工")
    clock_in = models.DateTimeField(verbose_name="上班打卡時間")
    clock_out = models.DateTimeField(null=True, blank=True, verbose_name="下班打卡時間")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="打卡 IP 位址")
    is_manual_entry = models.BooleanField(default=False, verbose_name="是否為手動補登")
    notes = models.CharField(max_length=255, blank=True, verbose_name="備註 (手動補登)")

    class Meta:
        ordering = ['-clock_in']

    def __str__(self):
        return f"{self.employee} on {self.clock_in.date()}"

class PayrollRun(models.Model):
    STATUS_CHOICES = (
        ('Draft', '草稿'),
        ('Generated', '已生成'),
        ('Paid', '已支付'),
    )
    month = models.IntegerField(verbose_name="月份")
    year = models.IntegerField(verbose_name="年份")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Draft', verbose_name="狀態")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('month', 'year')
        ordering = ['-year', '-month']
        verbose_name = "發薪週期"
        verbose_name_plural = "發薪週期"

    def __str__(self):
        return f"{self.year}年 {self.month}月 薪資"

# 2. 個人薪資單模型
class Payslip(models.Model):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips', verbose_name="發薪週期")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payslips', verbose_name="員工")
    
    # 匯總欄位
    gross_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="應發薪資 (Gross)")
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="總扣款")
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="實發薪資 (Net)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('payroll_run', 'employee')
        verbose_name = "薪資單"
        verbose_name_plural = "薪資單"

    def __str__(self):
        return f"{self.employee}'s payslip for {self.payroll_run}"

# 3. 薪資單項目模型 (收入或扣款)
class PayslipItem(models.Model):
    ITEM_TYPE_CHOICES = (
        ('Earning', '收入'),
        ('Deduction', '扣款'),
    )
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES, verbose_name="項目類型")
    description = models.CharField(max_length=255, verbose_name="描述")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="金額")

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.description} ({self.amount})"

class PayrollConfiguration(models.Model):
    epf_employee_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.11, verbose_name="員工 EPF 費率 (例如 0.11)")
    epf_employer_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.13, verbose_name="僱主 EPF 費率 (例如 0.13)")
    socso_employee_amount = models.DecimalField(max_digits=7, decimal_places=2, default=19.75, verbose_name="員工 SOCSO 金額 (固定值)")
    # 您可以繼續新增 EIS, Employer SOCSO 等欄位

    class Meta:
        verbose_name = "薪資組態"
        verbose_name_plural = "薪資組態"

    def __str__(self):
        return "薪資組態"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(PayrollConfiguration, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class LeaveBalance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    balance_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0, verbose_name="剩餘時數")

    class Meta:
        unique_together = ('employee', 'leave_type') # 確保每個員工對每種假別只有一筆餘額記錄
        verbose_name = "假期餘額"
        verbose_name_plural = "假期餘額"

    def __str__(self):
        return f"{self.employee.user.username} - {self.leave_type.name}: {self.balance_hours} hours"