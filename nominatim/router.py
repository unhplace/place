class NominatimRouter(object):
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'nominatim':
            return 'nominatim'
        else:
            return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label == 'nominatim' and obj2._meta.app_label == 'nominatim':
            return True
        elif obj1._meta.app_label != 'nominatim' and obj2._meta.app_label != 'nominatim':
            return True
        else:
            return False

    def allow_migrate(self, db, model):
        if db == 'nominatim':
            return False
        else:
            return True

    def allow_syncdb(self, db, model):
        if db == 'nominatim':
            return False
        else:
            return True
