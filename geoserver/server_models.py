import requests
from django.template.loader import render_to_string
from utilities.conversion import *
from utilities.misc import is_string
from PIL import Image

from django.conf import settings
GEOSERVER = settings.GEOSERVER

def get_workspace(json={}, name=None):
    if not 'name' in json and not name:
        return None
    elif 'name' in json:
        name = json['name']

    url = "%s/workspaces/%s" % (GEOSERVER['REST_URL'], name)
    headers = { "Accept" : "text/json" }

    response = requests.get(url, auth = (GEOSERVER['USER'], GEOSERVER['PASSWORD']), headers = headers)

    if response.status_code == 404:
        return None

    return Workspace(json=response.json())

def get_coverage_store(json={}, workspace="ogp", name=None):
    if 'name' in json and 'workspace' in json:
        name = json['name']
        workspace = json['workspace']['name']
    elif not workspace or not name:
        return None

    if is_string(workspace):
        workspace = Workspace(name=workspace)

    url = "%s/coveragestores/%s" % (workspace.url_with_name(), name)
    auth = (GEOSERVER['USER'], GEOSERVER['PASSWORD'])
    headers = {"Accept": "application/json"}

    response = requests.get(url=url, auth=auth, headers=headers)

    if response.status_code == 404:
        return None

    return CoverageStore(json=response.json())

def get_coverage(coverage_store=None, name=None):
    if not name and not coverage_store:
        return None 

    if is_string(coverage_store):
        coverage_store = get_coverage_store(name=coverage_store)

    url = "%s/coverages/%s" % (coverage_store.url_with_name(), name)
    auth = (GEOSERVER['USER'], GEOSERVER['PASSWORD'])
    headers = {"Accept": "application/json"}
    
    response = requests.get(url=url, auth=auth, headers=headers)

    return Coverage(json=response.json(), coverage_store=coverage_store)

#assumes map plus worldfile is already on the server
#relative paths are relative to the geoserver data directory
def add_to_geoserver(name, filepath, workspace="ogp", srs="EPSG:3445", units="ft"):
    if not filepath.startswith("file:"):
        filepath = "file:" + filepath
    
    if not unicode(srs).startswith("EPSG:"):
        srs = "EPSG:%s" % (srs)

    coverage_store = CoverageStore(name=name, workspace=workspace, url=filepath)

    (saved, response) = coverage_store.save()

    if saved:
        coverage = Coverage(name=coverage_store.name, coverage_store=coverage_store, srs=srs, units = units)
        (saved, response) = coverage.save()

        return (saved, response, coverage)

    else:
        return (saved, response, None)

class GeoServerObject(object):
    name = None
    _server_name = None
    _modified = False
    _new = False

    get_functions = {
        'workspace': get_workspace,
        'coverageStore': get_coverage_store,
    }

    def __init__(self, *args, **kwargs):
        if 'json' in kwargs:
            json = kwargs['json']

            main_key = json.keys()[0] #the top level of the dictionary has a lone key with the same name as the object type
            attribute_json = json[main_key]

            attributes = dir(self)

            if 'name' in attribute_json:
                self._server_name = attribute_json['name']

            for k in attribute_json:
                if k in attributes and not k in self.get_functions:
                    self.__setattr__(k, attribute_json[k])
                elif k in attributes and k in self.get_functions:
                    geo_server_object = self.get_functions[k](json=attribute_json[k])
                    self.__setattr__(k, geo_server_object)
        else:
            self._new = True

    def __setattr__(self, name, value):
        if not name.startswith("_") and not self._new and name in self.__dict__:
            self._modified = True

        super(GeoServerObject, self).__setattr__(name, value)

    def base_url(self):
        return GEOSERVER['REST_URL']

    def url_with_name(self):
        return "%s/%s" % (self.base_url(), self.name if self._new else self._server_name)

    def save(self, *args, **kwargs):
        if 'headers' in kwargs and 'data' in kwargs:
            headers = kwargs['headers']
            data = kwargs['data']
            auth = (GEOSERVER['USER'], GEOSERVER['PASSWORD'])

            
            response = None
            status_okay = None

            if self._new:
                url = self.base_url()

                response = requests.post(url=url, auth=auth, headers=headers, data=unicode(data))
                if response.status_code == 201:
                    status_okay = True
            else:
                url = self.url_with_name()
                response = requests.put(url=url, auth=auth, headers=headers, data=unicode(data))

                if response.status_code == 200:
                    status_okay = True

            if status_okay:
                self._new = False
                self._modified = False
                self._server_name = self.name
                return (True, response)
            else:
                return (False, response)
        else:
            return (False, None)

    def delete(self, *args, **kwargs):
        if not self._new:
            url = self.url_with_name()
            response = requests.delete(url=url, auth=(GEOSERVER['USER'], GEOSERVER['PASSWORD']))
    
            if response.status_code == 200:
                self._new = True
                self._modified = False
                return (True, response)
            else:
                return (False, response)
        else:
            return (False, None)

class Workspace(GeoServerObject):
    def __init__(self, *args, **kwargs):
        #if json is given, ignore all other keywords. 'name' is the only attribute exposed by the REST api, and it can't be modified
        #for other types, this check would not be included and super__init__ would be called directly. Other keywords would overwrite what is in the json
        if 'json' in kwargs:
            super(Workspace, self).__init__(*args, **kwargs)
            return

        self._new = True
        
        if 'name' in kwargs:
            self.name = kwargs['name']

    def base_url(self):
        return "%s/workspaces" % (GEOSERVER['REST_URL'])

    def save(self, *args, **kwargs):
        if not self._new:
            return (False, None) #only new Workspaces can be saved

        headers = {'Content-Type': 'application/json'}
        data = {
            'workspace': {
                'name': self.name
            }
        }

        return super(Workspace, self).save(headers=headers, data=data)

class CoverageStore(GeoServerObject):
    url = None
    type = "WorldImage"
    enabled = True
    workspace = None

    def __init__(self, *args, **kwargs):
        super(CoverageStore, self).__init__(*args, **kwargs)

        attributes = ['name', 'url', 'type', 'enabled', 'workspace']

        for k in kwargs:
            if k == 'workspace' and is_string(kwargs[k]):
                self.workspace = get_workspace({'name':kwargs[k]})
            elif k in attributes:
                self.__setattr__(k, kwargs[k])

    def save(self, *args, **kwargs):
        if self._new or self._modified:
            attributes_to_save = ['name', 'type', 'url', 'enabled']
    
            xml = "<coverageStore>"
            for a in attributes_to_save:
                xml += "<%s>%s</%s>" % (a, self.__getattribute__(a), a)
            xml += "</coverageStore>"

            headers = {'Content-Type': "text/xml"}

            return super(CoverageStore, self).save(headers=headers, data=xml)
    
        else:
            return (False, None)

    def base_url(self):
        if type(self.workspace) == Workspace:
            return "%s/workspaces/%s/coveragestores" % (GEOSERVER['REST_URL'], self.workspace.name)

class Coverage(GeoServerObject):
    name = None
    srs = None
    coverage_store = None
    height = None
    width = None
    units = None

    def __init__(self, *args, **kwargs):
        super(Coverage,self).__init__(*args, **kwargs)

        parameters = ['name', 'srs', 'coverage_store', 'units']

        for k in kwargs:
            if k == 'coverage_store' and is_string(kwargs[k]) and 'workspace' in kwargs:
                workspace = kwargs['workspace']
                self.coverage_store = get_coverage_store(workspace = workspace if is_string(workspace) else workspace.name, name = kwargs['coverage_store']) 
            elif k in parameters:
                self.__setattr__(k, kwargs[k])

        if self.coverage_store:
            world_file = open(self.world_file_path())
            image_file_path = self.image_file_path()
            (self.width, self.height) = Image.open(image_file_path).size
            

    def world_file_path(self):
        if self.coverage_store:
            path = self.image_file_path()
            ext = path.split(".")[-1]

            path = path.replace(ext, "%s%sw" % (ext[0], ext[2]))

            return path

    def image_file_path(self):
        if self.coverage_store:
            path = self.coverage_store.url.replace("file:","")

            if path.startswith("/"):
                return path
            else:
                return "%s%s" % (GEOSERVER['DATA_PATH'], self.coverage_store.url.replace("file:",""))


    def base_url(self):
        if type(self.coverage_store) == CoverageStore:
            return "%s/coverages" % (self.coverage_store.url_with_name())

    def save(self):
        if self._new or self._modified:
            data = self.xml()

            headers = {'Content-Type': "text/xml"}

            return super(Coverage, self).save(headers=headers, data=data)
        else:
            return (False, None)

    def delete(self):
        if not self._new:
            url = "%s/layers/%s" % (GEOSERVER['REST_URL'], self.name)
            response = requests.delete(url=url, auth=(GEOSERVER['USER'], GEOSERVER['PASSWORD']))
    
            if response.status_code == 200:
                return super(Coverage,self).delete()
            else:
                return (False, response)
        else:
            return (False, None)


    def xml(self):
        if type(self.coverage_store) == CoverageStore:
            world_file = open(self.world_file_path())
            lines = world_file.readlines()
            world_file.close()

            x_pixel_width = float(lines[0])
            y_pixel_width = float(lines[3])
            min_x = float(lines[4])
            max_y = float(lines[5])
            width, height = Image.open(self.image_file_path()).size

            max_x = min_x + width*x_pixel_width
            min_y = max_y + height*y_pixel_width

            (min_lat, min_lng) = srs_to_latlng(min_x, min_y, srs=self.srs, units=self.units)
            (max_lat, max_lng) = srs_to_latlng(max_x, max_y, srs=self.srs, units=self.units)

            data = {
                'min_x': min_x,
                'max_x': max_x,
                'min_y': min_y,
                'max_y': max_y,

                'x_width': x_pixel_width,
                'y_width': y_pixel_width,

                'min_lat': min_lat,
                'max_lat': max_lat,
                'min_lng': min_lng,
                'max_lng': max_lng,

                'height': height,
                'width': width,

                'coverage_store_name': self.coverage_store.name,
                'name': self.name,
                'srs': self.srs,
            }

            return render_to_string("coverage.xml", data)
