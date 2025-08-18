# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('jobs/', views.job_board_view, name='job_board'),
    path('jobs/<int:job_id>/', views.job_detail_view, name='job_detail'),

    # Employee Pages
    path('profile/', views.profile_view, name='profile'),
    path('directory/', views.employee_directory_view, name='employee_directory'),
    
    # Leave Management
    path('leave/apply/', views.leave_apply_view, name='leave_apply'),
    
    # Performance Reviews
    path('reviews/', views.my_reviews_view, name='my_reviews'),
    path('reviews/<int:review_id>/', views.review_detail_view, name='review_detail'),

    path('attendance/', views.attendance_view, name='attendance'),
    path('attendance/clock-in-out/', views.clock_in_out_view, name='clock_in_out'),
    path('manager/manual-attendance/', views.manual_attendance_view, name='manual_attendance'),


    # Manager Pages
    path('manager/dashboard/', views.manager_dashboard_view, name='manager_dashboard'),
    path('manager/review/<int:review_id>/', views.manager_review_detail_view, name='manager_review_detail'),
    path('leave/approve/<int:request_id>/', views.leave_approve_view, name='leave_approve'),
    path('leave/reject/<int:request_id>/', views.leave_reject_view, name='leave_reject'),
    path('manager/edit-schedule/', views.edit_team_schedule_view, name='edit_team_schedule'),
    path('internal/jobs/<int:job_id>/pipeline/', views.recruitment_pipeline_view, name='recruitment_pipeline'),
    path('internal/application/<int:app_id>/update-status/', views.update_application_status_view, name='update_application_status'),



    # Analytics
    path('analytics/', views.analytics_view, name='analytics'), # <-- This is the line that was likely missing or incorrect
    path('schedule/', views.team_schedule_view, name='team_schedule_current'),
    path('schedule/<int:year>/<int:month>/', views.team_schedule_view, name='team_schedule'),

    path('reports/', views.reporting_view, name='reporting'),

    #path('schedule/', views.duty_schedule_view, name='duty_schedule'),

    path('overtime/apply/', views.overtime_apply_view, name='overtime_apply'),
    path('overtime/approve/<int:request_id>/', views.overtime_approve_view, name='overtime_approve'),
    path('overtime/reject/<int:request_id>/', views.overtime_reject_view, name='overtime_reject'),

    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('onboarding/complete-task/<int:task_id>/', views.complete_task_view, name='complete_task'),

]