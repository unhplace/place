from django.contrib.gis.geos import Polygon, Point, WKBReader
from django.db import connections
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, HttpResponseRedirect, Http404
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt

import httplib2
import json
import os
from osgeo import gdal
from PIL import Image
import re
import requests
from urllib2 import Request, urlopen

from gazetteer.models import GeneratedGeometry
from nominatim.models import Placex
from ogp.importing import import_map, query_solr
from ogp.models import BoundedItem, Category, ItemCollection, DownloadRequest
from utilities.misc import name_from_filepath
from utilities.conversion import fgdc_to_ogp_csv, latlng_to_srs

from django.conf import settings

def map(request):
    return render(request, "map.html")

def solr_select(request):
    query_string = request.META['QUERY_STRING']
    response = query_solr(query_string)
    return completed_request([response])

def query_solr(query_string):
    solr_url = "%s/select?%s" % (settings.SOLR_REPO["URL"], query_string)
    request = Request(solr_url)
    response = urlopen(request)

    return response.read()

def download_items(request):
    layers = request.POST.get("layers")
    email_address = request.POST.get("email")
    wfs_format = request.POST.get("wfsFormat")

    if not email_address:
        return bad_request(["MISSING: email"])

    if not layers and not external_layers:
        return bad_request(["MISSING: layers"])

    if wfs_format == "shapefile":
        wfs_format = "shape-zip"
    elif wfs_format == "gml":
        wfs_format = "GML3"
    elif wfs_format == "kml":
        wfs_format = "KML"
    else:
        wfs_format = "application/json"

    layers = layers.split(",") if layers else []

    if (len(layers)) > 10:
        return completed_request(["Please select 10 or fewer items to download"])

    items = []
    for layer in layers:
        items.append(BoundedItem.objects.get(LayerId=layer))

    dr = DownloadRequest(email_address=email_address, wfs_format=wfs_format)
    dr.save()
    dr.items = items
    dr.active = True
    dr.save()

    return completed_request(["An email with your download link will be sent to %s" % (email_address)])

def originators(request):
    name_start = request.GET.get("name")
    gazetteer_id = request.GET.get("polygon")
    bbox = request.GET.get("bbox")

    geometry = None
    statement = ""
    parameters = []

    if gazetteer_id:
        geometry = GeneratedGeometry.objects.get(gazetteer_id=gazetteer_id).geometry
    elif bbox:
        #would also need to set srs
        pass

    if name_start and geometry:
        pass
    elif name_start and not geometry:
        pass
    elif not name_start and geometry:
        pass
    else: #no parameters
        statement = 'SELECT DISTINCT "Originator", COUNT("Originator") FROM ogp_item GROUP BY "Originator" ORDER BY "Originator"'

    originators = []

    with connections["default"].cursor() as c:
        c.execute(statement, parameters)
        for row in c.fetchall():
            originators.append({"name": row[0], "count": row[1]})

    return completed_request(originators)

@csrf_exempt
def nominatim_request(request):
    url = "http://epscor-pv-2.sr.unh.edu%s?%s" % (request.path, request.META['QUERY_STRING'])

    return external_request(url)

@csrf_exempt
def external_request(url, content_type = None, method="GET"):
    if not url.startswith("http://"):
        url = "http://%s" % (url)

    connection = httplib2.Http()
    headers, content = connection.request(url, method)

    response = HttpResponse(content, content_type = content_type or headers["content-type"])
    return response_with_headers(response)

@csrf_exempt
def geoserver_request(request):
    path = request.path
    url = "%s%s?%s" % (settings.TOMCAT_BASE_URL, path, request.META['QUERY_STRING'])
    
    return external_request(url)

@csrf_exempt
def solr_request(request):
    if not request.META.get("REMOTE_ADDR").startswith("132.177"):
        return bad_request(["Remote Solr access is currently unavailable pending the finalization of metadata."])

    path = request.path
    query = request.META['QUERY_STRING']
    url = "%s%s?%s" % (settings.TOMCAT_BASE_URL, path, query)
    content_type = None
    if "wt=json" in url:
        content_type = "application/json"

    return external_request(url, content_type)

@csrf_exempt
def ogp_request(request):
    path = request.path
    query = request.META['QUERY_STRING']
    url = "%s%s?%s" % (settings.TOMCAT_BASE_URL, path, query)

    return external_request(url)

@csrf_exempt
def external_solr_request(request):
    hostname = request.GET.get("hostname")
    path = request.GET.get("path", "solr")
    query = request.GET.get("query")

    errors = []
    if not hostname:
        errors.append("MISSING: hostname")
    if not path:
        errors.append("MISSING: path")
    if errors:
        return bad_request(errors)

    if hostname.startswith("place"):
        hostname = "place.sr.unh.edu:8080"

    url = "http://%s/%s/select?%s" % (hostname,path,query)

    content_type = None
    if "wt=json" in url:
        content_type = "application/json"

    return external_request(url, content_type)

@csrf_exempt
def external_wfs_request(request, hostname):
    wfs_query = request.META["QUERY_STRING"]
    url = "%s/wfs?%s" % (hostname, wfs_query)

    return external_request(url, method=request.method)

@csrf_exempt
def external_wms_request(request, hostname):
    wms_query = request.META["QUERY_STRING"]
    url = "%s/wms?%s" % (hostname, wms_query)

    return external_request(url, method=request.method)

@csrf_exempt
def external_reflect_request(request, hostname):
    wms_query = request.META["QUERY_STRING"]
    url = "%s/wms/reflect?%s" % (hostname, wms_query)

    return external_request(url, method=request.method)

def find_items(request):
    bounds_string = request.GET.get("bbox")
    point_string = request.GET.get("coord")
    gazetteer_polygon_id = request.GET.get("polygon")
    osm_id = request.GET.get("osm_id")
    field_string = request.GET.get("return")
    years_string = request.GET.get("years")
    keyword_string = request.GET.get("keyword")
    originator_string = request.GET.get("originator")
    datatype_string = request.GET.get("datatype")
    start = int(request.GET.get("start", 0))
    end = int(request.GET.get("end", 0))
    grouped = request.GET.get("grouped")
    group_id = request.GET.get("id")

    if not (bounds_string or gazetteer_polygon_id or point_string or osm_id) or not field_string:
        errors = []

        if not (bounds_string or gazetteer_polygon_id or point_string or osm_id):
            errors.append("MISSING: osm_id, bbox, polygon, point")
        if not field_string:
            errors.append("MISSING: return")

        return bad_request(errors)

    query = Q()

    if gazetteer_polygon_id:
        query &= Q(bounds__intersects=GeneratedGeometry.objects.get(gazetteer_id=gazetteer_polygon_id).geometry)
    elif osm_id:
        polygon = None

        try:
            polygon = Placex.objects.get(osm_id=osm_id).geometry
        except MultipleObjectsReturned:
            with connections["nominatim"].cursor() as c:
                c.execute('select ST_Collect("placex"."geometry") from "placex" where "placex"."osm_id"=%s', [osm_id])
                polygon = WKBReader().read(c.fetchone()[0])

        query &= Q(bounds__intersects=polygon)
    if point_string:
        (lng, lat) = [float(x) for x in point_string.split(",")]
        point = Point(lat,lng)
    elif bounds_string:
        (minX, minY, maxX, maxY) = (float(b) for b in bounds_string.split(","))
        bounds_polygon = Polygon(((minX, minY), (minX, maxY), (maxX, maxY), (maxX, minY), (minX, minY)))
        query &= Q(bounds__intersects=bounds_polygon)

    if keyword_string:
        keyword_query =  Q(LayerDisplayName__icontains=keyword_string)
#       keyword_query =  Q(Name__icontains=keyword_string)
        keyword_query |= Q(PlaceKeywords__icontains=keyword_string)
        keyword_query |= Q(ThemeKeywords__icontains=keyword_string)
        keyword_query |= Q(collection__full_name__icontains=keyword_string)
        query &= keyword_query

    if originator_string:
        query &= Q(Originator__icontains=originator_string)

    if datatype_string:
        datatype_query = Q()
        for datatype in datatype_string.split(","):
            datatype_query |= Q(DataType=datatype)
        query &= datatype_query

    #dates are strings in the format %Y-%m-%dT%H:%M:%SZ
    if years_string:
        (start_year, end_year) = years_string.split("-")
        date_query = Q()

        if (start_year):
            date_query &= Q(ContentDate__gt=start_year)
        if (end_year):
            date_query &= Q(ContentDate__lt=end_year)

        query &= date_query

    if grouped == "collection":
        groups = []

        collections = [ItemCollection.objects.get(Q(short_name = group_id) | Q(full_name = group_id))] if group_id else ItemCollection.objects.all().order_by("external", "short_name") 

        for ic in collections: 
            items = BoundedItem.objects.filter(query & Q(collection=ic, collection__enabled = True)).order_by("LayerDisplayName")

            if items.count() == 0:
                continue

            total_number = items.count()
            items = items[start:end] if end else items
            
            name = ic.short_name if not ic.external else ic.full_name
            groups.append({"name": name, "id": ic.id, "items": [x.as_dictionary(field_string) for x in items], "totalNumber": total_number})
        return completed_request({"groups": groups})
    elif grouped == "datatype":
        groups = []

        data_types = {}

        if group_id == "Maps and Images":
            data_types["Maps and Images"] = Q(DataType="Raster") | Q(DataType="Paper Map")
        elif group_id:
            data_types[group_id] = Q(DataType=group_id)
        else:
            data_types["Book"] = Q(DataType="Book")
            data_types["Line"] = Q(DataType="Line")
            data_types["Maps and Images"] = Q(DataType="Raster") | Q(DataType="Paper Map")
            data_types["Point"] = Q(DataType="Point")
            data_types["Polygon"] = Q(DataType="Polygon")

        for data_type in data_types:
            data_type_query = data_types[data_type]
            items = BoundedItem.objects.filter(query & data_type_query).order_by("LayerDisplayName")
            total_number = items.count()
            items = items[start:end] if end else items
            groups.append({"name": data_type, "items": [x.as_dictionary(field_string) for x in items], "totalNumber": total_number, "id": data_type})

        return completed_request({"groups": groups})
    elif grouped == "category":
        groups = []

        if not group_id:
            misc_query = Q()
            for c in Category.objects.all().order_by("name"):
                items = c.items.filter(query).order_by("LayerDisplayName")
                total_number = items.count()
                items = items[start:end] if end else items
                groups.append({"name": c.name, "items": [x.as_dictionary(field_string) for x in items], "totalNumber": total_number, "id": c.id})
                misc_query = misc_query & ~Q(ThemeKeywords__icontains=c.keyword)
    
            misc_items = BoundedItem.objects.filter(query & misc_query).order_by("LayerDisplayName")
            misc_total = misc_items.count()
            misc_items = misc_items[start:end] if end > 0 else misc_items
            groups.append({
                "name": "Uncategorized",
                "items": [x.as_dictionary(field_string) for x in misc_items],
                "totalNumber": misc_total,
                "id": "misc"
            })
        elif group_id == "Uncategorized":
            misc_query = Q()
            for c in Category.objects.all().order_by("name"):
                misc_query = misc_query & ~Q(ThemeKeywords__icontains=c.keyword)
            misc_items = BoundedItem.objects.filter(query & misc_query).order_by("LayerDisplayName")
            misc_total = misc_items.count()
            misc_items = misc_items[start:end] if end > 0 else misc_items
            groups.append({
                "name": "Uncategorized",
                "items": [x.as_dictionary(field_string) for x in misc_items],
                "totalNumber": misc_total,
                "id": "misc"
            })
        elif group_id:
            c = Category.objects.get(name=group_id)
            items = c.items.filter(query).order_by("LayerDisplayName")
            total_number = items.count()
            items = items[start:end] if end else items
            groups.append({"name": c.name, "items": [x.as_dictionary(field_string) for x in items], "totalNumber": total_number, "id": c.id})

        return completed_request({"groups": groups})
    elif grouped == "year":
        groups = []
        years = {}
        items = BoundedItem.objects.filter(query).order_by("LayerDisplayName")

        for item in items:
            year = item.ContentDate[0:4]
            if not year in years:
                years[year] = []
            years[year].append(item)
        for year in years:
            groups.append({"name": unicode(year), "items": [x.as_dictionary(field_string) for x in years[year]]})

        return completed_request({"groups": groups})
    else:
        items = BoundedItem.objects.filter(query).order_by("LayerDisplayName")
        total_number = items.count()
        items = items[start:end] if end else items
        
        groups = [{"name": "All Items Alphabetically", "items": [x.as_dictionary(field_string) for x in items], "totalNumber": total_number, "id": "all"}]

        return completed_request({"groups": groups})

def items_for_layers(request):
    layers = request.GET.get("layers")
    field_string = request.GET.get("return")

    if not layers:
        return bad_request(["MISSING: layers"])
    if not field_string:
        return bad_request(["MISSING: return"])

    layers = layers.split(",")

    items = BoundedItem.objects.filter(LayerId__in=layers)

    return completed_request([x.as_dictionary(field_string, include_collection=True) for x in items])

@csrf_exempt
def minimal_ogp_import(request):
    image_path = request.GET.get("image_path")
    srs = request.GET.get("srs", "EPSG:3445")
    units = request.GET.get("units", "ft")
    no_image = request.GET.get("no_image")

    if not image_path or not srs or not units:
        errors = []

        if not image_path:
            errors.append("MISSING: image_path")
        if not srs:
            errors.append("MISSING: srs")
        if not units:
            errors.append("MISSING: units")

        return bad_request(errors)

    extraData = {
        "DataType": "Raster",
        "Originator": "Unknown",
        "Publisher": "Unknown",
        "Abstract": "No Abstract"
    }

    if request.GET.get("bbox"):
        (minX, minY, maxX, maxY) = request.GET.get("bbox").split(",")
        extraData["MinX"] = minX
        extraData["MinY"] = minY
        extraData["MaxX"] = maxX
        extraData["MaxY"] = maxY
        extraData["ContentDate"] = request.GET.get("ContentDate")
        extraData["LayerDisplayName"] = request.GET.get("LayerDisplayName")
    else:
        for f in ["MinX", "MaxX", "MinY", "MaxY", "ContentDate", "LayerDisplayName"]:
            extraData[f] = request.GET.get(f)

    xml_string = render_to_string("fgdc_stub.xml", extraData)

    fgdc_file_path = "%s.xml" % (os.path.splitext(image_path)[0])

    fgdc_file = open(fgdc_file_path, "w")
    fgdc_file.write(xml_string)
    fgdc_file.close()

    return import_to_ogp(request)

def import_item(request):
    import_type = request.GET.get("type")

    if not import_type:
        return bad_request(["MISSING: type"])
    
    if type in ("Scanned+Map", "Scanned Map", "Paper+Map", "Paper Map"):
        return import_to_ogp(request)
    elif type == "Book":
        return import_pdf(request)

@csrf_exempt
def import_to_ogp(request):
    image_path = request.GET.get("image_path")
    srs = request.GET.get("srs")
    units = request.GET.get("units")

    if None in [image_path, srs, units]:
        errors = []

        if not image_path:
            errors.append("MISSING: image_path")
        if not srs:
            errors.append("MISSING: srs")
        if not units:
            errors.append("MISSING: units")

        return bad_request(errors)

    (saved, response) = import_map(image_path, srs, units)

    if saved:
        return completed_request()
    else:
        return bad_request([response])

@csrf_exempt
def import_pdf(request):
    pdf_path = request.GET.get("pdf_path")
    bbox = request.GET.get("bbox")

    errors = []

    if not pdf_path:
        errors.append("MISSING: pdf_path")
    if not bbox:
        errors.append("MISSING: bbox")

    if errors:
        return bad_request(errors)

    directory_path = os.path.split(pdf_path)[0]
    file_name = os.path.split(pdf_path)[1]
    name = os.path.splitext(file_name)[0]
    year = name.split("_")[0].replace("neigc","")
    section = int(name.split("_")[1].replace("sec", ""))
    section_title = None

    if section == 0:
        section_title = "Intro"
    else:
        section_title = "Section %d" % section

    (MinX, MinY, MaxX, MaxY) = bbox.split(",")

    fields = {
        "Onlink": "",
        "DataType": "Book",
        "MinX": MinX,
        "MaxX": MaxX,
        "MinY": MinY,
        "MaxY": MaxY,
        "ContentDate": year,
        "Originator": "New England Intercollegiate Geological Conference",
        "Publisher": "New England Intercollegiate Geological Conference",
        "Abstract": "No abstract",
        "LayerDisplayName": "NEIGC %s Excursion - %s" % (year, section_title),
        "Institution": "UNH"
    }

    xml_string = render_to_string("fgdc_stub.xml", fields)
    fgdc_file_path = "%s/%s.xml" % (directory_path, name)
    csv_file_path = "%s/%s.csv" % (directory_path, name)

    fgdc_file = open(fgdc_file_path, "w")
    fgdc_file.write(xml_string)
    fgdc_file.close()

    (h,r) = fgdc_to_ogp_csv(fgdc_file_path, True)
    csv_file = open(csv_file_path, "w")
    csv_file.writelines([h,r])
    csv_file.close()

    url = "%s/update/csv?commit=true&stream.file=%s&stream.contentType=text/csv;charset=utf-8&overwrite=true" % (settings.SOLR_REPO["URL"], csv_file_path)
    response = requests.get(url=url)

    os.remove(csv_file_path)

    if response.status_code == 200:
        item_name = name

#       solrData = json.loads(query_solr("q=Name:%s&wt=json" % (itemName)).read())["response"]["docs"][0]
        solrData = json.loads(requests.get("%s/select?q=Name:%s&wt=json" % (settings.SOLR_REPO["URL"], item_name)).text)

        solrData = solrData["response"]["docs"][0]

        del solrData["_version_"]
        del solrData["PlaceKeywordsSynonyms"]
        del solrData["OriginatorSort"]

        solrData["srs"] = 4326

        if len(BoundedItem.objects.filter(Name=item_name)) == 0:
            b = BoundedItem(**solrData)
            b.directory_path = directory_path
            b.collection = ItemCollection.objects.get(full_name__contains="Intercollegiate")
            b.save()
        else:
            b = BoundedItem.objects.get(Name=item_name)
            b.update_from_dictionary(solrData)
            b.directory_path = directory_path
            b.save()

        return completed_request()

    return completed_request([response.status_code])

@csrf_exempt
def link_for_layer(request):
    (item, error_response) = item_from_request(request)
    if error_response:
        return error_response

    try:
        url = "%s/%s/%s" % (settings.ONLINK_BASE, item.collection.abbreviated_name, item.Name)
        return HttpResponseRedirect(url)
    except:
        pass

    url = re.findall("\<onlink\>.*\<\/onlink\>", item.FgdcText)[0]
    url = re.sub("<\/?onlink\>|&..;|URL:", "", url)

    if url:
        return HttpResponseRedirect(url)
    else:
        raise Http404


@csrf_exempt
def abstract_for_layer(request):
    (item, error_response) = item_from_request(request)
    if error_response:
        return error_response

    return response_with_headers(HttpResponse(item.Abstract, content_type="text/plain"))

@csrf_exempt
def metadata_for_layer(request):
    (item, error_response) = item_from_request(request)
    if error_response:
        return error_response

    if not item.collection.metadata_available:
        return HttpResponse("Metadata is not available for this item.", content_type="text/plain")

    return response_with_headers(HttpResponse(item.FgdcText, content_type="text/xml"))

def item_from_request(request):
    layerID = request.GET.get("id")

    if not layerID:
        return (None, bad_request(["MISSING: id"]))

    item = None

    try:
        item = BoundedItem.objects.get(LayerId=layerID)
    except:
        return (None, bad_request(["INVALID: %s" % (layerID)]))

    return (item, None)

def bbox_for_layers(request):
    layers = request.GET.get("layers")

    if not layers:
        return bad_request(["MISSING: layers"])

    layers = layers.split(",")

    c = connections["default"].cursor()
    c.execute('select ST_AsGeoJSON(Box2d(ST_Collect("ogp_boundeditem"."bounds"))) from "ogp_boundeditem","ogp_item" where "ogp_item"."LayerId" like any(%s) and "ogp_boundeditem"."item_ptr_id" = "ogp_item"."id"', [layers])

    return completed_request(json.loads(c.fetchone()[0]))

def items_at_coord(request):
    coord = request.GET.get("coord")
    fields = request.GET.get("fields")

    if not coord:
        return bad_request(["MISSING: coord"])

    (lng,lat) = [float(x) for x in coord.split(",")]
    point = Point(lng,lat)

    items = BoundedItem.objects.filter(bounds__intersects=point, Institution = "UNH").order_by("ContentDate", "LayerDisplayName")

    return completed_request([b.as_dictionary(fields,True) for b in items])

def display_page(request, page, content_type="text/html"):
    if page.endswith(".json"):
        content_type = "application/json"

    try:
        return response_with_headers(render(request, page, content_type=content_type))
    except:
        raise Http404

def bad_request(errors):
    return HttpResponseBadRequest(json.dumps({"version": 1, "completed": False, "errors": errors}), content_type="application/json")

def completed_request(response=[]):
    http_response = HttpResponse(json.dumps({"version": 1, "completed": True, "response": response}), content_type="application/json")

    return response_with_headers(http_response)

def plain_json_request(response = {}):
    return response_with_headers(HttpResponse(json.dumps(response), content_type="application/json"))

def response_with_headers(response):
    response["Cache-Control"] = "max-age=3600"
    return response
