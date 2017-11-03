from django.conf.urls import include, url

from . import views as gazetteerviews

urlpatterns = [ 
    url(r'^bbox', gazetteerviews.bbox_polygon),
    url(r'^countries', gazetteerviews.gazetteer_countries),
    url(r'^country', gazetteerviews.country_polygon),
    url(r'^states', gazetteerviews.gazetteer_states),
    url(r'^state', gazetteerviews.state_polygon),
    url(r'^counties', gazetteerviews.counties_for_state),
    url(r'^county', gazetteerviews.county_polygon),
    url(r'^municipalities', gazetteerviews.municipalities_for_county),
    url(r'^municipality', gazetteerviews.municipality_polygon), 
]
