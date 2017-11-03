from django.contrib.gis.geos import WKTReader, Polygon, MultiPolygon, GEOSException
from django.db import connections
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render

from gazetteer.models import GeneratedGeometry, Municipality, GNIS, ShapeFileData, State, County
from nominatim.models import CountryName, USState, USStateCounty
from ogp.views import bad_request, completed_request
from utilities.conversion import srs_to_latlng

def bbox_polygon(request):
    gazetteer_id = request.GET.get("id")

    if not gazetteer_id:
        return bad_request(["MISSING: id"])

    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT ST_AsGeoJSON(Box2d(gazetteer_generatedgeometry_test.geometry)) from gazetteer_generatedgeometry_test where gazetteer_id=%s", [gazetteer_id])
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
    states = [{"name": s.name, "id": s.state_fips, "next_entries": s.counties.count()} for s in State.objects.all().order_by("name")]

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

    counties = [{"name": c.name, "id": c.identifier, "next_entries": c.municipalities.count()} for c in County.objects.filter(state_fips=state_fips).order_by("name")]

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

def shape_to_geos(shape, srs, unit="m"):
    args = []

    for point_index in range(0, len(shape.points)):
        if point_index in shape.parts:
            args.append([])
        point = shape.points[point_index]
        point = srs_to_latlng(point[0], point[1], srs, unit)
        args[-1].append([point[1], point[0]])

    polygon = Polygon(*args)

    try:
        polygon.union(polygon) #this will fail if the polygon is actual a MultiPolygon
    except GEOSException as e:
        polygon = MultiPolygon([Polygon(p) for p in polygon])

    return polygon

def load_shapefile(sf, srs, state, state_fips, name_key, unit="m", title_case=False, county_key=None):
    fields = [f[0] for f in sf.fields[1:]]
    n = len(sf.records())

    for i in range(0,n):
        g = shape_to_geos(sf.shapes()[i], srs, unit=unit)
        if title_case:
            r = [str(l).title() for l in sf.records()[i]]
        else:
            r = [str(l) for l in sf.records()[i]]
        r = dict(zip(fields, r)) 

        county_fips = "%03d" % (int(r[county_key])) if county_key else None

        sfd = ShapeFileData(geometry=g, record=r, state=state, name=r[name_key], state_fips=state_fips, county_fips=county_fips)
        sfd.save()
        print "%d/%d" % (i+1, n)

def add_gnis(file_name):
    print file_name

    with open(file_name) as f:
        lines = [l.strip().split("|") for l in f.readlines()]

    lines = lines[1:]

    attributes = ['feature_id', 'feature_name', 'feature_class', 'state_alpha', 'state_numeric', 'county_name', 'county_numeric', 'primary_latitude_dms', 'primary_longitude_dms', 'primary_latitude_dec', 'primary_longitude_dec', 'source_latitude_dms', 'source_longitude_dms', 'source_latitude_dec', 'source_longitude_dec', 'elevation_meters', 'elevation_feet', 'map_name', 'date_created', 'date_modified']

    num_attributes = len(attributes)

    number_of_lines = len(lines)
    current_line_number = 0
    skipped = 0

    print "Loading %d" % (number_of_lines)

    for line in lines:
        current_line_number += 1

        if current_line_number % 1000 == 0:
            print "%d/%d" % (current_line_number + 1, number_of_lines)


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

    return skipped
