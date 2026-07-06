from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import FirstAccessPasswordChangeDoneView, FirstAccessPasswordChangeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='dashboard', permanent=False)),
    path('dashboard/', include('dashboard.urls')),
    path('accounts/password_change/', FirstAccessPasswordChangeView.as_view(), name='password_change'),
    path('accounts/password_change/done/', FirstAccessPasswordChangeDoneView.as_view(), name='password_change_done'),
    path('accounts/', include('django.contrib.auth.urls')),
]
