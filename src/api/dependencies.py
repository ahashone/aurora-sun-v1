"""
FastAPI Dependencies for Authentication, Authorization, and Rate Limiting.
"""

import logging
from typing import Any, Generic, Optional, TypeVar

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from src.api.auth import AuthService, AuthToken
from src.lib.security import (
    InputSanitizer,
    RateLimiter,
    RateLimitTier,
    sanitize_for_llm,
    sanitize_for_storage,
)

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# Initialize AuthService (raises RuntimeError if secrets are missing, but validate_secrets()
# is called at app startup so this should be fine)
auth_service = AuthService()


async def get_current_user_token(
    token: str = Depends(oauth2_scheme),
) -> AuthToken:
    """
    Dependency to get the current user's authenticated token.

    Raises HTTPException if token is missing or invalid.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_token = auth_service.decode_token(token)
    if not auth_token or auth_token.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_token


async def get_current_user_id(
    token: AuthToken = Depends(get_current_user_token),
) -> int:
    """
    Dependency to get the current user's authenticated ID.

    Raises HTTPException if token is missing or invalid.
    """
    return token.user_id


async def require_admin(
    user_id: int = Depends(get_current_user_id),
) -> int:
    """
    Dependency that requires admin role (CRIT-2).

    Checks user_id against AURORA_ADMIN_USER_IDS environment variable.
    Format: comma-separated list of user IDs.

    Raises HTTPException 403 if user is not an admin.
    """
    import os

    admin_ids_str = os.getenv("AURORA_ADMIN_USER_IDS", "")
    admin_ids = {
        int(x.strip())
        for x in admin_ids_str.split(",")
        if x.strip().isdigit()
    }
    if not admin_ids or user_id not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user_id


class APIRateLimiter:
    """
    FastAPI Dependency for API Rate Limiting.

    Applies the Redis-backed RateLimiter from src.lib.security.
    """
    async def __call__(self, user_id: int = Depends(get_current_user_id)) -> None:
        """
        Check rate limit for API actions.
        """
        if not await RateLimiter.check_rate_limit(user_id, RateLimitTier.API):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )


# Generic type for Pydantic models
ModelType = TypeVar("ModelType", bound=BaseModel)
T = TypeVar("T", bound=BaseModel)

class InputSanitizerDependency(Generic[ModelType]):
    """
    FastAPI Dependency to sanitize incoming Pydantic models.

    Applies InputSanitizer.sanitize_all to all string fields
    in the request body model.

    Usage:
        @router.post("/items")
        async def create_item(
            item: ItemCreate = Depends(InputSanitizerDependency(ItemCreate))
        ):
            ...
    """

    def __init__(
        self,
        model: type[ModelType],
        llm_fields: Optional[list[str]] = None,
        storage_fields: Optional[list[str]] = None,
    ) -> None:
        self.model = model
        self.llm_fields = llm_fields if llm_fields is not None else []
        self.storage_fields = storage_fields if storage_fields is not None else []

    async def __call__(self, request: Request) -> ModelType:
        """
        Processes the incoming request and sanitizes string fields in the Pydantic model.
        """
        # Get the JSON body from the request
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Create an instance of the Pydantic model with the raw data
        try:
            raw_model_instance = self.model(**body)
        except Exception as e:
            # MED-21: Log validation errors but return generic message to client
            logger.warning("Input validation failed: %s", e)
            raise HTTPException(status_code=422, detail="Validation error")

        # Sanitize the model instance
        sanitized_model_instance = self._sanitize_model(raw_model_instance, "", self.llm_fields, self.storage_fields)
        return sanitized_model_instance

    @classmethod
    def _sanitize_value(cls, value: Any, field_name_path: str, llm_fields: list[str], storage_fields: list[str]) -> Any:
        if isinstance(value, str):
            if field_name_path in llm_fields:
                return sanitize_for_llm(value)
            elif field_name_path in storage_fields:
                return sanitize_for_storage(value)[0] # sanitize_for_storage returns (str, bool)
            else:
                return InputSanitizer.sanitize_all(value)
        elif isinstance(value, BaseModel):
            return cls._sanitize_model(value, field_name_path, llm_fields, storage_fields)
        elif isinstance(value, list):
            return [cls._sanitize_value(item, field_name_path, llm_fields, storage_fields) for item in value]
        elif isinstance(value, dict):
            return {k: cls._sanitize_value(v, f"{field_name_path}.{k}" if field_name_path else k, llm_fields, storage_fields) for k, v in value.items()}
        return value

    @classmethod
    def _sanitize_model(
        cls,
        model_instance: T,
        parent_path: str,
        llm_fields: list[str],
        storage_fields: list[str],
    ) -> T:
        # Create a deep copy to avoid modifying the original model instance during iteration
        # This is important because the model_instance might be passed by reference
        # and its fields might be read during the iteration over model_instance.
        import copy
        processed_model = copy.deepcopy(model_instance)

        for field_name, field_value in processed_model:
            current_path = f"{parent_path}.{field_name}" if parent_path else field_name
            setattr(processed_model, field_name, cls._sanitize_value(field_value, current_path, llm_fields, storage_fields))
        return processed_model
