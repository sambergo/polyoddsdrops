import unittest
from unittest.mock import Mock, patch

import httpx

from src.config import MarketFilterConfig
from src.gamma.client import GammaClient


def make_filter_config() -> MarketFilterConfig:
    return MarketFilterConfig(
        min_liquidity=0,
        max_spread=1,
        min_volume_24h=0,
        min_price=0,
        max_price=1,
    )


def response(status_code: int, json_data: list[dict] | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://gamma-api.polymarket.com/events")
    return httpx.Response(status_code, request=request, json=json_data)


class GammaClientPaginationTest(unittest.TestCase):
    def test_fetch_events_by_tag_treats_late_422_as_end_of_results(self) -> None:
        client = GammaClient(make_filter_config())
        first_page = [{"id": i} for i in range(100)]
        mock_http_client = Mock()
        mock_http_client.get.side_effect = [
            response(200, first_page),
            response(422, []),
        ]
        mock_http_client.__enter__ = Mock(return_value=mock_http_client)
        mock_http_client.__exit__ = Mock(return_value=None)

        with patch("src.gamma.client.httpx.Client", return_value=mock_http_client):
            events = client.fetch_events_by_tag(1)

        self.assertEqual(events, first_page)
        self.assertEqual(mock_http_client.get.call_count, 2)

    def test_fetch_events_by_tag_raises_initial_422(self) -> None:
        client = GammaClient(make_filter_config())
        mock_http_client = Mock()
        mock_http_client.get.return_value = response(422, [])
        mock_http_client.__enter__ = Mock(return_value=mock_http_client)
        mock_http_client.__exit__ = Mock(return_value=None)

        with patch("src.gamma.client.httpx.Client", return_value=mock_http_client):
            with self.assertRaises(httpx.HTTPStatusError):
                client.fetch_events_by_tag(1)


if __name__ == "__main__":
    unittest.main()
