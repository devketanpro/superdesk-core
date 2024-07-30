import json
from typing import Any, List, Union

import apps.archive  # NOQA

# XXX: This import is needed in order to avoid ImportError when importing
# package_service, caused by circular dependencies.
# When that issue is resolved, the workaround should be removed.

from superdesk.core import get_current_app, get_app_config
import apps.packages.package_service as package
from superdesk import get_resource_service
from superdesk.services import BaseService
from eve.utils import ParsedRequest
from superdesk.notification import push_notification
from superdesk.utc import get_timezone_offset, utcnow
from apps.archive.common import ITEM_MARK, ITEM_UNMARK
from bson import ObjectId


def init_parsed_request(elastic_query):
    parsed_request = ParsedRequest()
    parsed_request.args = {"source": json.dumps(elastic_query)}
    return parsed_request


def get_highlighted_items(highlights_id):
    """Get items marked for given highlight and passing date range query."""
    highlight = get_resource_service("highlights").find_one(req=None, _id=highlights_id)
    query = {
        "query": {
            "filtered": {
                "filter": {
                    "and": [
                        {
                            "range": {
                                "versioncreated": {
                                    "gte": highlight.get("auto_insert", "now/d"),
                                    "time_zone": get_timezone_offset(get_app_config("DEFAULT_TIMEZONE"), utcnow()),
                                }
                            }
                        },
                        {"term": {"highlights": str(highlights_id)}},
                    ]
                }
            }
        },
        "sort": [
            {"versioncreated": "desc"},
        ],
        "size": 200,
    }
    request = ParsedRequest()
    request.args = {"source": json.dumps(query), "repo": "archive,published"}
    return list(get_resource_service("search").get(req=request, lookup=None))


def init_highlight_package(doc):
    """Add to package items marked for doc highlight."""
    main_group = doc.get("groups")[1]
    items = get_highlighted_items(doc.get("highlight"))
    used_items = []
    for item in items:
        if item["_id"] not in used_items:
            main_group["refs"].append(package.get_item_ref(item))
            used_items.append(item["_id"])


def init_default_content_profile(doc):
    if not doc.get("profile"):
        desk_id = doc.get("task", {}).get("desk")
        desk = get_resource_service("desks").find_one(req=None, _id=desk_id)
        doc["profile"] = desk.get("default_content_profile")


def on_create_package(sender, docs):
    """Call init_highlight_package for each package with highlight reference."""
    for doc in docs:
        if doc.get("highlight"):
            init_highlight_package(doc)
            init_default_content_profile(doc)


def get_highlight_name(highlights_id):
    """
    Given the id of a highlight it will return the name.
    :param hightlight_id:
    :return:
    """
    highlight = get_resource_service("highlights").find_one(req=None, _id=highlights_id)
    if highlight and "name" in highlight:
        return highlight.get("name", None)
    return None


class HighlightsService(BaseService):
    def on_delete(self, doc):
        service = get_resource_service("archive")
        highlights_id = str(doc["_id"])
        query = {"query": {"filtered": {"filter": {"term": {"highlights": highlights_id}}}}}
        req = init_parsed_request(query)
        proposedItems = service.get(req=req, lookup=None)
        app = get_current_app().as_any()
        for item in proposedItems:
            app.on_archive_item_updated(
                {"highlight_id": highlights_id, "highlight_name": get_highlight_name(highlights_id)}, item, ITEM_UNMARK
            )
            highlights = [h for h in item.get("highlights") if h != highlights_id]
            service.update(item["_id"], {"highlights": highlights}, item)


class MarkedForHighlightsService(BaseService):
    def create(self, docs, **kwargs):
        """Toggle highlight status for given highlight and item."""
        service = get_resource_service("archive")
        publishedService = get_resource_service("published")
        ids = []
        app = get_current_app().as_any()
        for doc in docs:
            item = service.find_one(req=None, _id=doc["marked_item"])
            if not item:
                ids.append(None)
                continue
            ids.append(item["_id"])
            highlights = item.get("highlights") or []

            doc_highlights: List[Union[ObjectId, str]] = doc["highlights"] or []
            if doc_highlights and not isinstance(doc_highlights, list):
                doc_highlights = [doc_highlights]
            status = {}
            for highlight in doc_highlights:
                if highlight not in highlights:
                    highlights.append(highlight)
                    status[str(highlight)] = ITEM_MARK
                else:
                    highlights = [h for h in highlights if h != highlight]
                    status[str(highlight)] = ITEM_UNMARK

            updates = {"highlights": highlights, "_etag": item["_etag"]}
            service.update(item["_id"], updates, item)

            publishedItems = publishedService.find({"item_id": item["_id"]})
            for publishedItem in publishedItems:
                if publishedItem["_current_version"] == item["_current_version"]:
                    updates = {
                        "highlights": highlights,
                        "_updated": publishedItem["_updated"],
                        "_etag": publishedItem["_etag"],
                    }
                    publishedService.update(publishedItem["_id"], updates, publishedItem)

            for highlight in doc_highlights:
                app.on_archive_item_updated(
                    {"highlight_id": highlight, "highlight_name": get_highlight_name(highlight)},
                    item,
                    status[str(highlight)],
                )

                push_notification(
                    "item:highlights",
                    marked=int(status[str(highlight)] == ITEM_MARK),
                    item_id=item["_id"],
                    mark_id=str(highlight),
                )

        return ids


package.package_create_signal.connect(on_create_package)
