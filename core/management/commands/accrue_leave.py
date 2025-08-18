from django.core.management.base import BaseCommand
from core.models import Employee, LeavePolicy, PolicyRule
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Accrues annual leave for all active employees based on their policies.'

    def handle(self, *args, **kwargs):
        today = date.today()
        active_employees = Employee.objects.filter(status='Active', leave_policy__isnull=False)

        self.stdout.write(f"Starting leave accrual process for {active_employees.count()} employees...")

        for emp in active_employees:
            policy = emp.leave_policy

            policy_start_date = emp.hire_date
            if policy.waiting_period_unit == 'DAYS':
                policy_start_date += timedelta(days=policy.waiting_period_amount)
            elif policy.waiting_period_unit == 'MONTHS':
                policy_start_date += relativedelta(months=policy.waiting_period_amount)

            # 如果今天還沒到策略生效日，就跳過這位員工
            if today < policy_start_date:
                self.stdout.write(f"  - Skipping employee {emp.id}: Still in waiting period (policy starts on {policy_start_date}).")
                continue
            # --- 🔼 等待期檢查邏輯結束 🔼 ---


            # 1. 基礎權責增加 (例如：每日/每月/每年)
            accrual_to_add = Decimal(0)
            if (policy.accrual_frequency == 'DAILY' or 
               (policy.accrual_frequency == 'WEEKLY' and today.weekday() == 0) or # 每週一
               (policy.accrual_frequency == 'MONTHLY' and today.day == 1) or # 每月一號
               (policy.accrual_frequency == 'YEARLY' and today.month == 1 and today.day == 1)): # 每年一月一號

                amount = policy.accrual_amount
                if policy.accrual_unit == 'DAYS':
                    amount *= 8 # 假設一天 8 小時
                accrual_to_add += amount

            # 2. 年資門檻增加
            years_of_service = today.year - emp.hire_date.year - ((today.month, today.day) < (emp.hire_date.month, emp.hire_date.day))

            # 檢查今天是否剛好是員工的入職週年日
            if today.month == emp.hire_date.month and today.day == emp.hire_date.day:
                rule = policy.rules.filter(years_of_service=years_of_service).first()
                if rule:
                    adjustment = rule.adjustment_amount
                    if policy.accrual_unit == 'DAYS': # 規則的單位跟隨策略
                        adjustment *= 8

                    # 這裡可以根據 rule_type 做不同操作，我們先簡化為 ADD
                    accrual_to_add += adjustment
                    self.stdout.write(f"  - Employee {emp.id} reached {years_of_service} years, applying rule: +{adjustment} hours.")

            # 3. 更新員工結餘
            if accrual_to_add > 0:
                # 假設年度權責只增加 'al' (年假)
                al_type = LeaveType.objects.get(name='al') 
                balance, created = LeaveBalance.objects.get_or_create(employee=emp, leave_type=al_type)
                balance.balance_hours += accrual_to_add
                balance.save()
                self.stdout.write(f"  - Accrued {accrual_to_add} hours of Annual Leave for employee {emp.id}.")


self.stdout.write("Leave accrual process finished.")