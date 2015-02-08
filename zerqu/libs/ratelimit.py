# coding: utf-8

import time
import logging
from ..models import cache


logger = logging.getLogger('zerqu')


def ratelimit(prefix, count=600, duration=300):
    logger.info('Ratelimit on %s' % prefix)
    count_key = '%s$c' % prefix
    reset_key = '%s$r' % prefix
    remaining, resetting = cache.get_many(count_key, reset_key)

    if not remaining and not resetting:
        remaining = count - 1
        expires_at = duration + int(time.time())
        cache.set_many({
            count_key: remaining,
            reset_key: expires_at,
        }, duration)
        expires = duration
    else:
        expires = int(resetting) - int(time.time())
        if remaining <= 0 and expires:
            return remaining, expires
        remaining = int(remaining) - 1
        cache.set(count_key, remaining, expires)
    return remaining, expires