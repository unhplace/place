from geoserver.server_models import add_to_geoserver, get_coverage_store
from ogp.models import BoundedItem, ItemCollection
from utilities.conversion import fgdc_to_ogp_csv, image_path_with_fgdc_to_world_file
from utilities.misc import ogp_timestamp_for_now

from PIL import Image
from urllib2 import Request, urlopen

import json
import requests
import os
import csv

from gazetteer.models import Municipality

#from place.settings import GEOSERVER, SOLR_REPO
from django.conf import settings
GEOSERVER = settings.GEOSERVER
SOLR_REPO = settings.SOLR_REPO

#relative image paths are assumed to be relative to the geoserver shared directory
def import_map(image_path, srs, units):
    if not image_path.startswith("/"):
        image_path = "%s/%s" % (GEOSERVER['DATA_PATH'], image_path) 

    (image_path_base, image_ext) = os.path.splitext(image_path)
    world_file_ext = "%s%sw" % (image_ext[1], image_ext[-1])
    world_file_path = "%s.%s" % (image_path_base, world_file_ext)
    fgdc_file_path = "%s.xml" % (image_path_base)
    image_name = os.path.split(image_path)[1].replace(image_ext, "")

    world_file = open(world_file_path, "w")
    image_path_with_fgdc_to_world_file(image_path, world_file, srs, units)
    world_file.close()

    if get_coverage_store(name=image_name):
        saved = True
    else:
        (saved, response, coverage) = add_to_geoserver(image_name, image_path, workspace="ogp", srs=srs, units=units)

    if not saved:
        return (False, response) 

    response = add_to_solr(image_path)
    saved = response.status_code == 200

    if saved:
        directory_path = os.path.split(image_path)[0]

        itemName = image_name
        solrData = json.loads(query_solr("q=Name:%s&wt=json" % (itemName)).read())["response"]["docs"][0]

        del solrData["_version_"]
        del solrData["PlaceKeywordsSynonyms"]
        del solrData["OriginatorSort"]

        solrData["srs"] = srs

        if len(BoundedItem.objects.filter(Name=itemName)) == 0:
            b = BoundedItem(**solrData)
            b.directory_path = directory_path
            if "hurd" in directory_path:
                b.collection = ItemCollection.objects.get(full_name__contains="Hurd")
            b.save()
        else:
            b = BoundedItem.objects.get(Name=itemName)
            b.update_from_dictionary(solrData)
            b.directory_path = directory_path
            b.save()

        return (True, None)
    else:
        return (False, "Could not add to Solr")

def add_to_solr(image_file_path):
    image_file_base = os.path.splitext(image_file_path)[0]
    csv_file_path = image_file_base + ".csv"
    fgdc_file_path = image_file_base + ".xml"

    (h,r) = fgdc_to_ogp_csv(fgdc_file_path, True)
    csv_file = open(csv_file_path, "w")
    csv_file.writelines([h,r])
    csv_file.close()

    url = "%s/update/csv?commit=true&stream.file=%s&stream.contentType=text/csv;charset=utf-8&overwrite=true" % (SOLR_REPO['URL'], csv_file_path)
    response = requests.get(url=url)

    os.remove(csv_file_path)

    return response

def query_solr(query_string):
    solr_url = "http://place.sr.unh.edu:8080/solr/select?%s" % (query_string)
    request = Request(solr_url)
    response = urlopen(request)

    return response
