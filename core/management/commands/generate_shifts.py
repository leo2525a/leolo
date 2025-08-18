# core/management/commands/generate_shifts.py
from django.core.management.base import BaseCommand
from core.models import Employee, DutyShift
from datetime import date, timedelta

class Command(BaseCommand):
    help = 'Generates duty shifts for the upcoming week for all active employees.'

    def handle(self, *args, **kwargs):
        today = date.today()
        # 計算下一週的日期範圍
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        next_week_dates = [start_of_next_week + timedelta(days=i) for i in range(7)]

        employees_with_schedule = Employee.objects.filter(status='Active', work_schedule__isnull=False)
        self.stdout.write(f"Generating shifts for next week ({next_week_dates[0]} to {next_week_dates[-1]}) for {employees_with_schedule.count()} employees...")

        for emp in employees_with_schedule:
            for day in next_week_dates:
                weekday = day.weekday()
                rule = emp.work_schedule.rules.filter(day_of_week=weekday).first()

                if rule:
                    # get_or_create 避免重複產生
                    shift, created = DutyShift.objects.get_or_create(
                        employee=emp,
                        date=day,
                        defaults={'start_time': rule.start_time, 'end_time': rule.end_time}
                    )
                    if created:
                        self.stdout.write(f"  - Created shift for {emp.user.username} on {day}")

        self.stdout.write("Shift generation finished.")