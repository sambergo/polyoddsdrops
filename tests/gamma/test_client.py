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


def response(status_code: int, json_data: object | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://gamma-api.polymarket.com/events")
    return httpx.Response(status_code, request=request, json=json_data)


class GammaClientPaginationTest(unittest.TestCase):
    def test_fetch_events_by_tag_uses_next_cursor(self) -> None:
        client = GammaClient(make_filter_config())
        first_page = [{"id": i} for i in range(100)]
        second_page = [{"id": 100}]
        mock_http_client = Mock()
        mock_http_client.get.side_effect = [
            response(200, {"events": first_page, "next_cursor": "next-page"}),
            response(200, {"events": second_page}),
        ]
        mock_http_client.__enter__ = Mock(return_value=mock_http_client)
        mock_http_client.__exit__ = Mock(return_value=None)

        with patch("src.gamma.client.httpx.Client", return_value=mock_http_client):
            events = client.fetch_events_by_tag(1)

        self.assertEqual(events, first_page + second_page)
        self.assertEqual(mock_http_client.get.call_count, 2)
        first_call, second_call = mock_http_client.get.call_args_list
        self.assertTrue(first_call.args[0].endswith("/events/keyset"))
        self.assertNotIn("after_cursor", first_call.kwargs["params"])
        self.assertEqual(second_call.kwargs["params"]["after_cursor"], "next-page")

    def test_fetch_events_by_tag_raises_on_late_422(self) -> None:
        client = GammaClient(make_filter_config())
        mock_http_client = Mock()
        mock_http_client.get.side_effect = [
            response(200, {"events": [{"id": 1}], "next_cursor": "next-page"}),
            response(422, []),
        ]
        mock_http_client.__enter__ = Mock(return_value=mock_http_client)
        mock_http_client.__exit__ = Mock(return_value=None)

        with patch("src.gamma.client.httpx.Client", return_value=mock_http_client):
            with self.assertRaises(httpx.HTTPStatusError):
                client.fetch_events_by_tag(1)

    def test_fetch_events_by_tag_passes_start_time_range(self) -> None:
        client = GammaClient(make_filter_config())
        mock_http_client = Mock()
        mock_http_client.get.return_value = response(200, {"events": []})
        mock_http_client.__enter__ = Mock(return_value=mock_http_client)
        mock_http_client.__exit__ = Mock(return_value=None)

        with patch("src.gamma.client.httpx.Client", return_value=mock_http_client):
            client.fetch_events_by_tag(
                1,
                start_time_min="2026-09-08T12:00:00Z",
                start_time_max="2026-09-10T12:00:00Z",
            )

        params = mock_http_client.get.call_args.kwargs["params"]
        self.assertEqual(params["start_time_min"], "2026-09-08T12:00:00Z")
        self.assertEqual(params["start_time_max"], "2026-09-10T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
