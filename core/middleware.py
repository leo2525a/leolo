# leo2525a/leolo/leolo-3ca44c5b5be68a58e15772da0edf67a6ed2b860a/core/middleware.py
from django.shortcuts import redirect
from django.urls import reverse

class ProfileCompletionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated or request.path.startswith('/admin/'):
            return self.get_response(request)

        try:
            employee = request.user.employee_profile
        except AttributeError:
            return self.get_response(request)

        # 【↓↓↓ 修改這裡的 allowed_urls ↓↓↓】
        allowed_urls = [
            reverse('core:profile_edit'),
            reverse('core:logout') # Add the 'core:' namespace here
        ]
        
        # 檢查 profile 本身的路徑，避免在已完成時產生問題
        if request.path == reverse('core:profile'):
             return self.get_response(request)


        if not employee.is_profile_complete() and request.path not in allowed_urls:
            # 強制重新導向到編輯頁面
            return redirect('core:profile_edit')

        response = self.get_response(request)
        return response