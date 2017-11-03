from django.contrib.gis.db import models
from django.contrib.postgres.fields import HStoreField
from django.db import connections

import json

#gazetteer id format - type:id
#country:"2 character ISO 3166-1 alpha-2 code" e.g. country:us
#state:"2 character state fips code" e.g. state:33
#county:"2 character state fips code""3 character county fips code"  e.g. county:33001
#municipality: "2 character state fips code""3 character county fips code"-"variable length GNIS ID" e.g. municipality:33003-873526
#   in rare cases where no GNIS ID is available, the name is used in lower case and with underscores substituting spaces e.g. municipality:23025-t3_r5_bkp_wkr
class GeneratedGeometry(models.Model):
    gazetteer_id = models.TextField(unique=True)
    geometry = models.GeometryField() 
    osm_id = models.IntegerField(null=True) #optional OSM id for searches stemming from nominatim

    objects = models.GeoManager()

    def __unicode__(self):
        return self.gazetteer_id

    class Meta:
        db_table = "gazetteer_generatedgeometry"

class State(models.Model):
    name = models.TextField()
    geometry = models.GeometryField()
    state_fips = models.CharField(max_length=2, unique=True)
    abbreviation = models.TextField(blank=True)
    
    def __unicode__(self):
        return self.name

    @property
    def identifier(self):
        return self.state_fips or self.name.lower().replace(" ", "_")

    @property
    def counties(self):
        return County.objects.filter(state_fips=self.state_fips)

class County(models.Model):
    name = models.TextField()
    geometry = models.GeometryField()
    state_fips = models.CharField(max_length=2)
    county_fips = models.CharField(max_length=3)

    def __unicode__(self):
        return self.name

    @property
    def identifier(self):
        return "%s%s" % (self.state_fips, self.county_fips) or self.name.lower().replace(" ", "_")

    @property
    def municipalities(self):
        return Municipality.objects.filter(state_fips = self.state_fips, county_fips = self.county_fips).order_by("name")

class Municipality(models.Model):
    name = models.TextField()
    geometry = models.GeometryField()
    place_id = models.TextField(null=True, blank=True)
    state_fips = models.CharField(max_length=2)
    county_fips = models.CharField(max_length=3)

    def __unicode__(self):
        return self.name

    @property
    def identifier(self):
        return self.place_id or self.name.lower().replace(" ", "_")

    @property
    def bbox(self):
        with connections["default"].cursor() as c:
            m = self
            c.execute("select ST_AsGeoJSON(Box2D(gazetteer_municipality.geometry)) from gazetteer_municipality where state_fips=%s and county_fips=%s and name=%s", [m.state_fips, m.county_fips, m.name])
            r = c.fetchone()

            return json.loads(r[0])["coordinates"][0]

    class Meta:
        db_table = "gazetteer_municipality"

class GNIS(models.Model):
    feature_id = models.IntegerField(primary_key=True)
    feature_name = models.TextField(null=True, blank=True)
    feature_class = models.TextField(null=True, blank=True)
    state_alpha = models.TextField(null=True, blank=True)
    state_numeric = models.TextField(null=True, blank=True)
    county_name = models.TextField(null=True, blank=True)
    county_numeric = models.TextField(null=True, blank=True)
    primary_latitude_dms = models.TextField(null=True, blank=True)
    primary_longitude_dms = models.TextField(null=True, blank=True)
    primary_latitude_dec = models.FloatField(null=True, blank=True)
    primary_longitude_dec = models.FloatField(null=True, blank=True)
    source_latitude_dms = models.TextField(null=True, blank=True)
    source_longitude_dms = models.TextField(null=True, blank=True)
    source_latitude_dec = models.FloatField(null=True, blank=True)
    source_longitude_dec = models.FloatField(null=True, blank=True)
    elevation_meters = models.FloatField(null=True, blank=True)
    elevation_feet = models.FloatField(null=True, blank=True)
    map_name = models.TextField(null=True, blank=True)
    date_created = models.TextField(null=True, blank=True)
    date_modified = models.TextField(null=True, blank=True)

    def __unicode__(self):
        return self.feature_name

class FIPS55(models.Model):
    state = models.CharField(max_length=2)
    state_fips = models.CharField(max_length=2)
    place_fips = models.CharField(max_length=5)
    place_name = models.TextField()
    place_type = models.TextField()
    status = models.CharField(max_length=1)
    county = models.TextField()

    def __unicode__(self):
        return "%s: %s" % (self.state, self.place_name)

class ShapeFileData(models.Model):
    geometry = models.GeometryField()
    record = HStoreField()
    state = models.CharField(max_length=2)
    name = models.TextField()
    state_fips = models.CharField(max_length=2)
    county_fips = models.CharField(max_length=3, blank=True, null=True)

    def __unicode__(self):
        return "%s, %s" % (self.name, self.state)
