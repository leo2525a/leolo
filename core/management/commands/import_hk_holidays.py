# core/management/commands/import_hk_holidays.py
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from core.models import PublicHoliday

# 使用您提供的、更穩定的通用 API URL
API_URL = "https://www.1823.gov.hk/common/ical/en.json"

class Command(BaseCommand):
    help = 'Imports Hong Kong public holidays from the official data.gov.hk API.'

    def handle(self, *args, **kwargs):
        self.stdout.write(f"Fetching public holidays from official source...")

        try:
            response = requests.get(API_URL)
            response.raise_for_status() # 確保請求成功 (HTTP 狀態碼 200)
            data = response.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Error fetching data: {e}"))
            return

        # JSON 結構是 vcalendar -> vevent
        holidays_data = data.get('vcalendar', [{}])[0].get('vevent', [])

        if not holidays_data:
            self.stdout.write(self.style.ERROR("Could not find holiday data ('vevent') in the JSON response."))
            return

        count_created = 0
        count_updated = 0

        for holiday in holidays_data:
            summary = holiday.get('summary')
            start_date_str = holiday.get('dtstart', [None])[0]

            if summary and start_date_str:
                try:
                    # 將 "YYYYMMDD" 格式的字串轉換為 date 物件
                    holiday_date = datetime.strptime(start_date_str, '%Y%m%d').date()

                    # 使用 update_or_create 來避免重複建立，並能更新假期名稱
                    obj, created = PublicHoliday.objects.update_or_create(
                        date=holiday_date,
                        defaults={'name': summary}
                    )
                    if created:
                        count_created += 1
                    else:
                        count_updated += 1

                except ValueError:
                    self.stdout.write(self.style.WARNING(f"Could not parse date: {start_date_str} for holiday '{summary}'"))

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed holidays. New holidays added: {count_created}, Existing holidays updated: {count_updated}."
        ))