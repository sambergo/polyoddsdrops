import json

from src.websocket.messages import parse_message


def test_parses_book_without_retaining_order_levels() -> None:
    raw = json.dumps(
        {
            "event_type": "book",
            "asset_id": "asset-1",
            "market": "market-1",
            "timestamp": "1757908892351",
            "bids": [{"price": "0.48"}, {"price": "0.50"}],
            "asks": [{"price": "0.54"}, {"price": "0.52"}],
        }
    )

    messages = parse_message(raw)

    assert len(messages) == 1
    assert messages[0].asset_id == "asset-1"
    assert messages[0].best_bid == 0.50
    assert messages[0].best_ask == 0.52
    assert messages[0].mid_price == 0.51


def test_price_change_uses_nested_asset_ids_and_latest_state() -> None:
    raw = json.dumps(
        {
            "event_type": "price_change",
            "market": "market-1",
            "timestamp": "1757908892351",
            "price_changes": [
                {
                    "asset_id": "asset-1",
                    "best_bid": "0.49",
                    "best_ask": "0.53",
                },
                {
                    "asset_id": "asset-2",
                    "best_bid": "0.30",
                    "best_ask": "0.35",
                },
                {
                    "asset_id": "asset-1",
                    "best_bid": "0.50",
                    "best_ask": "0.52",
                },
            ],
        }
    )

    messages = {message.asset_id: message for message in parse_message(raw)}

    assert set(messages) == {"asset-1", "asset-2"}
    assert messages["asset-1"].best_bid == 0.50
    assert messages["asset-1"].best_ask == 0.52


def test_ignores_incomplete_or_invalid_messages() -> None:
    assert parse_message("not-json") == []
    assert parse_message(json.dumps({"event_type": "book", "asset_id": ""})) == []
    assert (
        parse_message(
            json.dumps(
                {
                    "event_type": "price_change",
                    "price_changes": [{"asset_id": "asset-1", "price": "0.5"}],
                }
            )
        )
        == []
    )
