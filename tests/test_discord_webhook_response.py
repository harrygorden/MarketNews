import httpx

from shared.services.discord import DiscordNotifier


def test_parse_message_id_handles_no_content():
    resp = httpx.Response(status_code=204, request=httpx.Request("POST", "http://example.com"))
    notifier = DiscordNotifier(digests_webhook="http://example.com")
    assert notifier._parse_message_id(resp) is None

