# core/management/commands/update_annual_leave.py

from django.core.management.base import BaseCommand
from django.db import transaction, models
from core.models import Employee, PublicHoliday, LeaveType, LeaveBalance, LeaveBalanceAdjustment
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Recalculates and adjusts annual leave balances, including policy entitlement and holiday compensation.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='The year to process for all calculations. Defaults to the current year.'
        )

    def _get_daily_work_hours(self, employee):
        if not employee.work_schedule or not employee.work_schedule.rules.exists():
            return Decimal('8.00')
        rule = employee.work_schedule.rules.first()
        start_dt = datetime.combine(date.today(), rule.start_time)
        end_dt = datetime.combine(date.today(), rule.end_time)
        duration_seconds = (end_dt - start_dt).total_seconds()
        hours = Decimal(duration_seconds / 3600)
        if hours > 5:
            hours -= 1
        return hours if hours > 0 else Decimal('8.00')

    @transaction.atomic
    def handle(self, *args, **options):
        year = options['year']
        today = date.today()
        self.stdout.write(self.style.SUCCESS(f"--- Starting Annual Leave Update for {year} ---"))

        try:
            annual_leave_type = LeaveType.objects.get(name__iexact='Annual Leave')
        except LeaveType.DoesNotExist:
            self.stdout.write(self.style.ERROR("FATAL: 'Annual Leave' type not found. Please create it first."))
            return

        public_holidays = PublicHoliday.objects.filter(date__year=year)
        active_employees = Employee.objects.filter(status='Active', leave_policy__isnull=False)

        if not active_employees.exists():
            self.stdout.write(self.style.WARNING("No active employees with a leave policy found. Exiting."))
            return

        self.stdout.write(f"Found {active_employees.count()} active employee(s) to process.\n")

        for employee in active_employees:
            policy = employee.leave_policy
            self.stdout.write(f"Processing Employee: {employee.user.get_full_name()} (ID: {employee.id})")

            daily_hours = self._get_daily_work_hours(employee)
            self.stdout.write(f"  - Employee's daily work hours calculated as: {daily_hours} hours.")

            service_duration = relativedelta(today, employee.hire_date)
            years_of_service = service_duration.years
            
            base_entitlement_units = policy.accrual_amount
            rule_adjustment = Decimal('0.0')
            applicable_rule = policy.rules.filter(years_of_service__lte=years_of_service).order_by('-years_of_service').first()

            if applicable_rule:
                if applicable_rule.rule_type == 'ADD':
                    rule_adjustment = applicable_rule.adjustment_amount
                elif applicable_rule.rule_type == 'SET':
                    base_entitlement_units = applicable_rule.adjustment_amount
            
            total_entitlement_units = base_entitlement_units + rule_adjustment
            
            base_hours = total_entitlement_units
            if policy.accrual_unit == 'DAYS':
                base_hours = total_entitlement_units * daily_hours
            
            self.stdout.write(f"  - Policy Entitlement: {base_hours:.2f} hours")

            # --- 【↓↓↓ 在這裡加入檢查邏輯 ↓↓↓】 ---
            holiday_compensation_hours = Decimal('0.00')
            if not policy.enable_holiday_compensation:
                self.stdout.write(self.style.WARNING(f"  - Skipping holiday compensation: Disabled in '{policy.name}' policy."))
            elif not public_holidays.exists():
                self.stdout.write(self.style.WARNING(f"  - Skipping holiday compensation: No public holidays found for {year}."))
            elif not employee.work_schedule:
                self.stdout.write(self.style.WARNING(f"  - Skipping holiday compensation: No work schedule assigned."))
            else:
                work_days = set(employee.work_schedule.rules.values_list('day_of_week', flat=True))
                
                for holiday in public_holidays:
                    if holiday.date.weekday() not in work_days:
                        _, created = LeaveBalanceAdjustment.objects.get_or_create(
                            employee=employee,
                            leave_type=annual_leave_type,
                            reason=f"Holiday Compensation: {holiday.name} on {holiday.date}",
                            defaults={'hours_changed': daily_hours}
                        )
                        if created:
                           self.stdout.write(self.style.NOTICE(f"  - Logged {daily_hours} hours compensation for holiday: {holiday.name}"))
                        holiday_compensation_hours += daily_hours
            
            self.stdout.write(f"  - Holiday Compensation for {year}: {holiday_compensation_hours:.2f} hours")

            target_total_hours = base_hours + holiday_compensation_hours
            balance, _ = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave_type
            )
            
            current_balance = balance.balance_hours
            adjustment_needed = target_total_hours - current_balance

            self.stdout.write(f"  - Target Balance: {target_total_hours:.2f} hours. Current Balance: {current_balance:.2f} hours.")

            if adjustment_needed != 0:
                balance.balance_hours += adjustment_needed
                balance.save()
                LeaveBalanceAdjustment.objects.create(
                    employee=employee,
                    leave_type=annual_leave_type,
                    reason=f"Annual balance update for {year}. Adjusted from {current_balance} to {target_total_hours}.",
                    hours_changed=adjustment_needed
                )
                self.stdout.write(self.style.SUCCESS(f"  - SUCCESS: Adjusted balance by {adjustment_needed:.2f} hours. New balance is {balance.balance_hours:.2f} hours.\n"))
            else:
                self.stdout.write(self.style.SUCCESS("  - SUCCESS: No adjustment needed. Balance is already correct.\n"))

        self.stdout.write(self.style.SUCCESS("--- Annual Leave Update Finished ---"))