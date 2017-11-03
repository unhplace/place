from django.contrib.gis.geos import WKTReader, Polygon
from django.db import connections
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from gazetteer.models import GeneratedGeometry, Municipality, GNIS
from nominatim.models import CountryName, USState, USStateCounty
from ogp.views import bad_request, completed_request
from utilities.conversion import srs_to_latlng

import shapefile

# Create your views here.

def bbox_polygon(request):
    gazetteer_id = request.GET.get("id")

    if not gazetteer_id:
        return bad_request(["MISSING: id"])

    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT ST_AsGeoJSON(Box2d(gazetteer_generatedgeometry.geometry)) from gazetteer_generatedgeometry where gazetteer_id=%s", [gazetteer_id])
        geojson = cursor.fetchone()[0]

    return HttpResponse(geojson, content_type="application/json")

def gazetteer_countries(request):
    language_code = request.GET.get("language", "en")
    countries = [{"name": c.name_for_language(language_code), "id": c.country_code} for c in CountryName.objects.all()]
    countries.sort(key=lambda c: c["name"])

    return completed_request(countries)

def country_polygon(request):
    country = request.GET.get("id")

    if not country:
        return bad_request(["MISSING: id"])

    country = country.lower()

    return render(request, "polygons/country/%s.json" % (country), content_type="application/json")


def gazetteer_states(request):
    states = [{"name": s.state, "id": s.state_fips, "next_entries": s.counties.count()} for s in USState.objects.all().distinct("state").order_by("state")]

    return completed_request(states)

def state_polygon(request):
    state_fips = request.GET.get("id")

    if not state_fips:
        return bad_request(["MISSING: id"])

    return render(request, "polygons/state/%s.json" % (state_fips), content_type="application/json")

def counties_for_state(request):
    state_fips = request.GET.get("id")

    if not state_fips:
        return bad_request(["MISSING: id"])

    counties = [{"name": c.county, "id": c.fips, "next_entries": c.municipalities.count()} for c in USStateCounty.objects.filter(state_fips=state_fips).order_by("county").distinct("county")]

    return completed_request(counties)

def county_polygon(request):
    fips = request.GET.get("id")

    if not fips:
        return bad_request(["MISSING: id"])

    state_fips = fips[:2]
    county_fips = fips[2:]

    return render(request, "polygons/county/%s/%s.json" % (state_fips, county_fips), content_type="application/json")

def municipalities_for_county(request):
    fips = request.GET.get("id")

    if not fips:
        return bad_request(["MISSING: id"])

    municipalities = [{ 
        "name": m.name, 
        "id": "%s%s-%s" % (m.state_fips, m.county_fips, m.identifier),
        "next_entries": 0,
    } for m in Municipality.objects.filter(state_fips = fips[:2], county_fips = fips[2:]).order_by("name")]

    return completed_request(municipalities)

def municipality_polygon(request):
    m_id = request.GET.get("id")

    if not m_id:
        return bad_request(["MISSING: id"])

    (fips, identifier) = m_id.split("-")

    return render(request, "polygons/municipality/%s/%s/%s.json" % (fips[:2], fips[2:], identifier), content_type="application/json")

def add_gnis(file_name):
    print file_name

    with open(file_name) as f:
        lines = [l.strip().split("|") for l in f.readlines()]

    attributes = lines[0]
    lines = lines[1:]

    num_attributes = len(attributes)

    number_of_lines = len(lines)
    current_line_number = 0
    skipped = 0

    print "%d/%d" % (current_line_number, number_of_lines)
    for line in lines:
        current_line_number += 1
        if current_line_number % 1000 == 0:
            print "%d/%d" % (current_line_number, number_of_lines)

        if GNIS.objects.filter(feature_id=line[0]).count():
            skipped += 1
            continue

        g = GNIS()
        for i in range(0,num_attributes):
            v = line[i] or None
            g.__dict__[attributes[i]] = v
        g.save()

    return skipped

#for testing
def municipalities_in_county(fips):
    county = USStateCounty.objects.filter(fips=fips)[0].county
    gnis = GNIS.objects.filter(feature_class="Civil", state_numeric=fips[:2], county_numeric=fips[2:]).exclude(feature_name__startswith="State of").exclude(feature_name=county)

    ewkt = None
    results = []
    rows = None

    with connections["nominatim"].cursor() as c:
        c.execute("select ST_AsEWKT(ST_Union(us_statecounty.the_geom)) from us_statecounty where fips=%s", [fips])
        ewkt = c.fetchone()[0]
        c.execute("select placex.name->'name', placex.place_id, placex.indexed_date, ST_Area(placex.geometry) from placex where class='boundary' and type='administrative' and ST_Intersects(placex.geometry, %s) and ST_Area(ST_Difference(placex.geometry, %s)) <  0.5 * ST_Area(placex.geometry) and ST_Area(placex.geometry) < 0.99*ST_Area(%s) order by placex.name->'name', ST_Area(placex.geometry) desc", [ewkt,ewkt,ewkt])
        rows = c.fetchall()

    last_place_name = None
    for row in rows:
        name = row[0]
        gnis_name = " of %s" % (name)

        if name == last_place_name:
            print "Duplicate (%s): %s" % (name, row)
            continue

        if ("'" in name):
            name_count = gnis.filter(feature_name__endswith=gnis_name).count()
            if name_count > 1:
                print "Too many (%s): %s" % (name, row)
                continue
            elif name_count == 0:
                without_apos_count = gnis.filter(feature_name__endswith=gnis_name.replace("'", "")).count()
                if without_apos_count == 0:
                    print "Can't find (%s): %s" % (gnis_name.replace("'",""), row)
                    continue
                elif without_apos_count == 1:
                    gnis_name = name.replace("'","")
                else: #with_apos_count > 1
                    print "Too many (%s) %d: %s" % (gnis_name.replace("'", ""), without_apos_count, row)


        count = gnis.filter(feature_name__endswith=gnis_name).count()

        if count == 0:
            print "Can't find (%s): %s" % (gnis_name, row)
        elif count == 1:
            results.append(row)
        else: # count > 1
            print "Too many (%s) %d: %s" % (gnis_name, count, row)

        last_place_name = name

    return results

def add_vermont():
    vt_names = []
    vt_dict = {}
    with open("/tmp/vt_names") as f:
        vt_names = [l.strip() for l in f.readlines()]

    for name in vt_names:
        vt_name = name
        gnis_name = None
        municipality_name = None
        
        if " - " in name:
            (vt_name, gnis_name, municipality_name) = name.split(" - ")
        
        if gnis_name:
            gnis = GNIS.objects.get(feature_class="Civil", state_alpha="VT", feature_name=gnis_name)
        else:
            gnis = GNIS.objects.filter(feature_class="Civil", state_alpha="VT", feature_name__endswith="of %s" % (vt_name)).exclude(feature_name__startswith="Village of")[0]

        vt_dict[vt_name] = { "vt_name": vt_name, "gnis_name": gnis_name or vt_name, "municipality_name": municipality_name or vt_name, "gnis": gnis }

    wktr = WKTReader()
    sf = shapefile.Reader("/tmp/Boundary_BNDHASH_region_towns.shp")

    for i in range(0,255):
        shape = sf.shape(i)
        record = sf.record(i)

        wkt = "POLYGON (("
        for p in shape.points:
            p = srs_to_latlng(p[0],p[1],2852)
            wkt += "%f %f," % (p[1], p[0])
        wkt = wkt[:-1]
        wkt += "))"

        try:
            polygon = wktr.read(wkt)
        except:
            p = srs_to_latlng(shape.points[0][0], shape.points[0][1], 2852)
            wkt = wkt[:-2]
            wkt += ",%f %f))" % (p[1], p[0])
            polygon = wktr.read(wkt)

        dict_entry = vt_dict[record[6]]
        gnis = dict_entry["gnis"]

        m = Municipality()
        m.name = dict_entry["municipality_name"]
        m.geometry = polygon
        m.state_fips = gnis.state_numeric
        m.county_fips = gnis.county_numeric
        m.gnis = gnis.feature_id
        m.save()
        print "Saved %s" % (m)

def add_maine_data():
    sf = shapefile.Reader("/net/home/cv/iatkin/me/metwp24p.shp")
    wktr = WKTReader()

    for me_index in range(0,8422):
        m = MaineData()
        m.name = sf.record(me_index)[0]
        m.county = sf.record(me_index)[4]
        m.data_type = sf.record(me_index)[12]

        args = []
        shape = sf.shape(me_index)

        for point_index in range(0, len(shape.points)):
            if point_index in shape.parts:
                args.append([])
            point = shape.points[point_index]
            point = srs_to_latlng(point[0], point[1], 26919)
            args[-1].append([point[1], point[0]])

        try:
            polygon = Polygon(*args)
        except:
            print me_index
            continue

        m.geometry = polygon
        m.save()

        if me_index % 1000 == 0:
            print "%04d/8422" % (me_index)

def import_maine_data():
    base_query = Q(feature_class="Civil") & Q(state_alpha="ME")
    maine_municipalities = MaineData.objects.filter(skip=False).distinct("name").order_by("name")

    for municipality in maine_municipalities:
        name = municipality.name
        name_query = None

        township_query = Q(feature_name=name.replace("Twp", "Township")) | Q(feature_name="Township of %s" % (name.replace(" Twp","")))
        plantation_query = Q(feature_name=name.replace("Plt", "Plantation")) | Q(feature_name="Plantation of %s" % (name.replace(" Plt","")))

        if " Twp" in name:
            name_query = Q(feature_name=name.replace("Twp", "Township")) | Q(feature_name="Township of %s" % (name.replace(" Twp","")))
        elif name.endswith(" Plt"):
            name_query = Q(feature_name=name.replace("Plt", "Plantation")) | Q(feature_name="Plantation of %s" % (name.replace(" Plt","")))
        else:
            name_query = Q(feature_name=name) | Q(feature_name ="Town of %s" % (name)) | Q(feature_name ="City of %s" % (name))

        gnis = GNIS.objects.filter(base_query, name_query)

        if gnis.count() == 0:
            gnis = GNIS.objects.filter(state_alpha="ME", feature_class="Island", feature_name=name)

        if gnis.count() > 0:
            gnis = gnis[0]
        else:
            gnis = None

        args = {"name": None, "geometry": None, "state_fips": None, "county_fips": None, "gnis": None}

        if gnis:
            args["name"] = name
            args["state_fips"] = gnis.state_numeric
            args["county_fips"] = gnis.county_numeric
            args["gnis"] = gnis.feature_id
        else:
            args["name"] = name
            args["state_fips"] = "23"

            try:
                args["county_fips"] = "%03d" % (int(municipality.county))
            except:
                print municipality
                continue

        with connections["default"].cursor() as c:
            c.execute("select ST_AsEWKT(ST_Collect(geometry)) from gazetteer_mainedata where name = %s", [name])
            args["geometry"] = c.fetchone()[0]

        m = Municipality(**args)
        m.save()


def shape_to_geos(shape, srs, units="m"):
    args = []

    for point_index in range(0, len(shape.points)):
        if point_index in shape.parts:
            args.append([])
        point = shape.points[point_index]
        point = srs_to_latlng(point[0], point[1], srs, units)
        args[-1].append([point[1], point[0]])

    polygon = Polygon(*args)

    return polygon
