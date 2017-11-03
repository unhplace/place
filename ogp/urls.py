from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect

from . import views as ogpviews

ogp_urlpatterns = [ 
    url(r'^abstract$', ogpviews.abstract_for_layer),
    url(r'^download$', ogpviews.download_items),
    url(r'^find$', ogpviews.find_items),
    url(r'^import$', ogpviews.import_item),
    url(r'^items$', ogpviews.items_for_layers),
    url(r'^layer$', ogpviews.link_for_layer),
    url(r'^map$', ogpviews.map),
    url(r'^metadata$', ogpviews.metadata_for_layer),
    url(r'^minimal_import', ogpviews.minimal_ogp_import),
    url(r'^originators', ogpviews.originators),
    url(r'^bbox', ogpviews.bbox_for_layers), 
    url(r'items_at_coord', ogpviews.items_at_coord),
    url(r'import_pdf', ogpviews.import_pdf),
]

urlpatterns = [
    url(r'ogp/', include(ogp_urlpatterns)),
    url(r'^gazetteer/', include('gazetteer.urls')),
    url(r'^$', ogpviews.map),

    url(r'^external_wfs/(.*)/wfs$', ogpviews.external_wfs_request),
    url(r'^external_reflect/(.*)/wms/reflect$', ogpviews.external_reflect_request),
    url(r'^external_solr$', ogpviews.external_solr_request),
    url(r'^geoserver/', ogpviews.geoserver_request),
    url(r'^nominatim/', ogpviews.nominatim_request),
    url(r'^opengeoportal$', lambda r: HttpResponseRedirect("/opengeoportal/")),
    url(r'^opengeoportal/', ogpviews.ogp_request),
    url(r'^solr/', ogpviews.solr_request),
    url(r'^(?P<page>.+)$', 'ogp.views.display_page'),
]
