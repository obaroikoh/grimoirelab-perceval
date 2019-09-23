# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2019 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Valerio Cosentino <valcos@bitergia.com>
#

import bs4
import logging
import re

from grimoirelab_toolkit.datetime import datetime_utcnow

from ...backend import (Backend,
                        BackendCommand,
                        BackendCommandArgumentParser,
                        uuid)
from ...client import HttpClient
from ...errors import BackendError

# Default sleep time and retries to deal with connection/server problems
DEFAULT_SLEEP_TIME = 1
MAX_RETRIES = 5

CATEGORY_HITS = "google_hits"
GOOGLE_SEARCH_URL = 'https://www.google.com/search'


logger = logging.getLogger(__name__)


class GoogleHits(Backend):
    """GoogleHits backend for Perceval.

    This class retrieves the number of hits for a given list of
    keywords via the Google API. To initialize this class a list
    of keywords is needed.

    :param keywords: a list of keywords
    :param tag: label used to mark the data
    :param archive: archive to store/retrieve items
    :param max_retries: number of max retries to a data source
        before raising a RetryError exception
    :param sleep_time: time (in seconds) to sleep in case
        of connection problems
    """
    version = '0.3.0'

    CATEGORIES = [CATEGORY_HITS]
    EXTRA_SEARCH_FIELDS = {
        'keywords': ['keywords']
    }

    def __init__(self, keywords, tag=None, archive=None,
                 max_retries=MAX_RETRIES, sleep_time=DEFAULT_SLEEP_TIME):

        if len(keywords) == 1 and keywords[0].strip() == "":
            cause = "No keywords provided"
            raise BackendError(cause=cause)

        self.keywords = keywords
        super().__init__(GOOGLE_SEARCH_URL, tag=tag, archive=archive)

        self.max_retries = max_retries
        self.sleep_time = sleep_time

        self.client = None

    def fetch(self, category=CATEGORY_HITS):
        """Fetch data from Google API.

        The method retrieves a list of hits for some
        given keywords using the Google API.

        :param category: the category of items to fetch

        :returns: a generator of data
        """
        kwargs = {}
        items = super().fetch(category, **kwargs)

        return items

    def fetch_items(self, category, **kwargs):
        """Fetch Google hit items

        :param category: the category of items to fetch
        :param kwargs: backend arguments

        :returns: a generator of items
        """
        logger.info("Fetching data for '%s'", self.keywords)

        hits_raw = self.client.hits(self.keywords)
        hits = self.__parse_hits(hits_raw)

        yield hits

        logger.info("Fetch process completed")

    @classmethod
    def has_archiving(cls):
        """Returns whether it supports archiving items on the fetch process.

        :returns: this backend supports items archive
        """
        return True

    @classmethod
    def has_resuming(cls):
        """Returns whether it supports to resume the fetch process.

        :returns: this backend supports items resuming
        """
        return True

    @staticmethod
    def metadata_id(item):
        """Extracts the identifier from a GoogleHit item."""

        return item['id']

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a GoogleHit item.

        The timestamp is based on the current time when the hit was extracted.
        This field is not part of the data provided by Google API. It is added
        by this backend.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        return item['fetched_on']

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a GoogleHits item.

        This backend only generates one type of item which is
        'google_hits'.
        """
        return CATEGORY_HITS

    def _init_client(self, from_archive=False):
        """Init client"""

        return GoogleHitsClient(self.sleep_time, self.max_retries,
                                archive=self.archive, from_archive=from_archive)

    def __parse_hits(self, hit_raw):
        """Parse the hits returned by the Google Search API"""

        # Create the soup and get the desired div
        bs_result = bs4.BeautifulSoup(hit_raw, 'html.parser')
        hit_string = bs_result.find("div", id="resultStats").text

        # Remove commas or dots
        hit_string = hit_string.replace(',', u'')
        hit_string = hit_string.replace('.', u'')

        fetched_on = datetime_utcnow().timestamp()
        id_args = self.keywords[:]
        id_args.append(str(fetched_on))

        hits_json = {
            'fetched_on': fetched_on,
            'id': uuid(*id_args),
            'keywords': self.keywords,
            'type': 'googleSearchHits'
        }

        if not hit_string:
            logger.warning("No hits for %s", self.keywords)
            hits_json['hits'] = 0

            return hits_json

        str_hits = re.search(r'\d+', hit_string).group(0)
        hits = int(str_hits)
        hits_json['hits'] = hits

        return hits_json


class GoogleHitsClient(HttpClient):
    """GoogleHits API client.

    Client for fetching hits data from Google API.

    :param sleep_time: time (in seconds) to sleep in case
        of connection problems
    :param max_retries: number of max retries to a data source
        before raising a RetryError exception
    :param archive: an archive to store/read fetched data
    :param from_archive: it tells whether to write/read the archive
    """
    EXTRA_STATUS_FORCELIST = [429]

    def __init__(self, sleep_time=DEFAULT_SLEEP_TIME, max_retries=MAX_RETRIES,
                 archive=None, from_archive=False):
        super().__init__(GOOGLE_SEARCH_URL, extra_status_forcelist=self.EXTRA_STATUS_FORCELIST,
                         sleep_time=sleep_time, max_retries=max_retries,
                         archive=archive, from_archive=from_archive)

    def hits(self, keywords):
        """Fetch information about a list of keywords."""

        if len(keywords) == 1:
            query_str = keywords[0]
        else:
            query_str = ' '.join([k for k in keywords])

        logger.info("Fetching hits for '%s'", query_str)
        params = {'q': query_str}

        # Make the request
        req = self.fetch(GOOGLE_SEARCH_URL, payload=params)

        return req.text


class GoogleHitsCommand(BackendCommand):
    """Class to run GoogleHits backend from the command line."""

    BACKEND = GoogleHits

    @classmethod
    def setup_cmd_parser(cls):
        """Returns the GoogleHits argument parser."""

        parser = BackendCommandArgumentParser(cls.BACKEND,
                                              archive=True)

        group = parser.parser.add_argument_group('GoogleHits arguments')
        # Generic client options
        group.add_argument('--max-retries', dest='max_retries',
                           default=MAX_RETRIES, type=int,
                           help="number of API call retries")
        group.add_argument('--sleep-time', dest='sleep_time',
                           default=DEFAULT_SLEEP_TIME, type=int,
                           help="sleeping time between API call retries")

        # Required arguments
        parser.parser.add_argument('keywords', nargs='+',
                                   help="Keywords to search as Google hits")

        return parser
