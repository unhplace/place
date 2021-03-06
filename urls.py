#use this file in place of the one generated by django when creating a project. Place it in the proper directory and do not leave it here.

from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect

from ogp import views as ogpviews

admin.autodiscover()

urlpatterns = [ 
    url(r'^robots\.txt$', lambda r: HttpResponse("User-agent: *\nDisallow: /", mimetype="text/plain")),
    url(r'^admin/', include(admin.site.urls)),

    url(r'', include('ogp.urls')),
]
