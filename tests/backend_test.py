# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

from datetime import timedelta
from unittest.mock import patch, ANY

from superdesk.resource_fields import DATE_CREATED, LAST_UPDATED, ETAG
from superdesk.tests import TestCase
from superdesk import get_backend
from superdesk.utc import utcnow


class BackendTestCase(TestCase):
    async def test_update_change_etag(self):
        backend = get_backend()
        updates = {"name": "foo"}
        item = {"name": "bar"}
        ids = backend.create("ingest", [item])
        doc_old = backend.find_one("ingest", None, _id=ids[0])
        backend.update("ingest", ids[0], updates, doc_old)
        doc_new = backend.find_one("ingest", None, _id=ids[0])
        self.assertNotEqual(doc_old[ETAG], doc_new[ETAG])

    async def test_check_default_dates_on_create(self):
        backend = get_backend()
        item = {"name": "foo"}
        ids = backend.create("ingest", [item])
        doc = backend.find_one("ingest", None, _id=ids[0])
        self.assertIn(DATE_CREATED, doc)
        self.assertIn(LAST_UPDATED, doc)

    async def test_check_default_dates_on_update(self):
        backend = get_backend()
        past = (utcnow() + timedelta(seconds=-2)).replace(microsecond=0)
        item = {"name": "foo", DATE_CREATED: past, LAST_UPDATED: past}
        updates = {"name": "bar"}
        ids = backend.create("ingest", [item])
        doc_old = backend.find_one("ingest", None, _id=ids[0])
        backend.update("ingest", ids[0], updates, doc_old)
        doc_new = backend.find_one("ingest", None, _id=ids[0])
        date1 = doc_old[LAST_UPDATED]
        date2 = doc_new[LAST_UPDATED]
        self.assertGreaterEqual(date2, date1)
        date1 = doc_old[DATE_CREATED]
        date2 = doc_new[DATE_CREATED]
        self.assertEqual(date1, date2)

    @patch("superdesk.eve_backend._push_notification")
    async def test_update_resource_push_notification(self, push_notification_mock):
        backend = get_backend()
        backend.create("archive", [{"_id": "some-id"}])
        push_notification_mock.assert_called_once_with(
            "resource:created",
            resource="archive",
            _id="some-id",
        )

        backend.update(
            "archive",
            "some-id",
            {
                "foo": 1,
                "new": {"baz": 1},
                "same": {"x": "y"},
                "different": {
                    "same": 1,
                    "foo": 1,
                    "bar": {
                        "baz": 1,
                    },
                },
            },
            {
                "baz": 0,
                "same": {"x": "y"},
                "different": {
                    "same": 1,
                    "foo": 2,
                    "bar": {
                        "baz": 2,
                    },
                    "missing": 1,
                },
            },
        )

        push_notification_mock.assert_called_with(
            "resource:updated",
            resource="archive",
            _id="some-id",
            fields={
                "foo": 1,
                "new": 1,
                "new.baz": 1,
                "different": 1,
                "different.foo": 1,
                "different.bar": 1,
                "different.missing": 1,
            },
        )

        backend.delete("archive", {"_id": "some-id"})
        push_notification_mock.assert_called_with(
            "resource:deleted",
            resource="archive",
            _id="some-id",
        )

    async def test_update_doc_missing_in_elastic(self):
        backend = get_backend()
        updates = {"name": "foo"}
        item = {"name": "bar"}
        ids = backend.create_in_mongo("ingest", [item])
        items = backend.search("ingest", {"query": {"match_all": {}}})
        self.assertEqual(0, items.count())
        original = backend.find_one("ingest", req=None, _id=ids[0])
        backend.update("ingest", ids[0], updates, original)
        items = backend.search("ingest", {"query": {"match_all": {}}})
        self.assertEqual(1, items.count())
