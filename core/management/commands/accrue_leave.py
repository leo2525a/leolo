# core/management/commands/accrue_leave.py
from django.core.management.base import BaseCommand
from core.models import Employee, LeavePolicy, LeaveBalance, LeaveType
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Accrues leave for all active employees based on their policies.'

    def handle(self, *args, **options):
        self.stdout.write("Starting leave accrual process...")

        today = date.today()
        active_employees = Employee.objects.filter(status='Active', leave_policy__isnull=False)
        
        try:
            annual_leave_type = LeaveType.objects.get(name__iexact='Annual Leave')
        except LeaveType.DoesNotExist:
            self.stdout.write(self.style.ERROR("Error: 'Annual Leave' type not found. Please create it."))
            return

        for employee in active_employees:
            policy = employee.leave_policy
            
            # --- Calculate Years of Service ---
            service_duration = relativedelta(today, employee.hire_date)
            years_of_service = service_duration.years

            # --- Determine Waiting Period ---
            waiting_period_end = employee.hire_date
            if policy.waiting_period_unit == 'DAYS':
                waiting_period_end += relativedelta(days=policy.waiting_period_amount)
            elif policy.waiting_period_unit == 'MONTHS':
                waiting_period_end += relativedelta(months=policy.waiting_period_amount)

            if today < waiting_period_end:
                # self.stdout.write(f"Employee {employee.user.username} is still in waiting period.")
                continue

            # --- Accrual Logic ---
            accrual_amount = policy.accrual_amount
            should_accrue = False

            if policy.accrual_frequency == 'YEARLY':
                # Accrue on the anniversary of the hire date each year
                if today.month == employee.hire_date.month and today.day == employee.hire_date.day and today > employee.hire_date:
                    should_accrue = True
            
            # Add other frequencies (MONTHLY, etc.) here if needed

            # --- Apply Policy Rules ---
            applicable_rules = policy.rules.filter(years_of_service__lte=years_of_service).order_by('-years_of_service')
            for rule in applicable_rules:
                if rule.rule_type == 'ADD':
                    accrual_amount += rule.adjustment_amount
                elif rule.rule_type == 'SET':
                    accrual_amount = rule.adjustment_amount
                # Only apply the highest-matching rule
                break 

            if should_accrue:
                balance, created = LeaveBalance.objects.get_or_create(
                    employee=employee,
                    leave_type=annual_leave_type,
                    defaults={'balance_hours': Decimal('0.0')}
                )
                
                # Assuming the policy accrual unit is 'DAYS', convert to hours (8 hours/day)
                # This part may need adjustment if your policies are in hours
                if policy.accrual_unit == 'DAYS':
                    accrual_hours = accrual_amount * 8
                else: # Assumes HOURS
                    accrual_hours = accrual_amount

                balance.balance_hours += Decimal(str(accrual_hours))
                balance.save()

                self.stdout.write(self.style.SUCCESS(
                    f"Accrued {accrual_hours} hours ({accrual_amount} days) for {employee.user.username}"
                ))
        
        # This line was incorrectly indented. It now belongs to the 'handle' method.
        self.stdout.write("Leave accrual process finished.")