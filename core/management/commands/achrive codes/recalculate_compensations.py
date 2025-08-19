# core/management/commands/compensate_holidays.py

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Employee, PublicHoliday, LeaveType, LeaveBalance, LeaveBalanceAdjustment, ScheduleRule
from datetime import date

class Command(BaseCommand):
    help = 'Compensates employees for public holidays that fall on their rest day.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='The year to process for holiday compensation. Defaults to the current year.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        year = options['year']
        self.stdout.write(self.style.SUCCESS(f"Starting holiday compensation check for the year {year}..."))

        # --- 1. Fetch necessary data ---
        try:
            # We will add the compensated hours to the 'Annual Leave' balance.
            annual_leave_type = LeaveType.objects.get(name__iexact='Annual Leave')
        except LeaveType.DoesNotExist:
            self.stdout.write(self.style.ERROR("Could not find a LeaveType named 'Annual Leave'. Please create it first."))
            return

        public_holidays = PublicHoliday.objects.filter(date__year=year)
        if not public_holidays.exists():
            self.stdout.write(self.style.WARNING(f"No public holidays found for the year {year}. Nothing to do."))
            return

        active_employees = Employee.objects.filter(status='Active').select_related('work_schedule')
        
        compensation_count = 0

        # --- 2. Iterate through each employee and holiday ---
        for employee in active_employees:
            if not employee.work_schedule:
                self.stdout.write(self.style.WARNING(f"Skipping {employee} as they have no work schedule assigned."))
                continue

            # Get the employee's scheduled workdays (0=Monday, 6=Sunday)
            work_day_rules = employee.work_schedule.rules.values_list('day_of_week', flat=True)
            work_days = set(work_day_rules)

            for holiday in public_holidays:
                holiday_weekday = holiday.date.weekday()

                # Check if the holiday falls on a rest day
                if holiday_weekday not in work_days:
                    # The holiday is on a rest day, so we compensate the employee.
                    
                    # Create a LeaveBalanceAdjustment record for audit purposes
                    adjustment, created = LeaveBalanceAdjustment.objects.get_or_create(
                        employee=employee,
                        leave_type=annual_leave_type,
                        reason=f"Holiday Compensation: {holiday.name} on {holiday.date}",
                        defaults={'hours_changed': 8.00}
                    )

                    if created:
                        # Find or create the employee's annual leave balance record
                        balance, _ = LeaveBalance.objects.get_or_create(
                            employee=employee,
                            leave_type=annual_leave_type
                        )
                        
                        # Add 8 hours to their balance
                        balance.balance_hours += 8.00
                        balance.save()
                        
                        compensation_count += 1
                        self.stdout.write(f"Compensated {employee} with 8 hours for '{holiday.name}'.")

        if compensation_count > 0:
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully processed {compensation_count} compensations for {year}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nNo new compensations were needed for {year}."))