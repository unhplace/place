from django.contrib.gis.db import models
from django.template.loader import render_to_string

import datetime
import re
import requests

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

def rollback(t_id):
    response = requests.post("%s/fcr:tx/fcr:rollback" % (t_id))

    return response

class FCObject(object):
    _new = None
    _rdf = None
    _url = None
    _use_objects = None
    _changed_properties = []
    _item = None
    properties = {}
    types = {}
    namespaces = {}

    @classmethod
    def string_to_object(self, string):
        if re.match('".*"\^\^<.*>', string):
            string = re.sub('^"|"$', "", string)
            string = re.sub('"\^\^', "^^", string)
            (v, t) = string.split("^^")

            t = re.sub("^<.*#|>$", "", t)

            if t == "boolean":
                return True if t.lower() == "true" else False
            elif t == "dateTime":
                return datetime.datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%fZ")
            elif t == "string":
                return v
            else:
                return v

        elif re.match("^<.*>$", string):
            url = re.sub("^<|>$", "", string)
            return FCObject(url=url, use_objects = True)
        elif re.match(".*:.*", string):
            return string
        else:
            return None

    def save(self):
        values = {}
        namespaces = {}

        for k in self._changed_properties:
            values[k] = self[k]
            ns = k.split(":")[0]

            if not ns in namespaces:
                namespaces[ns] = self.namespaces[ns]
        
        t_id = requests.post("%s/fcr:tx" % (settings.FCREPO_BASE_URL)).headers["location"]
        save_url = self._url.replace(settings.FCREPO_BASE_URL, t_id)

        template_data = {
            "namespaces": namespaces,
            "values": values
        }

        if self._new:
            error = import_template_to_fcrepo(save_url, "rdf/object.rdf")
    
            if error:
                return error

        error = import_template_to_fcrepo(save_url, "rdf/update.rdf", template_data)

        if error:
            return error

        commit_response = requests.post("%s/fcr:tx/fcr:commit" % (t_id))
        if commit_response.status_code != UPDATE_SUCCESS:
            return commit_response

        self._new = False
        self.__load_rdf__()

        return None

    @property
    def rdf_update_text(self):
        values = {}
        namespaces = {}

        for k in self._changed_properties:
            values[k] = self[k]
            ns = k.split(":")[0]

            if not ns in namespaces:
                namespaces[ns] = self.namespaces[ns]

        template_data = {
            "namespaces": namespaces,
            "values": values
        }

        text = render_to_string("rdf/update.rdf", template_data) 

        return text

    def __init__(self, *args, **kwargs):
        if "url" in kwargs:
            self._new = False

            url = kwargs["url"]
            use_objects = True
            load_rdf = kwargs.get("load_rdf") == True

            if url.startswith("/"):
                url = "%s%s" % (settings.FCREPO_BASE_URL, url)
            
            self._url = url
            self._use_objects = use_objects

            if load_rdf:
                self.__load_rdf__()
        else:
            self._new = True

    def __contains__(self, key):
        if not ":" in key:
            return False

        (ns, k) = key.split(":", 1)

        if not ns in self.properties:
            return False
        if not k in self.properties[ns]:
            return False

        return True

    def __getitem__(self, key):
        if not ":" in key:
            if not key in self.properties:
                raise KeyError("Invalid Namespace: %s" % (key))
            else:
                return self.properties[key]

        (ns, k) =  key.split(":", 1)

        if not ns in self.properties:
            raise KeyError("Invalid Namespace: %s" % (ns))

        if not k in self.properties[ns]:
            raise KeyError("Invalid Property: %s" % (k))

        return self.properties[ns][k]

    def __setitem__(self, key, value):
        if not ":" in key:
            raise KeyError("Invalid Format: %s" % (key))

        (ns, k) = key.split(":", 1)

        if not ns in self.properties:
            self.properties[ns] = {}

        original_value = self.properties[ns][k]._original_value if k in self.properties[ns] else []

        if type(value) != list:
            value = [value]

        self.properties[ns][k] = SemanticValue(*value, object=self, namespace=ns, property=k, original_value = original_value)

    def __getattribute__(self, name):
        if name in ["properties", "types", "namespaces"] and not self._new and not self._rdf:
            self.__load_rdf__()
        return object.__getattribute__(self, name)

    @property
    def rdf(self):
        if not self._new and not self._rdf:
            self.__load_rdf__()
        return self._rdf

    def __load_rdf__(self):
        self._changed_properties = []
        self._rdf = requests.get(self._url).text

        lines = [x.strip() for x in self._rdf.split("\n")]

        properties = {}
        types = {}
        namespaces = {}

        for line in lines:
            line = re.sub("^<.*?>| ;$| .$", "", line).strip()

            if line == (""):
                continue

            if line.startswith("@prefix"):
                l = re.sub("^@prefix| .$|<|>", "", line)

                (ns, v) = (x.strip() for x in l.split(": "))
                namespaces[ns] = v
                continue

            if line.startswith("a "):
                ts = re.sub("a ", "", line).split(" , ")
                
                for t in ts:
                    (ns, v) = t.split(":")

                    if not ns in types:
                        types[ns] = []

                    types[ns].append(v)
            elif line.startswith("rdf:type"):
                line = re.sub("^rdf:type *", "", line)
                (ns, v) = line.split(":")
                if not ns in types:
                    types[ns] = []
                types[ns].append(v)
            else:
                (p,value) = line.split(" ",1)
                (namespace, key) = p.split(":")

                value = value.strip()

                if not namespace in properties:
                    properties[namespace] = {}
                
                if key in properties[namespace]:
                    if self._use_objects:
                        properties[namespace][key].append(self.string_to_object(value), initial=True)
                    else:
                        properties[namespace][key].append(value, initial=True)
                else:
                    kwargs = {
                        "initial": True,
                        "object": self,
                        "namespace": namespace,
                        "property": key
                    }

                    if self._use_objects:
                        properties[namespace][key] = SemanticValue(self.string_to_object(value), **kwargs)
                    else:
                        properties[namespace][key] = SemanticValue(value, **kwargs)

        self.lines = lines

        self.types = types
        self.namespaces = namespaces
        self.properties = properties

    def __unicode__(self):
        return u"<%s>" % (self._url)

    def __str__(self):
        return u"<%s>" % (self._url)

    def __repr__(self):
        return u"<%s: %s>" % (self.__class__.__name__, self._url)

class SemanticValue(object):
    _namespace = None
    _original_value = []
    _property = None
    _value = []
    _object = None

    def __init__(self, *args, **kwargs):

        self._object = kwargs.get("object")
        self._namespace = kwargs["namespace"]
        self._property = kwargs["property"]

        original_value = kwargs.get("original_value", [])

        initial = kwargs.get("initial") == True

        self._value = [x for x in args]

        if initial:
            self._original_value = [x for x in args]
        if not initial:
            self._original_value = original_value
            self.set_changed_property()

    def __getitem__(self, index):
        return self._value[index]

    def set_changed_property(self):
        key = "%s:%s" % (self._namespace, self._property)

        if not key in self._object._changed_properties:
            self._object._changed_properties.append(key)

    def append(self, *args, **kwargs):
        if len(args) == 0:
            raise ValueError("Must supply at least 1 value.")

        for value in args:
            self._value.append(value)

        initial = kwargs.get("initial") == True
        
        if not initial:
            self.set_changed_property()
        else:
            self._original_value = [x for x in self._value]

    def remove(self, value):
        try:
            self._value.remove(value)
            self.set_changed_property()
        except:
            raise ValueError("Semantic value does not contain %s" % (value))

    def replace(self, *args):
        self._value = [x for x in args]
        self.set_changed_property()

    @property
    def rdf_value(self):
        if self._value and len(self._value) > 0:
            value = self._value[0]

            if type(value) == datetime.datetime:
                value_format = '"%s.0Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>'
                return " , ".join([value_format % (x.isoformat()) for x in self._value])
            elif type(value) == bool:
                value_format = '"%s"^^<http://www.w3.org/2001/XMLSchema#boolean>'
                return " , ".join([value_format % ("true" if x == True else "false") for x in self._value])
            else:
                value_format = '%s' if re.match("^<.*?>$", unicode(self._value[0])) else '"%s"'

            return " , ".join([value_format % (unicode(x)) for x in self._value])
        else:
            return None

    @property
    def rdf_original_value(self):
        if self._original_value and len(self._original_value) > 0:
            value = self._original_value[0]

            if type(value) == datetime.datetime:
                value_format = '"%s.0Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>'
                return " , ".join([value_format % (x.isoformat()) for x in self._original_value])
            elif type(value) == bool:
                value_format = '"%s"^^<http://www.w3.org/2001/XMLSchema#boolean>'
                return " , ".join([value_format % ("true" if x == True else "false") for x in self._value])
            else:
                value_format = '%s' if re.match("^<.*?>$", unicode(self._original_value[0])) else '"%s"'

            return " , ".join([value_format % (unicode(x)) for x in self._original_value])
        else:
            return None

    def __unicode__(self):
        return unicode(self._value)

    def __str__(self):
        return str(self._value)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, repr(self._value))
