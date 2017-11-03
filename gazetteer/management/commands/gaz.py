from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import Polygon, Point, WKBReader
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from nominatim.models import USState, USStateCounty
from gazetteer.models import GeneratedGeometry, GNIS, FIPS55, Municipality, ShapeFileData, State, County

from gazetteer.views import shape_to_geos

from glob import glob
from lockfile import LockFile
from zipfile import ZipFile

import datetime
import errno
import os
import requests
import shapefile
import shutil
import sys
import urllib

#from place.settings import BASE_DIR
from django.conf import settings
BASE_DIR = settings.BASE_DIR
BOLD_START = '\033[1m'
BOLD_END = '\033[0m'

class Command(BaseCommand):
    help = 'Create or update the gazetteer'

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)
        parser.add_argument("--state", type=str)
        parser.add_argument("--county", type=str)
        parser.add_argument("--template_directory", type=str, default=settings.TEMPLATE_DIRS[0])

    def handle(self, *args, **options):
        task = options["task"]
        state = options["state"]
        county = options["county"]
        template_dir = options["template_directory"]

        if not task in ("create", "list", "load_fips", "load_gnis"):
            raise CommandError("task must be 'create', 'list', 'load_fips' or 'load_gnis'")

        if task == "create":
            if not state:
                raise CommandError("A state is required. Use '--state=initial' to create the initial gazetteer data, or '--state=all' to load all gazetteer data.")

            if state == "initial":
                self.load_initial_data(template_dir)
            elif state == "all":
                if State.objects.all().count() == 0:
                    self.load_initial_data(template_dir)

                for s in State.objects.all().order_by("state_fips"):
                    self.stdout.write(s.name)
                    self.load_tiger_shapefile(s.state_fips, template_dir)
            else:
                self.load_tiger_shapefile(state, template_dir)

        if task == "list":
            if state == "all":
                for state in State.objects.distinct("name").order_by("name"):
                    self.stdout.write(state.name)
                    for county in County.objects.filter(state_fips = state.state_fips).distinct("name").order_by("name"):
                        self.stdout.write(u"    %s" % (county))
                        for m in Municipality.objects.filter(state_fips=state.state_fips, county_fips=county.county_fips).order_by("name"):
                            self.stdout.write(u"        %s" % (m))
            elif not state and not county:
                states = State.objects.all().distinct("state_fips").order_by("state_fips").values_list("state_fips", "name", "abbreviation")

                self.stdout.write("Listing all states with FIPS code and abbreviation.")
                for state in states:
                    self.stdout.write("%s/%s - %s" % (state[0], state[2], state[1]))
            elif state and not county:
                state = self.state_to_fips(state)
                
                self.stdout.write("Listing all counties in %s%s%s with FIPS codes" % (BOLD_START, State.objects.get(state_fips=state).name, BOLD_END))

                for county in County.objects.filter(state_fips=state).order_by("county_fips"):
                    self.stdout.write("%s - %s" % (county.county_fips, county))
            elif state and county:
                state = self.state_to_fips(state)
                county = self.county_to_fips(state, county)

                self.stdout.write("Listing all municipalities and county subdivisions in %s%s, %s%s" % 
                    (BOLD_START, County.objects.get(county_fips=county, state_fips=state), State.objects.get(state_fips=state), BOLD_END))
                for m in Municipality.objects.filter(state_fips=state, county_fips=county).order_by("name"):
                    self.stdout.write("%s" % (m))
            return

        if task == "load_gnis":
            if not state:
                raise CommandError("A 2 character state code is required")
            self.load_gnis(state)

        if task == "load_fips":
            if not state:
                raise CommandError("A 2 character state code is required or enter \"all\" for the entire US")
            self.load_fips(state)

    def load_fips(self, state):
        url = None
        if len(state) == 2:
            state_fips = self.state_to_fips(state)
            url = "https://www2.census.gov/geo/docs/reference/codes/files/st%s_%s_places.txt" % (state_fips, state.lower())
        elif state == "all":
            url = "https://www2.census.gov/geo/docs/reference/codes/files/national_places.txt"
        else:
            raise CommandError("A 2 character state code is required or enter \"all\" for the entire US")

        response = requests.get(url)
        lines = [l.strip().split("|") for l in response.text.split("\n")]

        if state == "all":
            lines = lines[1:]

        last_state = None

        for fips_values in lines:
            fips_keys = ["state", "state_fips", "place_fips", "place_name", "place_type", "status", "county"]

            d = dict(zip(fips_keys, fips_values))

            if not "place_fips" in d:
                continue

            if d["state"] != last_state:
                last_state = d["state"]
                self.stdout.write("Loading codes for %s" % last_state)

            qs = FIPS55.objects.filter(state=d["state"], place_fips=d["place_fips"])

            if qs.exists():
                continue

            fips = FIPS55(**d)
            fips.save()

        return

    def municipalities_in_county(self, state, county):
        state = self.state_to_fips(state)
        county = self.county_to_fips(state, county)
        return Municipality.objects.filter(state_fips=state, county_fips=county).order_by("name")

    def state_to_fips(self, state):
        if len(state) == 2 and state.isdigit():
            qs = State.objects.filter(state_fips=state)

            if not qs.exists():
                raise CommandError("\"%s\" is not a valid state FIPS code. Use \"gazetteer list\" to get a list of state codes." % (state))
            return state
        elif len(state) == 2: #not 2 digit code
            qs = State.objects.filter(abbreviation=state)

            if not qs.exists():
                raise CommandError("\"%s\" is not a valid 2 character abbreviation. Use \"gazetteer list\" to get a list of state codes." % (state))

            return qs.first().state_fips
        elif len(state) > 2:
            qs = State.objects.filter(name=state)

            if not qs.exists():
                raise CommandError("\"%s\" is not a valid state name. Use \"gazetteer list\" to get a list of state codes." % (state))

            return qs.first().state_fips
        else:
            raise CommandError("State must be either the full state name, the 2 character abbreviation or the 2 digit FIPS code. Use \"gazetteer list\" to get a list of state codes.")

    def county_to_fips(self, state, county):
        state = self.state_to_fips(state)
        if len(county) == 3 and county.isdigit():
            qs = County.objects.filter(state_fips = state, county_fips=county)

            if not qs.exists():
                raise CommandError("\"%s\" is not a valid county FIPS code. Use \"gazetteer list --state=%s\" to get a list of county codes." % (county, state))
            return county
        else:
            qs = County.objects.filter(state_fips = state, name = county)

            if not qs.exists():
                raise CommandError("\"%s\" is not a valid county name. Use \"gazetteer list --state=%s\" to get a list of county codes." % (county, state))

            return qs.first().county_fips

    def load_tiger_shapefile(self, state, template_dir):
        state = self.state_to_fips(state)
        url = "https://www2.census.gov/geo/tiger/TIGER2016/COUSUB/tl_2016_%s_cousub.zip" % (state)

        tmp_dir = "/tmp/tiger-%s" % (state)
        tmp_file = "%s/tl_2016_%s_cousub.zip" % (tmp_dir, state)

        #create directory if needed
        try:
            os.makedirs(tmp_dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise e

        #retrieve file
        urllib.urlretrieve(url, tmp_file)

        #extract
        zipfile = ZipFile(tmp_file)
        zipfile.extractall(path=tmp_dir)
        zipfile.close()

        #process

        sf = shapefile.Reader(tmp_file.replace("zip", "shp"))
        fields = [f[0] for f in sf.fields[1:]]
        n = len(sf.records())

        for i in range(0,n):
            r = dict(zip(fields, sf.records()[i]))
            if Municipality.objects.filter(state_fips=r["STATEFP"], county_fips=r["COUNTYFP"], name=r["NAME"]).exists():
                continue

            s = shape_to_geos(sf.shapes()[i], 4326)
            d = {
                "county_fips": r["COUNTYFP"],
                "geometry": s,
                "place_id": unicode(r["GEOID"]),
                "name": r["NAME"].decode("utf-8"),
                "state_fips": r["STATEFP"],
            }

            m = Municipality(**d)
            m.save()

            gg = GeneratedGeometry(geometry=s, gazetteer_id="municipality:%s%s-%s" % (r["STATEFP"], r["COUNTYFP"], r["GEOID"]))
            gg.save()

            municipality_template_dir = "%s/polygons/municipality/%s/%s" % (template_dir, r["STATEFP"], r["COUNTYFP"])
            if not (os.path.exists(municipality_template_dir)):
                os.makedirs(municipality_template_dir, mode=0755)
            with open("%s/%s.json" % (municipality_template_dir, r["GEOID"]), "w") as f:
                f.write(s.geojson)

            self.stdout.write("%d/%d - %s" % (i+1, n, r["NAME"].decode("utf-8")))

        #delete file
        for f in glob("%s/tl_2016_%s_cousub.*" % (tmp_dir, state)):
            os.remove(f)

        try:
            os.rmdir(tmp_dir)
        except e:
            pass

        return

    def load_initial_data(self, template_dir):
        self.load_initial_states(template_dir)
        self.load_initial_counties(template_dir)

    def load_initial_states(self, template_dir):
        state_directory = "%s/polygons/state" % (template_dir)

        #creates states
        if not os.path.exists(state_directory):
            os.makedirs(state_directory, mode=0755)

        state_url = "https://www2.census.gov/geo/tiger/TIGER2016/STATE/tl_2016_us_state.zip"

        tmp_dir = "/tmp/tiger-state"
        tmp_file = "%s/tl_2016_us_state.zip" % (tmp_dir)

        try:
            os.makedirs(tmp_dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise e

        urllib.urlretrieve(state_url, tmp_file)

        zipfile = ZipFile(tmp_file)
        zipfile.extractall(path=tmp_dir)
        zipfile.close()

        sf = shapefile.Reader(tmp_file.replace("zip", "shp"))
        fields = [f[0] for f in sf.fields[1:]]
        n = len(sf.records())

        self.stdout.write("Loading %d states and territories" % (n))

        for i in range(0,n):
            r = dict(zip(fields, sf.records()[i]))
            if State.objects.filter(state_fips=r["STATEFP"]).exists():
                continue

            s = shape_to_geos(sf.shapes()[i], 4326)
            d = {
                "name": r["NAME"].decode("utf-8"),
                "geometry": s,
                "state_fips": r["STATEFP"],
                "abbreviation": r["STUSPS"],
            }

            state = State(**d)
            state.save()

            gg = GeneratedGeometry(geometry=s, gazetteer_id="state:%s" % (r["STATEFP"]))
            gg.save()

            with open("%s/%s.json" % (state_directory, r["STATEFP"]), "w") as f:
                f.write(s.geojson)

            self.stdout.write("%d/%d - %s" % (i+1, n, r["NAME"].decode("utf-8")))

        for f in glob("%s/tl_2016_us_state.*" % (tmp_dir)):
            os.remove(f)

        try:
            os.rmdir(tmp_dir)
        except e:
            pass

        return

    def load_initial_counties(self, template_dir):
        county_directory = "%s/polygons/county" % (template_dir)

        if not os.path.exists(county_directory):
            os.makedirs(county_directory, mode=0755)

        county_url = "https://www2.census.gov/geo/tiger/TIGER2016/COUNTY/tl_2016_us_county.zip"

        tmp_dir = "/tmp/tiger-county"
        tmp_file = "%s/tl_2016_us_county.zip" % (tmp_dir)

        try:
            os.makedirs(tmp_dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise e

        urllib.urlretrieve(county_url, tmp_file)

        zipfile = ZipFile(tmp_file)
        zipfile.extractall(path=tmp_dir)
        zipfile.close()

        sf = shapefile.Reader(tmp_file.replace("zip", "shp"))
        fields = [f[0] for f in sf.fields[1:]]
        n = len(sf.records())

        self.stdout.write("Loading %d counties" % (n))

        for i in range(0,n):
            if (i+1) % 100 == 0:
                self.stdout.write("%d/%d" % (i+1, n))
            
            r = dict(zip(fields, sf.records()[i]))
            if County.objects.filter(state_fips=r["STATEFP"], county_fips=r["COUNTYFP"]).exists():
                continue

            s = shape_to_geos(sf.shapes()[i], 4326)
            d = {
                "name": r["NAME"].decode("utf-8"),
                "geometry": s,
                "state_fips": r["STATEFP"],
                "county_fips": r["COUNTYFP"],
            }

            county = County(**d)
            county.save()

            gg = GeneratedGeometry(geometry=s, gazetteer_id="county:%s%s" % (r["STATEFP"], r["COUNTYFP"]))
            gg.save()

            county_template_directory = "%s/%d" % (county_directory, r["STATEFP"])
            if not (os.path.exists(county_template_directory)):
                os.makedirs(county_template_directory, mode=0755)

            with open("%s/%s.json" % (county_template_directory, r["COUNTYFP"]), w) as f:
                f.write(s.geojson)

        for f in glob("%s/tl_2016_us_county.*" % (tmp_dir)):
            os.remove(f)

        try:
            os.rmdir(tmp_dir)
        except e:
            pass

        return

    def load_gnis(self, state):
        if not State.objects.filter(abbreviation=state).exists():
            raise CommandError("'%s' is not a valid state" % (state))

        url = 'https://geonames.usgs.gov/docs/stategaz/%s_Features_20171001.zip' % (state)
        tmp_file = '/tmp/%s_Features_20171001.zip' % (state)

        urllib.urlretrieve(url, tmp_file)

        zipfile = ZipFile(tmp_file)
        zipfile.extractall(path="/tmp")
        zipfile.close()

        with open(tmp_file.replace("zip", "txt")) as f:
            lines = [l.strip().split("|") for l in f.readlines()]
    
        lines = lines[1:]
    
        attributes = ['feature_id', 'feature_name', 'feature_class', 'state_alpha', 'state_numeric', 'county_name', 'county_numeric', 'primary_latitude_dms', 'primary_longitude_dms', 'primary_latitude_dec', 'primary_longitude_dec', 'source_latitude_dms', 'source_longitude_dms', 'source_latitude_dec', 'source_longitude_dec', 'elevation_meters', 'elevation_feet', 'map_name', 'date_created', 'date_modified']
    
        num_attributes = len(attributes)
    
        number_of_lines = len(lines)
        current_line_number = 0
        skipped = 0
    
        self.stdout.write("Loading %d for %s" % (number_of_lines, state))
    
        for line in lines:
            current_line_number += 1

            if current_line_number % 1000 == 0:
                print "%d/%d" % (current_line_number, number_of_lines)

    
            if GNIS.objects.filter(feature_id=line[0]).exists():
                skipped += 1
                continue
    
            record = dict(zip(attributes, line))
    
            record['feature_id'] = int(record['feature_id'])
            record['primary_latitude_dec'] = float(record['primary_latitude_dec'])
            record['primary_longitude_dec'] = float(record['primary_longitude_dec'])
            record['source_latitude_dec'] = float(record['source_latitude_dec']) if record['source_latitude_dec'] != '' else None
            record['source_longitude_dec'] = float(record['source_longitude_dec']) if record['source_longitude_dec'] != '' else None
            record['elevation_meters'] = float(record['elevation_meters']) if record['elevation_meters'] else None
            record['elevation_feet'] = float(record['elevation_feet']) if record['elevation_feet'] else None
    
            g = GNIS(**record)
            g.save()
    
        os.remove(tmp_file)
        os.remove(tmp_file.replace("zip", "txt"))

        if skipped > 0:
            self.stdout.write("%d already loaded" % (skipped))
