from django.conf.urls import patterns, include, url

urlpatterns = patterns('', 
    url(r'^external_wfs/(.*)/wfs$', 'ogp.views.external_wfs_request'),
    url(r'^external_reflect/(.*)/wms/reflect$', 'ogp.views.external_reflect_request'),
    url(r'^external_solr$', 'ogp.views.external_solr_request'),
    url(r'^geoserver/', 'ogp.views.geoserver_request'),
    url(r'^nominatim/', 'ogp.views.nominatim_request'),
    url(r'^opengeoportal$', lambda r: HttpResponseRedirect("/opengeoportal/")),
    url(r'^opengeoportal/', 'ogp.views.ogp_request'),
    url(r'^solr/', 'ogp.views.solr_request'),
)
