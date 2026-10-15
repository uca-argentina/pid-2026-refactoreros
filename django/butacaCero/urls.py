from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "Butaca Cero - Admin Panel"
admin.site.site_title = "Butaca Cero - Admin Panel"


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('', include('web.catalog.urls')),
    path('', include('web.tickets.urls')),
    path('', include('web.auth.urls')),
    path('gestion/', include('web.manager.urls')),
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG or settings.SERVE_MEDIA_FILES:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "web.catalog.views.bad_request_view"
handler403 = "web.catalog.views.permission_denied_view"
handler404 = "web.catalog.views.not_found_view"
handler500 = "web.catalog.views.server_error_view"
