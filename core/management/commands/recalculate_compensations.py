# core/management/commands/recalculate_compensations.py
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Employee, PublicHoliday, LeaveBalanceAdjustment
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Recalculates and grants compensatory leave for an entire year.'

    def add_arguments(self, parser):
        # 新增一個可選的 --year 參數
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='The year to recalculate compensations for. Defaults to the current year.',
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        year = kwargs['year']
        self.stdout.write(self.style.SUCCESS(f"--- Starting Compensatory Leave Recalculation for {year} ---"))

        holidays_in_year = PublicHoliday.objects.filter(date__year=year)
        if not holidays_in_year.exists():
            self.stdout.write(self.style.WARNING(f"No public holidays found for {year}. Aborting."))
            return

        eligible_employees = Employee.objects.filter(status='Active', work_schedule__isnull=False)

        reason_filter = f"Compensatory leave for {year}"
        old_adjustments = LeaveBalanceAdjustment.objects.filter(reason__startswith=reason_filter)
        if old_adjustments.exists():
            self.stdout.write(f"Clearing {old_adjustments.count()} old compensation records for {year}...")
            for adj in old_adjustments:
                adj.employee.compensatory_leave_balance_hours -= adj.hours_changed
                adj.employee.save()
            old_adjustments.delete()

        for emp in eligible_employees:
            self.stdout.write(f"\nProcessing employee: {emp.user.username}")
            # Initialize as a Decimal
            total_compensation_for_year = Decimal('0.0')

            for holiday in holidays_in_year:
                service_duration = relativedelta(holiday.date, emp.hire_date)
                service_months = service_duration.years * 12 + service_duration.months
                if service_months < emp.compensatory_leave_eligible_after_months:
                    continue

                weekday = holiday.date.weekday()
                is_rest_day = not emp.work_schedule.rules.filter(day_of_week=weekday).exists()

                if is_rest_day:
                    compensation_hours = Decimal("8.0") 
                    rule = emp.work_schedule.rules.first()
                    if rule:
                        duration = datetime.combine(date.today(), rule.end_time) - datetime.combine(date.today(), rule.start_time)
                        # Convert the calculated hours to Decimal
                        compensation_hours = Decimal(duration.total_seconds() / 3600)

                    total_compensation_for_year += compensation_hours

                    LeaveBalanceAdjustment.objects.create(
                        employee=emp,
                        hours_changed=compensation_hours,
                        reason=f"Compensatory leave for {year}: {holiday.name}"
                    )
                    self.stdout.write(f"  - Qualifies for {holiday.name} (+{compensation_hours:.2f} hours)")

            if total_compensation_for_year > 0:
                # 假設補休的假別名稱為 'Compensatory'
                comp_type, _ = LeaveType.objects.get_or_create(name='Compensatory')
                balance, created = LeaveBalance.objects.get_or_create(employee=emp, leave_type=comp_type)
                balance.balance_hours += total_compensation_for_year
                balance.save()
                self.stdout.write(self.style.SUCCESS(f"  -> Total compensation for {year} granted: {total_compensation_for_year:.2f} hours."))

        self.stdout.write(self.style.SUCCESS(f"\n--- Compensatory Leave Recalculation for {year} Finished ---"))