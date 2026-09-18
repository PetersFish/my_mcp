from app.domain.user import User as DomainUser
from app.api.user import User as ApiUser


def both() -> str:
    return DomainUser().name() + ApiUser().name()
