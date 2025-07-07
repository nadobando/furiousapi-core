from __future__ import annotations

import os

from pydantic import BaseModel


class PaginationSettings(BaseModel):
    default_size: int = int(os.getenv("FURIOUS_PAGINATION_DEFAULT_SIZE", "10"))
    max_size: int = int(os.getenv("FURIOUS_PAGINATION_MAX_SIZE", "50"))


pagination: PaginationSettings = PaginationSettings()
