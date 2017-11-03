from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import WKTReader
from django.core.management.base import BaseCommand, CommandError

from gazetteer.models import State, Municipality, ShapeFileData, GeneratedGeometry
from gazetteer.views import shape_to_geos

import os
import shapefile

from django.conf import settings

class Command(BaseCommand):
    help = 'Add municipalities to the gazetteer'

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)
        parser.add_argument("shapefile_path", type=str)
        parser.add_argument("--record", type=int, default=0)
        parser.add_argument("--srs", type=int)
        parser.add_argument("--units", type=str)
        parser.add_argument("--state", type=str)
        parser.add_argument("--name_field", type=str)
        parser.add_argument("--county_field", type=str)
        parser.add_argument("--id_field", type=str)
        parser.add_argument("--keep_loaded_shapefile", type=bool, default=False)
        parser.add_argument("--keep_loaded_municipalities", type=bool, default=False)
        parser.add_argument("--template_directory", type=str, default=settings.TEMPLATE_DIRS[0])

    def handle(self, *args, **options):

        task = options["task"]
        shapefile_path = options["shapefile_path"]
        r = options["record"]

        if not task in ("fields", "load"):
            raise CommandError("task must be 'fields' or 'load'")

        if not shapefile_path:
            raise CommandError("A shapefile path must be provided")

        if task == "fields":
            self.show_record(shapefile_path, r)

        if task == "load":
            self.load_shapefile(shapefile_path, options)

    def show_record(self, shapefile_path, r):
        self.stdout.write("Listing shapefile fields along with a record sample")
        self.stdout.write("")

        sf = shapefile.Reader(shapefile_path)
        fields = [f[0] for f in sf.fields[1:]]
        max_length = 0

        for f in fields:
            if len(f) > max_length:
                max_length = len(f)

        format_string = "%" + str(max_length) + "s:"

        record = dict(zip(fields, sf.records()[r]))

        for k in record:
            self.stdout.write(format_string % (k), ending="")
            self.stdout.write(unicode(record[k]))

    def load_shapefile(self, shapefile_path, options):
        srs = options["srs"]
        state = options["state"]
        name_key = options["name_field"]
        county_key = options["county_field"]
        id_key = options["id_field"]
        units = options["units"]

        if not state:
            raise CommandError("A 2 character state code e.g. AK, is required.")

        if State.objects.count() == 0:
            raise CommandError("Initial data must be loaded first. Use 'manage.py gaz create --state=initial'")

        if not name_key:
            raise CommandError("The field name storing the municipality's name must be provided.")

        if not county_key:
            raise CommandError("The field name storing the FIPS code for the muncipality's county must be provided. Shapefiles that do not provide this field are currently not supported.")

        if not id_key:
            raise CommandError("The field name storing the ID to use for municipalities must be provided.")

        if srs == 4326 and not units:
            units = "m"

        sf = shapefile.Reader(shapefile_path)

        fields = [f[0] for f in sf.fields[1:]]
        n = len(sf.records())
    
        self.stdout.write("Loading %d shapes" % (n))
        state_fips = State.objects.get(abbreviation=state).state_fips

        for i in range(0,n):
            g = shape_to_geos(sf.shapes()[i], srs, unit=units)
            r = [str(l) for l in sf.records()[i]]
            r = dict(zip(fields, r))

            if r[name_key].strip() == '':
                continue
    
            if len(r[county_key]) <= 3:
                county_fips = "%3d" % (int(r[county_key]))
            else:
                county_fips = str(r[county_key])[-3:]

    
            sfd = ShapeFileData(geometry=g, record=r, state=state, name=r[name_key].decode("utf-8"), state_fips=state_fips, county_fips=county_fips)
            sfd.save()
            self.stdout.write("%d/%d" % (i+1, n))

        if not options["keep_loaded_municipalities"]:
            self.stdout.write("Deleting current municipalities")
            Municipality.objects.filter(state_fips=state_fips).delete()
            GeneratedGeometry.objects.filter(gazetteer_id__startswith="municipality:%s" % (state_fips)).delete()

        self.stdout.write("Creating %d municipalities" % (ShapeFileData.objects.filter(state=state).distinct("name").count()))

        for sfd in ShapeFileData.objects.filter(state=state).distinct("name"):
            geometry = ShapeFileData.objects.filter(name=sfd.name, state_fips=state_fips, county_fips=sfd.county_fips).aggregate(Union("geometry"))["geometry__union"]
            d = {
                "county_fips": sfd.county_fips,
                "geometry": geometry,
                "place_id": sfd.record[id_key],
                "name": sfd.name,
                "state_fips": state_fips
            }
            
            m = Municipality(**d)
            m.save()

            gg = GeneratedGeometry(geometry=geometry, gazetteer_id="municipality:%s%s-%s" % (state_fips, sfd.county_fips, sfd.record[id_key]))
            gg.save()

            template_dir = options["template_directory"]
            municipality_template_dir = "%s/polygons/municipality/%s/%s" % (template_dir, state_fips, sfd.county_fips)
            if not (os.path.exists(municipality_template_dir)):
                os.makedirs(municipality_template_dir, mode=0755)
            with open("%s/%s.json" % (municipality_template_dir, sfd.record[id_key]), "w") as f:
                f.write(geometry.geojson)

        if not options["keep_loaded_shapefile"]:
            ShapeFileData.objects.filter(state_fips=state_fips).delete()
