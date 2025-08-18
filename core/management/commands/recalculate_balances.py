from django.core.management.base import BaseCommand
from core.models import Employee
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Recalculates the total accrued leave balance for one or all employees from their start date.'

    def add_arguments(self, parser):
        # 新增一個可選的指令行參數 --employee_id
        parser.add_argument(
            '--employee_id',
            type=int,
            help='Recalculate balance for a specific employee ID.',
        )

    def handle(self, *args, **kwargs):
        employee_id = kwargs.get('employee_id')

        if employee_id:
            employees = Employee.objects.filter(id=employee_id, status='Active', leave_policy__isnull=False)
            if not employees.exists():
                self.stdout.write(self.style.ERROR(f"No active employee found with ID {employee_id} and an assigned policy."))
                return
        else:
            employees = Employee.objects.filter(status='Active', leave_policy__isnull=False)

        self.stdout.write(f"Starting balance recalculation for {employees.count()} employee(s)...")

        for emp in employees:
            policy = emp.leave_policy
            today = date.today()

            # 1. 決定計算的起始日期 (等待期結束後)
            start_date = emp.hire_date
            if policy.waiting_period_unit == 'DAYS':
                start_date += timedelta(days=policy.waiting_period_amount)
            elif policy.waiting_period_unit == 'MONTHS':
                start_date += relativedelta(months=policy.waiting_period_amount)

            if start_date > today:
                self.stdout.write(self.style.WARNING(f"  - Employee {emp.id}: Policy has not started yet. Balance set to 0."))
                emp.annual_leave_balance_hours = 0
                emp.save()
                continue

            total_accrued = Decimal(0)

            # 2. 模擬從起始日到今天，遍歷每一個權責發生週期
            current_date = start_date
            while current_date <= today:
                # 基礎權責增加
                if (policy.accrual_frequency == 'DAILY' or
                   (policy.accrual_frequency == 'WEEKLY' and current_date.weekday() == 0) or
                   (policy.accrual_frequency == 'MONTHLY' and current_date.day == 1) or
                   (policy.accrual_frequency == 'YEARLY' and current_date.month == 1 and current_date.day == 1)):

                    amount = policy.accrual_amount
                    if policy.accrual_unit == 'DAYS':
                        amount *= 8 # 假設 1 天 8 小時
                    total_accrued += amount

                # 年資門檻增加 (只在週年日當天計算)
                years_of_service = current_date.year - emp.hire_date.year - ((current_date.month, current_date.day) < (emp.hire_date.month, emp.hire_date.day))
                if current_date.month == emp.hire_date.month and current_date.day == emp.hire_date.day and years_of_service > 0:
                    rule = policy.rules.filter(years_of_service=years_of_service).first()
                    if rule:
                        adjustment = rule.adjustment_amount
                        if policy.accrual_unit == 'DAYS':
                            adjustment *= 8
                        total_accrued += adjustment

                current_date += timedelta(days=1)

            # 3. 直接設定員工的餘額為計算出的總數
            emp.annual_leave_balance_hours = total_accrued
            emp.save()
            self.stdout.write(self.style.SUCCESS(f"  - Employee {emp.id}: Balance recalculated to {total_accrued:.2f} hours."))

        self.stdout.write("Balance recalculation finished.")