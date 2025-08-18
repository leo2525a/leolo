# core/management/commands/process_year_end.py
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Employee, LeaveBalanceAdjustment
from datetime import date, datetime
from decimal import Decimal

class Command(BaseCommand):
    help = 'Processes year-end leave balance settlement (carry-over/forfeit).'

    # 👇 Add this method to define the --date argument
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Run the command for a specific date (YYYY-MM-DD) for testing purposes.'
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        # Use the provided date, or default to today
        custom_date_str = kwargs.get('date')
        if custom_date_str:
            today = datetime.strptime(custom_date_str, '%Y-%m-%d').date()
        else:
            today = date.today()

        self.stdout.write(f"--- Running Year-End Leave Settlement for {today} ---")
        
        # ... the rest of your handle method remains the same ...

        policies_to_process = []
        # Correctly get unique policies
        policy_ids = Employee.objects.filter(status='Active', leave_policy__isnull=False).values_list('leave_policy_id', flat=True).distinct()

        for policy_id in policy_ids:
            # We get the policy object from the employee model to avoid another import
            policy = Employee.objects.filter(leave_policy_id=policy_id).first().leave_policy
            
            if policy and today.month == policy.fiscal_year_start_month and today.day == 1:
                self.stdout.write(f"\nProcessing policy: '{policy.name}'")
                employees_on_policy = Employee.objects.filter(leave_policy=policy, status='Active')

                for emp in employees_on_policy:
                    current_balance = emp.annual_leave_balance_hours
                    
                    if policy.allow_carry_over:
                        max_carry_over_hours = policy.max_carry_over_amount
                        if policy.accrual_unit == 'DAYS':
                            max_carry_over_hours *= 8
                        
                        carry_over_hours = min(current_balance, max_carry_over_hours)
                        forfeited_hours = current_balance - carry_over_hours
                        
                        emp.annual_leave_balance_hours = carry_over_hours
                        emp.save()

                        LeaveBalanceAdjustment.objects.create(
                            employee=emp,
                            hours_changed=-forfeited_hours,
                            reason=f"Year-end settlement for {today.year - 1}: Forfeited"
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f"  - {emp.user.username}: Carried over {carry_over_hours:.2f} hours, Forfeited {forfeited_hours:.2f} hours."
                        ))
                    else:
                        forfeited_hours = current_balance
                        emp.annual_leave_balance_hours = 0
                        emp.save()
                        
                        LeaveBalanceAdjustment.objects.create(
                            employee=emp,
                            hours_changed=-forfeited_hours,
                            reason=f"Year-end settlement for {today.year - 1}: All leave forfeited."
                        )
                        self.stdout.write(self.style.WARNING(
                            f"  - {emp.user.username}: Forfeited all {forfeited_hours:.2f} hours (carry-over disabled)."
                        ))

        self.stdout.write("\n--- Year-End Settlement Finished ---")