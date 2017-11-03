from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.template.loader import render_to_string

from fcrepo.objects import FCObject, SemanticValue
from utilities.conversion import UnicodeWriter

import datetime
import json
import os
import re
import requests
import subprocess
import sys

from django.conf import settings

CREATE_SUCCESS = 201
CREATE_FAILED_EXISTS = 409
CREATE_FAILED_TOMBSTONE = 410
PROPERTY_DELETE_SUCCESS = 204 
UPDATE_SUCCESS = 204

def import_template_to_fcrepo(url, template, template_data = {}):
    r = requests.put(url)

    if (r.status_code == CREATE_FAILED_TOMBSTONE):
        return r

    r = requests.patch(url, data=render_to_string(template, template_data))

    if (r.status_code != UPDATE_SUCCESS):
        return r

    return None

def boundeditem_to_fcobject(item, update=False):
    properties = {
        "Abstract": "dcterms:abstract",
        "Access": "dcterms:accessRights",
        "ContentDate": "dcterms:created",
        "DataType": "dcterms:medium",
        "LayerDisplayName": "dcterms:title",
        "LayerId": "dcterms:identifier",
        "Location": "dcterms:references",
        "Originator": "dc:creator",
        "PlaceKeywords": "dcterms:spatial",
        "Publisher": "dc:publisher",
        "ThemeKeywords": "dcterms:subject",
    }

    fco = None

    if update:
        fco = FCObject(url=item.fedora_url, use_objects=True)
    else:
        fco = FCObject()
        fco.namespaces = {
            'dc': 'http://purl.org/dc/elements/1.1/',
            'dcterms': 'http://purl.org/dc/terms/',
        }

    for (k,v) in properties.items():
        if item.__dict__[k] != '""':
            if v == "dcterms:spatial" or v == "dcterms:subject":
                fco[v] = item.__dict__[k].replace('"', "'").split(", ")
            else: 
                fco[v] = item.__dict__[k].replace('"', "'")

    fco["dcterms:created"] = datetime.datetime.strptime(fco["dcterms:created"]._value[0].replace("Z", ".0Z"), "%Y-%m-%dT%H:%M:%S.%fZ")

    #MaxX to MinY as bbox string
    fco["dcterms:bounds"] = "%f,%f,%f,%f" % (item.MinX, item.MinY, item.MaxX, item.MaxY)

    fco._url = item.fedora_url
    fco._item = item
    
    return fco

def import_collection_to_fcrepo(collection, import_items = False):
    t_start_response = requests.post("%s/fcr:tx" % (settings.FCREPO_BASE_URL))
    t_id = t_start_response.headers["location"]

    collection_url = "%s/place/%s" % (t_id, collection.fedora_name)
    
    error = import_template_to_fcrepo(collection_url, "rdf/direct-container.rdf")

    if error:
        rollback(t_id)
        return error

    values = {
        "dc:title": collection.full_name
    }
    namespaces = {
        "dc": "http://purl.org/dc/elements/1.1/"
    }

    error = import_template_to_fcrepo(collection_url, "rdf/update.rdf", {
        "namespaces": { "dc": "http://purl.org/dc/elements/1.1/" },
        "values": { "dc:title": SemanticValue(collection.full_name.replace('"', "'"), object=None, property="title", namespace="dc", initial=True) }
    })

    if error:
        rollback(t_id)
        return error

    commit_response = requests.post("%s/fcr:tx/fcr:commit" % (t_id))

    if (commit_response.status_code != UPDATE_SUCCESS):
        rollback(t_id)
        return commit_response

    if import_items:
        items = collection.item_set.all()

        errors = []

        for item in items:
            error = import_item_to_fcrepo(item)
            if error:
                errors.append(error)

        if errors:
            return errors

    return None

def import_item_to_fcrepo(item):
    #import to fedora repo
    fco = boundeditem_to_fcobject(item)
    
    error = fco.save()

    if error:
        return error

    #save FGDC metadata
    headers = {
        "Content-Disposition": "form-data",
        "filename": "%s-fgdc.xml" % (item.LayerId),
        "Content-Type": "text/xml"
    }
    url = "%s/FGDC" % (item.fedora_url)

    response = requests.put(url, data=item.FgdcText, headers=headers)

    if response.status_code != CREATE_SUCCESS and response.status_code != UPDATE_SUCCESS:
        return response

    return None

def commit(t_id):
    response = requests.post("%s/fcr:tx/fcr:commit" % (t_id))

    return response

def rollback(t_id):
    response = requests.post("%s/fcr:tx/fcr:rollback" % (t_id))

    return response
