from pymongo import ASCENDING, DESCENDING
from django.db.backends.creation import TEST_DATABASE_PREFIX
from django.core.exceptions import ImproperlyConfigured
from djangotoolbox.db.base import NonrelDatabaseCreation
from .utils import first

class DatabaseCreation(NonrelDatabaseCreation):
    data_types = dict(NonrelDatabaseCreation.data_types, **{
        'EmailField':                   'unicode',
        'URLField':                     'unicode',
        'CharField':                    'unicode',
        'CommaSeparatedIntegerField':   'unicode',
        'IPAddressField':               'unicode',
        'SlugField':                    'unicode',
        'FileField':                    'unicode',
        'FilePathField':                'unicode',
        'TextField':                    'unicode',
        'XMLField':                     'unicode',
        'IntegerField':                 'int',
        'SmallIntegerField':            'int',
        'PositiveIntegerField':         'int',
        'PositiveSmallIntegerField':    'int',
        'BigIntegerField':              'int',
        'GenericAutoField':             'objectid',
        'StringForeignKey':             'objectid',
        'AutoField':                    'objectid',
        'RelatedAutoField':             'objectid',
        'OneToOneField':                'int',
        'DecimalField':                 'float',
    })

    def sql_indexes_for_model(self, model, termstyle):
        """ Creates indexes for all fields in ``model``. """
        meta = model._meta

        if not meta.managed or meta.proxy:
            return []

        print "Installing index for %s.%s model" % (meta.app_label, meta.object_name)

        descending_indexes = set(getattr(model._meta, 'descending_indexes', ()))
        collection = self.connection.get_collection(meta.db_table)

        # Ordinary indexes
        for field in meta.local_fields:
            if field.name in descending_indexes or field.column in descending_indexes:
                direction = DESCENDING
            else:
                if not field.db_index:
                    continue
                direction = ASCENDING
            collection.ensure_index([(field.column, direction)], unique=field.unique)

        field_names = set(field.name for field in meta.local_fields)
        def create_compound_indexes(indexes, **kwargs):
            if not indexes:
                return
            indexes = [(index if isinstance(index, tuple) else (index, ASCENDING))
                       for index in indexes]
            invalid = first(lambda (name, direction): name not in field_names,
                            indexes)
            if invalid is not None:
                from django.db.models.fields import FieldDoesNotExist
                raise FieldDoesNotExist("%r has no field named %r" %
                                        (meta.object_name, invalid))
            collection.ensure_index(indexes, **kwargs)

        # Django unique_together indexes
        for indexes in getattr(meta, 'unique_together', []):
            create_compound_indexes(indexes, unique=True)

        # MongoDB compound indexes
        index_together = getattr(meta, 'index_together', [])
        if index_together:
            if isinstance(index_together[0], dict):
                # assume index_together = [{'fields' : [...], ...}]
                for args in index_together:
                    kwargs = args.copy()
                    create_compound_indexes(kwargs.pop('fields'), **kwargs)
            else:
                # assume index_together = ['foo', 'bar', ('spam', -1), etc]
                create_compound_indexes(index_together)

        return []

    def sql_create_model(self, model, *unused):
        """ Creates the collection for model. Mostly used for capped collections. """
        kwargs = {}
        for option in ('capped', 'collection_max', 'collection_size'):
            x = getattr(model._meta, option, None)
            if x:
                kwargs[option] = x
        self.connection.get_collection(model._meta.db_table, **kwargs)
        return [], {}

    def set_autocommit(self):
        """ There's no such thing in MongoDB """

    def create_test_db(self, verbosity=1, autoclobber=False):
        # No need to create databases in MongoDB :)
        # but we can make sure that if the database existed is emptied

        test_database_name = self._get_test_db_name()

        self.connection.settings_dict['NAME'] = test_database_name
        # This is important. Here we change the settings so that all other code
        # thinks that the chosen database is now the test database. This means
        # that nothing needs to change in the test code for working with
        # connections, databases and collections. It will appear the same as
        # when working with non-test code.

        # In this phase it will only drop the database if it already existed
        # which could potentially happen if the test database was created but
        # was never dropped at the end of the tests
        self._drop_database(test_database_name)

        return test_database_name

    def destroy_test_db(self, old_database_name, verbosity=1):
        if verbosity >= 1:
            print "Destroying test database '%s'..." % self.connection.alias
        test_database_name = self.connection.settings_dict['NAME']
        self._drop_database(test_database_name)
        self.connection.settings_dict['NAME'] = old_database_name

    def _drop_database(self, database_name):
        self.connection.drop_database(database_name)
