from django.core.management.base import BaseCommand
from core.models import Employee, LeaveBalance, LeaveType
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Recalculates leave balances for all active employees based on their assigned policies.'

    def handle(self, *args, **options):
        self.stdout.write("Starting balance recalculation for all active employees...")

        active_employees = Employee.objects.filter(status='Active', leave_policy__isnull=False)
        
        try:
            # 我們假設此腳本專門針對 'Annual Leave'
            annual_leave_type = LeaveType.objects.get(name__iexact='Annual Leave')
            self.stdout.write(self.style.SUCCESS(f"Successfully found 'LeaveType': {annual_leave_type.name} (ID: {annual_leave_type.id})"))
        except LeaveType.DoesNotExist:
            self.stdout.write(self.style.ERROR("Error: 'Annual Leave' type not found. Please create it first."))
            return

        self.stdout.write(f"Found {active_employees.count()} active employee(s) with an assigned leave policy.")

        for employee in active_employees:
            policy = employee.leave_policy
            today = date.today()
            
            self.stdout.write(f"\nProcessing Employee: {employee.user.get_full_name()} (ID: {employee.id})")
            
            # --- 計算服務年資 ---
            service_duration = relativedelta(today, employee.hire_date)
            years_of_service = service_duration.years
            
            # --- 基本權益 ---
            total_entitlement_in_policy_unit = policy.accrual_amount

            # --- 根據服務年資應用政策規則 ---
            applicable_rule = policy.rules.filter(years_of_service__lte=years_of_service).order_by('-years_of_service').first()

            if applicable_rule:
                self.stdout.write(f"  - Applying rule for {applicable_rule.years_of_service} years of service.")
                if applicable_rule.rule_type == 'ADD':
                    total_entitlement_in_policy_unit += applicable_rule.adjustment_amount
                elif applicable_rule.rule_type == 'SET':
                    total_entitlement_in_policy_unit = applicable_rule.adjustment_amount
            
            # --- 如果政策單位是 'DAYS'，則將權益轉換為小時 ---
            final_balance_hours = total_entitlement_in_policy_unit
            if policy.accrual_unit == 'DAYS':
                self.stdout.write(f"  - Policy unit is DAYS. Converting {total_entitlement_in_policy_unit} days to hours...")
                final_balance_hours = total_entitlement_in_policy_unit * 8
            
            # --- 尋找或建立年假餘額記錄 ---
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave_type,
            )
            
            if created:
                self.stdout.write(self.style.WARNING(f"  - No existing '{annual_leave_type.name}' balance found. CREATED a new one."))
            else:
                self.stdout.write(f"  - Found existing '{annual_leave_type.name}' balance (Old value: {balance.balance_hours} hours).")

            # 分配正確計算出的小時數
            balance.balance_hours = Decimal(str(final_balance_hours))
            balance.save()

            self.stdout.write(self.style.SUCCESS(f"  - SUCCESS: Balance for '{balance.leave_type.name}' recalculated to {balance.balance_hours:.2f} hours."))

        self.stdout.write("\nBalance recalculation finished.")