"""Minimal Socrata SODA client: paged row iteration over a dataset."""

from collections.abc import Iterator

from scripts.api_client import BaseAPIClient


class SocrataClient(BaseAPIClient):
    def __init__(self, domain: str, app_token: str | None = None) -> None:
        headers = {"X-App-Token": app_token} if app_token else None
        super().__init__(f"https://{domain}", auth_headers=headers)

    def rows(
        self,
        dataset_id: str,
        *,
        where: str | None = None,
        select: str | None = None,
        group: str | None = None,
        having: str | None = None,
        page_size: int = 50000,
    ) -> Iterator[dict]:
        """Yield every row, paging with $limit/$offset ordered by :id (or the group columns) for stability."""
        params: dict[str, str | int] = {"$limit": page_size, "$order": ":id"}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        if group:
            params["$group"] = group
            params["$order"] = group  # :id is not available on aggregated queries
        if having:
            params["$having"] = having
        offset = 0
        while True:
            page = self.get_list(
                f"resource/{dataset_id}.json", params={**params, "$offset": offset}
            )
            yield from page
            if len(page) < page_size:
                return
            offset += page_size
