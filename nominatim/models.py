from django.contrib.gis.db import models
from django.contrib.gis.geos import WKTReader
from django.contrib.postgres.fields import HStoreField
from django.db import connections
from gazetteer.models import Municipality

import subprocess

class USState(models.Model):
    gid = models.IntegerField(primary_key=True)
    area = models.FloatField(null=True)
    perimeter = models.FloatField(null=True)
    statesp020 = models.IntegerField(null=True)
    state = models.CharField(null=True, max_length=20)
    state_fips = models.TextField(null=True, max_length=2)
    order_adm = models.IntegerField(null=True)
    month_adm = models.TextField(null=True)
    day_adm = models.IntegerField(null=True)
    year_adm = models.IntegerField(null=True)
    geometry = models.MultiPolygonField(db_column='the_geom', null=True)
    
    objects = models.GeoManager()

    #better to use pre-generated files because Alaska takes an inordinate amount of time to generate
    #it's basically the same as every other state combined
    @staticmethod
    def geojson_for_state(state):
        with connections["nominatim"].cursor() as cursor:
            cursor.execute("SELECT ST_AsGeoJSON(ST_Union(us_state.the_geom)) FROM us_state WHERE state=%s", [state])
            geojson = cursor.fetchone()[0]
        return geojson

    @property
    def counties(self):
        return USStateCounty.objects.filter(state_fips=self.state_fips).distinct("fips")

    def __unicode__(self):
        return self.state

    class Meta:
        db_table = 'us_state'
        managed = False

class USStateCounty(models.Model):
    gid = models.IntegerField(primary_key=True)
    area = models.FloatField(null=True)
    perimeter = models.FloatField(null=True)
    countyp020 = models.IntegerField(null=True)
    state = models.CharField(max_length=2, null=True)
    county = models.CharField(max_length=50, null=True)
    fips = models.CharField(max_length=5, null=True)
    state_fips = models.CharField(max_length=2, null=True)
    square_mil = models.FloatField(null=True)
    geometry = models.MultiPolygonField(db_column='the_geom', null=True)

    objects = models.GeoManager()

    @staticmethod
    def geojson_for_county(fips):
        with connections["nominatim"].cursor() as cursor:
            cursor.execute("SELECT ST_AsGeoJSON(ST_Union(us_statecounty.the_geom)) from us_statecounty where fips=%s", [fips])
            geojson = cursor.fetchone()[0]
        return geojson

    @property
    def municipalities(self):
        return Municipality.objects.filter(state_fips=self.state_fips, county_fips=self.county_fips)

    @property
    def county_fips(self):
        return self.fips[2:]

    @property
    def state_name(self):
        return USState.objects.filter(state_fips=self.state_fips).first().state

    def __unicode__(self):
        if self.county:
            return "%s, %s" % (self.county, self.state)
        else:
            return "Unknown County"

    class Meta:
        db_table = 'us_statecounty'
        managed = False

class CountryName(models.Model):
    country_code = models.CharField(primary_key=True, max_length=2)
    name = HStoreField()

    @property
    def english_name(self):
        return self.name_for_language("en")

    def name_for_language(self, language_code):
        with connections["nominatim"].cursor() as cursor:
            cursor.execute("SELECT hstore(name)->ARRAY[%s, 'name', %s, 'official_name'] FROM country_name WHERE country_code=%s", 
                ["name:%s" % (language_code), "official_name:%s" % (language_code), self.country_code])
            (name_lc, name, official_lc, official) = cursor.fetchone()[0]
        
        return name_lc or name or official_lc or official

    def __unicode__(self):
        return self.english_name

    class Meta:
        db_table = "country_name"
        managed = False

class CountryOSMGrid(models.Model):
    country_code = models.CharField(max_length=2)
    geometry = models.GeometryField()
    area = models.FloatField(primary_key=True)

    objects = models.GeoManager()

    def __unicode__(self):
        return self.country_code

    class Meta:
        db_table = "country_osm_grid"
        managed = False

class PlaceBase(models.Model):
    osm_type = models.CharField(max_length = 1)
    osm_id = models.IntegerField(primary_key=True)
    place_class = models.TextField(db_column="class")
    place_type = models.TextField(db_column="type")
    name = HStoreField(null=True)
    admin_level = models.IntegerField(null=True)
    housenumber = models.TextField(null=True)
    street = models.TextField(null=True)
    addr_place = models.TextField(null=True)
    isin = models.TextField(null=True)
    postcode = models.TextField(null=True)
    country_code = models.CharField(max_length=2, null=True)
    extratags = HStoreField(null=True)
    geometry = models.GeometryField()


    @property
    def english_name(self):
        return self.name_for_language("en")

    def name_for_language(self, language_code):
        if "name" in self.name:
            with connections["nominatim"].cursor() as cursor:
                cursor.execute("SELECT hstore(name)->ARRAY[%s, 'name'] FROM place WHERE osm_id=%s",
                    ["name:%s" % (language_code), self.osm_id])
                (name_lc, name) = cursor.fetchone()[0]
    
            return name_lc or name
        elif self.name:
            return self.name
        else:
            return None

    @property
    def geojson_with_name(self):
        gj = self.geometry.geojson
        gj = gj.replace("{", '{"properties": { "name": "%s" },' % (self.english_name), 1)

        return gj

    def __unicode__(self):
        if self.name:
            name = self.english_name or self.name.split(", ")[0]
            return "%s (%s)" % (self.place_type, name)
        else:
            return "No name"

    class Meta:
        abstract = True

class Place(PlaceBase):
    #all fields are in PlaceBase

    objects = models.GeoManager()

    class Meta:
        db_table = "place"
        managed = False
        
class Placex(PlaceBase):
#from PlaceBase
#   osm_type = models.CharField(max_length = 1)
#   osm_id = models.IntegerField(primary_key=True)
#   place_class = models.TextField(db_column="class")
#   place_type = models.TextField(db_column="type")
#   name = HStoreField(null=True)
#   admin_level = models.IntegerField(null=True)
#   housenumber = models.TextField(null=True)
#   street = models.TextField(null=True)
#   addr_place = models.TextField(null=True)
#   isin = models.TextField(null=True)
#   postcode = models.TextField(null=True)
#   country_code = models.CharField(max_length=2, null=True)
#   extratags = HStoreField(null=True)
#   geometry = models.GeometryField()

    calculated_country_code = models.CharField(max_length=2, null=True)
    centroid = models.GeometryField(null=True)
    geometry_sector = models.IntegerField(null=True)
    importance = models.FloatField(null=True)
    indexed_date = models.DateTimeField(null=True)
    indexed_status = models.IntegerField(null=True)
    linked_place_id = models.IntegerField(null=True)
    parent_place_id = models.IntegerField(null=True)
    partition = models.IntegerField(null=True)
    place_id = models.IntegerField(unique=True)
    rank_address = models.IntegerField(null=True)
    rank_search = models.IntegerField(null=True)
    wikipedia = models.TextField(null=True)

    objects = models.GeoManager()

    class Meta:
        db_table = "placex"
        managed = False

class LocationArea(models.Model):
    partition = models.IntegerField(null=True)
#   place_id = models.IntegerField(primary_key=True)
    country_code = models.CharField(max_length=2, null=True)
    keywords = models.TextField(null=True)
    rank_search = models.IntegerField()
    rank_address = models.IntegerField()
    isguess = models.NullBooleanField(null=True)
    centroid = models.PointField(null=True)
    geometry = models.GeometryField(null=True)

    place = models.ForeignKey(Placex, to_field="place_id")

    objects = models.GeoManager()

    class Meta:
        db_table = "location_area"
        managed = False

    def __unicode__(self):
        return self.place.__unicode__()

#not super useful because bounds are estimates and coverage possibly imcomplete
class CountryNaturalEarthData(models.Model):
    country_code = models.CharField(max_length=2)
    geometry = models.GeometryField(primary_key = True)

    objects = models.GeoManager()

    class Meta:
        db_table = "country_naturalearthdata"
        managed = False
