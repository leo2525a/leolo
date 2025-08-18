# core/scheduler.py
from django.core.management import call_command
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
import time

def accrue_leave_job():
    """
    Executes the accrue_leave management command.
    """
    try:
        call_command('accrue_leave')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully ran accrue_leave_job.")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error running accrue_leave_job: {e}")

def compensate_holiday_job():
    """
    Executes the compensate_holidays management command.
    """
    try:
        call_command('compensate_holidays')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully ran compensate_holiday_job.")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error running compensate_holiday_job: {e}")

def process_year_end_job():
    """
    Executes the process_year_end management command.
    """
    try:
        call_command('process_year_end')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully ran process_year_end_job.")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error running process_year_end_job: {e}")

def start_scheduler():
    """
    Starts the scheduler and adds all jobs.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")
    
    # Job 1: Accrue Leave
    scheduler.add_job(
        accrue_leave_job,
        trigger='interval',
        seconds=60, # For testing
        id='accrue_leave_daily_job',
        replace_existing=True,
    )
    
    # Job 2: Compensate for Holidays
    scheduler.add_job(
        compensate_holiday_job,
        trigger='cron',
        hour='1', # Daily at 1 AM
        id='compensate_holiday_daily_job',
        replace_existing=True,
    )

    # Job 3: Process Year-End Settlement
    scheduler.add_job(
        process_year_end_job,
        trigger='cron',
        hour='0', # Daily at midnight
        id='process_year_end_daily_job',
        replace_existing=True,
    )
    
    try:
        print("Starting scheduler...")
        scheduler.start()
    except KeyboardInterrupt:
        print("Stopping scheduler...")
        scheduler.shutdown()
        print("Scheduler shut down successfully!")