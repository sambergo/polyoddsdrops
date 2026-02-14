#!/usr/bin/env python3
"""Explore Polymarket WebSocket API.

Connects to the CLOB market WebSocket, subscribes to sample tokens,
and logs all incoming messages to understand the data format.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from websockets.asyncio.client import connect, ClientConnection

WS_ENDPOINT = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
HEARTBEAT_INTERVAL = 10  # seconds

# Token IDs from active NBA markets (NBA Champion 2026)
# These are high-volume markets that should have activity
TEST_TOKENS = [
    # Oklahoma City Thunder - Yes token (highest volume NBA team)
    "53866778779597540216098195494948116143462973030875609635557099377395290457894",
    # Boston Celtics - Yes token
    "101657448900324364213467059356648689270832606863187352286785694887095023173679",
    # Cleveland Cavaliers - Yes token
    "111039354521750894925304771773687530394455073318948424656845140321925374032772",
]

OUTPUT_FILE = (
    Path(__file__).parent.parent / "docs" / "examples" / "websocket_raw_capture.json"
)


async def heartbeat(ws: ClientConnection) -> None:
    """Send PING every 10 seconds to keep connection alive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await ws.send("PING")
        print(f"[{datetime.now().isoformat()}] PING sent")


async def subscribe(ws: ClientConnection, token_ids: list[str]) -> None:
    """Subscribe to market channel for given tokens."""
    msg = {"assets_ids": token_ids, "type": "market"}
    await ws.send(json.dumps(msg))
    print(f"[{datetime.now().isoformat()}] Subscribed to {len(token_ids)} tokens")


async def listen(
    ws: ClientConnection,
    duration: int = 60,
) -> list[dict]:
    """Listen for messages and collect them."""
    messages: list[dict] = []
    start = asyncio.get_event_loop().time()
    message_types_seen: set[str] = set()

    print(f"\nListening for {duration} seconds...\n")

    while asyncio.get_event_loop().time() - start < duration:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            timestamp = datetime.now().isoformat()

            # Handle PONG response
            if raw == "PONG":
                print(f"[{timestamp}] PONG received")
                continue

            # Parse JSON messages
            try:
                data = json.loads(raw)

                # Handle both single objects and arrays
                items = data if isinstance(data, list) else [data]

                for item in items:
                    if isinstance(item, dict):
                        event_type = item.get("event_type", "unknown")

                        # Track unique message types
                        if event_type not in message_types_seen:
                            message_types_seen.add(event_type)
                            print(f"[{timestamp}] NEW MESSAGE TYPE: {event_type}")
                            print(f"  Full message: {json.dumps(item, indent=2)[:500]}")
                        else:
                            # Abbreviated output for repeat types
                            asset_id = item.get("asset_id", "?")[:20] + "..."
                            print(f"[{timestamp}] {event_type} | asset: {asset_id}")

                        messages.append(
                            {
                                "timestamp": timestamp,
                                "event_type": event_type,
                                "data": item,
                            }
                        )
                    else:
                        print(f"[{timestamp}] UNEXPECTED ITEM: {item}")
                        messages.append(
                            {
                                "timestamp": timestamp,
                                "event_type": "unexpected",
                                "data": item,
                            }
                        )

            except json.JSONDecodeError:
                print(f"[{timestamp}] RAW: {raw[:100]}")
                messages.append(
                    {
                        "timestamp": timestamp,
                        "event_type": "raw",
                        "data": raw,
                    }
                )

        except asyncio.TimeoutError:
            continue

    return messages


def summarize_messages(messages: list[dict]) -> dict:
    """Create summary of collected messages."""
    type_counts: dict[str, int] = {}
    type_examples: dict[str, dict] = {}

    for msg in messages:
        event_type = msg.get("event_type", "unknown")
        type_counts[event_type] = type_counts.get(event_type, 0) + 1

        # Keep first example of each type
        if event_type not in type_examples:
            type_examples[event_type] = msg

    return {
        "total_messages": len(messages),
        "message_types": type_counts,
        "examples": type_examples,
        "all_messages": messages,
    }


async def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("Polymarket WebSocket Explorer")
    print("=" * 60)
    print(f"Endpoint: {WS_ENDPOINT}")
    print(f"Tokens: {len(TEST_TOKENS)}")
    print("=" * 60)

    try:
        async with connect(WS_ENDPOINT) as ws:
            print(f"[{datetime.now().isoformat()}] Connected!")

            # Start heartbeat task
            heartbeat_task = asyncio.create_task(heartbeat(ws))

            # Subscribe to test tokens
            await subscribe(ws, TEST_TOKENS)

            # Listen for messages
            messages = await listen(ws, duration=60)

            # Cancel heartbeat
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Summarize and save
            summary = summarize_messages(messages)

            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"Total messages: {summary['total_messages']}")
            print(f"Message types: {summary['message_types']}")

            # Save to file
            OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_FILE, "w") as f:
                json.dump(summary, f, indent=2)
            print(f"\nSaved to: {OUTPUT_FILE}")

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
