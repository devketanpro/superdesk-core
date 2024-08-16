# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import logging
from quart_babel import gettext as _

from superdesk.resource_fields import ID_FIELD
from superdesk.flask import g
import superdesk
from superdesk.errors import SuperdeskApiError
from superdesk.services import BaseService
from superdesk.celery_app import celery
from apps.auth.auth import SuperdeskTokenAuth
from .auth import AuthUsersResource, AuthResource  # noqa
from .sessions import SessionsResource, UserSessionClearResource
from .session_purge import RemoveExpiredSessions
from .service import UserSessionClearService, AuthService

logger = logging.getLogger(__name__)


def init_app(app) -> None:
    app.auth = SuperdeskTokenAuth()  # Overwrite the app default auth

    endpoint_name = "auth_users"
    service = BaseService(endpoint_name, backend=superdesk.get_backend())
    AuthUsersResource(endpoint_name, app=app, service=service)

    endpoint_name = "sessions"
    service = BaseService(endpoint_name, backend=superdesk.get_backend())
    SessionsResource(endpoint_name, app=app, service=service)

    endpoint_name = "clear_sessions"
    service = UserSessionClearService(endpoint_name, backend=superdesk.get_backend())
    UserSessionClearResource(endpoint_name, app=app, service=service)

    endpoint_name = "auth"
    service = AuthService(endpoint_name, backend=superdesk.get_backend())
    AuthResource(endpoint_name, app=app, service=service)


@celery.task
def session_purge():
    try:
        RemoveExpiredSessions().run()
    except Exception as ex:
        logger.error(ex)


def get_user(required=False):
    """Get user authenticated for current request.

    :param boolean required: if True and there is no user it will raise an error
    """
    user = g.get("user", {})
    if ID_FIELD not in user and required:
        raise SuperdeskApiError.notFoundError(_("Invalid user."))
    return user


def get_user_id(required=False):
    """Get authenticated user id.

    :param boolean required: if True and there is no user it will raise an error
    """
    user = get_user(required)
    return user.get(ID_FIELD)


def get_auth():
    """Get authenticated session data."""
    auth = g.get("auth", {})
    return auth


def is_current_user_admin(required=False):
    """Test if current user is administrator.

    :param required: raise an error if required and there is no user context
    """
    user = get_user(required) or {}
    return user.get("user_type", "") == "administrator"


superdesk.command("session:gc", RemoveExpiredSessions())
