from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import FirstAccessPasswordChangeDoneView, FirstAccessPasswordChangeView, post_login_redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/dashboard/img/favicon.svg', permanent=False)),
    path('', RedirectView.as_view(pattern_name='dashboard', permanent=False)),
    path('dashboard/', include('dashboard.urls')),
    path('accounts/password_change/', FirstAccessPasswordChangeView.as_view(), name='password_change'),
    path('accounts/password_change/done/', FirstAccessPasswordChangeDoneView.as_view(), name='password_change_done'),
    path('accounts/redirect/', post_login_redirect, name='post_login_redirect'),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
