# core/management/commands/compensate_holidays.py

from django.core.management.base import BaseCommand
from core.models import Employee, PublicHoliday, LeaveBalanceAdjustment
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta # 👈 確保頂部有這個 import

class Command(BaseCommand):
    help = 'Grants compensatory leave if a public holiday falls on an employee\'s rest day and they have passed the waiting period.'

    def handle(self, *args, **kwargs):
        # 我們檢查昨天的日期，這樣可以確保假日已經過去
        yesterday = date.today() - timedelta(days=1)

        holiday = PublicHoliday.objects.filter(date=yesterday).first()
        if not holiday:
            self.stdout.write(f"({yesterday}) Not a public holiday. No action taken.")
            return

        self.stdout.write(f"Found public holiday: {holiday.name} on {yesterday}. Checking employees for compensatory leave...")

        employees_with_schedule = Employee.objects.filter(status='Active', work_schedule__isnull=False)

        for emp in employees_with_schedule:
            # --- 👇 新增等待期和年資檢查 👇 ---
            # 1. 計算員工的服務月數
            service_duration = relativedelta(yesterday, emp.hire_date)
            service_months = service_duration.years * 12 + service_duration.months

            # 2. 檢查服務月數是否已達到福利等待期
            if service_months < emp.compensatory_leave_eligible_after_months:
                self.stdout.write(f"  - Skipping {emp.user.username}: Has not met the waiting period of {emp.compensatory_leave_eligible_after_months} months.")
                continue
            # --- 🔼 檢查結束 🔼 ---

            # 檢查昨天是否為該員工的休息日
            weekday = yesterday.weekday()
            is_rest_day = not emp.work_schedule.rules.filter(day_of_week=weekday).exists()

            if is_rest_day:
                # 假設補假時數為該員工一天的標準工時，如果沒有則預設為 8 小時
                compensation_hours = 8.0 
                rule = emp.work_schedule.rules.first() # 嘗試獲取一個規則來計算工時
                if rule:
                    duration = datetime.combine(date.today(), rule.end_time) - datetime.combine(date.today(), rule.start_time)
                    compensation_hours = duration.total_seconds() / 3600

                # 更新員工餘額
                emp.annual_leave_balance_hours += compensation_hours
                emp.save()

                # 建立稽核記錄
                LeaveBalanceAdjustment.objects.create(
                    employee=emp,
                    hours_changed=compensation_hours,
                    reason=f"Compensatory leave for {holiday.name} on rest day"
                )
                self.stdout.write(self.style.SUCCESS(f"  - Granted {compensation_hours:.2f} hours to {emp.user.username}."))

        self.stdout.write("Holiday compensation check finished.")