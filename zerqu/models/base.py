# coding: utf-8

from flask import current_app
from sqlalchemy import event
from sqlalchemy.orm import Query, class_mapper
from sqlalchemy.orm.exc import UnmappedClassError
from werkzeug.local import LocalProxy
from flask_sqlalchemy import SQLAlchemy

__all__ = ['db', 'cache', 'use_cache', 'CACHE_TIMES', 'Base']

ONE_DAY = 86400
CACHE_TIMES = {
    'get': ONE_DAY,
    'count': ONE_DAY,
    'ff': 300,
    'fc': 300,
}
CACHE_MODEL_PREFIX = 'db'

db = SQLAlchemy(session_options={'expire_on_commit': False})


def use_cache(prefix='zerqu'):
    return current_app.extensions[prefix + '_cache']


# default cache
cache = LocalProxy(use_cache)


class CacheQuery(Query):
    def get(self, ident):
        mapper = self._only_full_mapper_zero('get')

        if isinstance(ident, (list, tuple)):
            suffix = '-'.join(map(str, ident))
        else:
            suffix = str(ident)

        key = mapper.class_.generate_cache_prefix('get') + suffix
        rv = cache.get(key)
        if rv:
            return rv
        rv = super(CacheQuery, self).get(ident)
        if rv is None:
            return None
        cache.set(key, rv, CACHE_TIMES['get'])
        return rv

    def get_dict(self, idents):
        if not idents:
            return {}

        mapper = self._only_full_mapper_zero('get')
        if len(mapper.primary_key) != 1:
            raise NotImplemented

        prefix = mapper.class_.generate_cache_prefix('get')
        keys = {prefix + str(i) for i in idents}
        rv = cache.get_dict(*keys)

        missed = {i for i in idents if rv[prefix + str(i)] is None}

        rv = {k.lstrip(prefix): rv[k] for k in rv}

        if not missed:
            return rv

        pk = mapper.primary_key[0]
        missing = self.filter(pk.in_(missed)).all()
        to_cache = {}
        for item in missing:
            ident = str(getattr(item, pk.name))
            to_cache[prefix + ident] = item
            rv[ident] = item

        cache.set_many(to_cache, CACHE_TIMES['get'])
        return rv

    def get_many(self, idents, clean=True):
        d = self.get_dict(idents)
        if clean:
            return list(_itervalues(d, idents))
        return [d[str(k)] for k in idents]

    def filter_first(self, **kwargs):
        mapper = self._only_mapper_zero()
        prefix = mapper.class_.generate_cache_prefix('ff')
        key = prefix + '-'.join(['%s$%s' % (k, kwargs[k]) for k in kwargs])
        rv = cache.get(key)
        if rv:
            return rv
        rv = self.filter_by(**kwargs).first()
        if rv is None:
            return None
        # it is hard to invalidate this cache, expires in 2 minutes
        cache.set(key, rv, CACHE_TIMES['ff'])
        return rv

    def filter_count(self, **kwargs):
        mapper = self._only_mapper_zero()
        if not kwargs:
            key = mapper.class_.generate_cache_prefix('count')
            rv = cache.get(key)
            if rv is not None:
                return rv
            rv = self.count()
            cache.set(key, rv, CACHE_TIMES['count'])
            return rv
        prefix = mapper.class_.generate_cache_prefix('fc')
        key = prefix + '-'.join(['%s$%s' % (k, kwargs[k]) for k in kwargs])
        rv = cache.get(key)
        if rv:
            return rv
        rv = self.filter_by(**kwargs).count()
        cache.set(key, rv, CACHE_TIMES['fc'])
        return rv


class CacheProperty(object):
    def __init__(self, sa):
        self.sa = sa

    def __get__(self, obj, type):
        try:
            mapper = class_mapper(type)
            if mapper:
                return CacheQuery(mapper, session=self.sa.session())
        except UnmappedClassError:
            return None


class Base(db.Model):
    __abstract__ = True

    def __getitem__(self, key):
        return getattr(self, key)

    @classmethod
    def generate_cache_prefix(cls, name):
        prefix = '%s:%s:%s' % (CACHE_MODEL_PREFIX, name, cls.__tablename__)
        if hasattr(cls, '__cache_version__'):
            return '%s|%s:' % (prefix, cls.__cache_version__)
        return '%s:' % prefix

    @classmethod
    def __declare_last__(cls):
        @event.listens_for(cls, 'after_insert')
        def receive_after_insert(mapper, conn, target):
            cache.inc(target.generate_cache_prefix('count'))

        @event.listens_for(cls, 'after_update')
        def receive_after_update(mapper, conn, target):
            key = _unique_key(target, mapper.primary_key)
            cache.set(key, target, CACHE_TIMES['get'])

        @event.listens_for(cls, 'after_delete')
        def receive_after_delete(mapper, conn, target):
            key = _unique_key(target, mapper.primary_key)
            cache.delete_many(key, target.generate_cache_prefix('count'))

Base.cache = CacheProperty(db)


def _unique_suffix(target, primary_key):
    return '-'.join(map(lambda k: str(getattr(target, k.name)), primary_key))


def _unique_key(target, primary_key):
    key = _unique_suffix(target, primary_key)
    return target.generate_cache_prefix('get') + key


def _itervalues(data, idents):
    for k in idents:
        item = data[str(k)]
        if item is not None:
            yield item
