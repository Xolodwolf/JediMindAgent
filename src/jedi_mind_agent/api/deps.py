from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jedi_mind_agent.db.session import get_session
from jedi_mind_agent.product import service
from jedi_mind_agent.product.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(session: SessionDep) -> User:
    """The only place that decides who the current user is.

    The app is single-user for now. To support multiple users, replace this dependency with authentication;
    routes and the domain service already work with an explicit user id.
    """
    return await service.get_or_create_user(session, service.DEFAULT_USERNAME)


CurrentUser = Annotated[User, Depends(get_current_user)]
