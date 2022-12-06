from datetime import datetime
from mock import MagicMock
import mock
import time
from sentry_sdk.integrations.opentelemetry.span_processor import SentrySpanProcessor
from sentry_sdk.tracing import Span, Transaction

from opentelemetry.trace import SpanKind


def test_get_otel_context():
    otel_span = MagicMock()
    otel_span.attributes = {"foo": "bar"}
    otel_span.resource = MagicMock()
    otel_span.resource.attributes = {"baz": "qux"}

    span_processor = SentrySpanProcessor()
    otel_context = span_processor._get_otel_context(otel_span)

    assert otel_context == {
        "attributes": {"foo": "bar"},
        "resource": {"baz": "qux"},
    }


def test_get_trace_data_with_span_and_trace():
    otel_span = MagicMock()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = None

    parent_context = {}

    span_processor = SentrySpanProcessor()
    sentry_trace_data = span_processor._get_trace_data(otel_span, parent_context)
    assert sentry_trace_data["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert sentry_trace_data["span_id"] == "1234567890abcdef"
    assert sentry_trace_data["parent_span_id"] is None
    assert sentry_trace_data["parent_sampled"] is None
    assert sentry_trace_data["baggage"] is None


def test_get_trace_data_with_span_and_trace_and_parent():
    otel_span = MagicMock()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = MagicMock()
    otel_span.parent.span_id = int("abcdef1234567890", 16)

    parent_context = {}

    span_processor = SentrySpanProcessor()
    sentry_trace_data = span_processor._get_trace_data(otel_span, parent_context)
    assert sentry_trace_data["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert sentry_trace_data["span_id"] == "1234567890abcdef"
    assert sentry_trace_data["parent_span_id"] == "abcdef1234567890"
    assert sentry_trace_data["parent_sampled"] is None
    assert sentry_trace_data["baggage"] is None


def test_get_trace_data_with_sentry_trace():
    otel_span = MagicMock()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = MagicMock()
    otel_span.parent.span_id = int("abcdef1234567890", 16)

    parent_context = {}

    with mock.patch(
        "sentry_sdk.integrations.opentelemetry.span_processor.get_value",
        side_effect=[
            ("1234567890abcdef1234567890abcdef", "1234567890abcdef", True),
            None,
        ],
    ):
        span_processor = SentrySpanProcessor()
        sentry_trace_data = span_processor._get_trace_data(otel_span, parent_context)
        assert sentry_trace_data["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert sentry_trace_data["span_id"] == "1234567890abcdef"
        assert sentry_trace_data["parent_span_id"] == "abcdef1234567890"
        assert sentry_trace_data["parent_sampled"] is True
        assert sentry_trace_data["baggage"] is None

    with mock.patch(
        "sentry_sdk.integrations.opentelemetry.span_processor.get_value",
        side_effect=[
            ("1234567890abcdef1234567890abcdef", "1234567890abcdef", False),
            None,
        ],
    ):
        span_processor = SentrySpanProcessor()
        sentry_trace_data = span_processor._get_trace_data(otel_span, parent_context)
        assert sentry_trace_data["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert sentry_trace_data["span_id"] == "1234567890abcdef"
        assert sentry_trace_data["parent_span_id"] == "abcdef1234567890"
        assert sentry_trace_data["parent_sampled"] is False
        assert sentry_trace_data["baggage"] is None


def test_get_trace_data_with_sentry_trace_and_baggage():
    otel_span = MagicMock()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = MagicMock()
    otel_span.parent.span_id = int("abcdef1234567890", 16)

    parent_context = {}

    baggage = (
        "sentry-trace_id=771a43a4192642f0b136d5159a501700,"
        "sentry-public_key=49d0f7386ad645858ae85020e393bef3,"
        "sentry-sample_rate=0.01337,sentry-user_id=Am%C3%A9lie"
    )

    with mock.patch(
        "sentry_sdk.integrations.opentelemetry.span_processor.get_value",
        side_effect=[
            ("1234567890abcdef1234567890abcdef", "1234567890abcdef", True),
            baggage,
        ],
    ):
        span_processor = SentrySpanProcessor()
        sentry_trace_data = span_processor._get_trace_data(otel_span, parent_context)
        assert sentry_trace_data["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert sentry_trace_data["span_id"] == "1234567890abcdef"
        assert sentry_trace_data["parent_span_id"] == "abcdef1234567890"
        assert sentry_trace_data["parent_sampled"]
        assert sentry_trace_data["baggage"] == baggage


def test_update_span_with_otel_data_http_method():
    sentry_span = Span()

    otel_span = MagicMock()
    otel_span.name = "Test OTel Span"
    otel_span.kind = SpanKind.CLIENT
    otel_span.attributes = {
        "http.method": "GET",
        "http.status_code": 429,
        "http.status_text": "xxx",
        "http.user_agent": "curl/7.64.1",
        "net.peer.name": "example.com",
        "http.target": "/",
    }

    span_processor = SentrySpanProcessor()
    span_processor._update_span_with_otel_data(sentry_span, otel_span)

    assert sentry_span.op == "http.client"
    assert sentry_span.description == "GET example.com /"
    assert sentry_span._tags["http.status_code"] == "429"
    assert sentry_span.status == "resource_exhausted"

    assert sentry_span._data["http.method"] == "GET"
    assert sentry_span._data["http.status_code"] == 429
    assert sentry_span._data["http.status_text"] == "xxx"
    assert sentry_span._data["http.user_agent"] == "curl/7.64.1"
    assert sentry_span._data["net.peer.name"] == "example.com"
    assert sentry_span._data["http.target"] == "/"


def test_update_span_with_otel_data_http_method2():
    sentry_span = Span()

    otel_span = MagicMock()
    otel_span.name = "Test OTel Span"
    otel_span.kind = SpanKind.SERVER
    otel_span.attributes = {
        "http.method": "GET",
        "http.status_code": 429,
        "http.status_text": "xxx",
        "http.user_agent": "curl/7.64.1",
        "http.url": "https://httpbin.org/status/403?password=123&username=test@example.com&author=User123&auth=1234567890abcdef",
    }

    span_processor = SentrySpanProcessor()
    span_processor._update_span_with_otel_data(sentry_span, otel_span)

    assert sentry_span.op == "http.server"
    assert sentry_span.description == "GET https://httpbin.org/status/403"
    assert sentry_span._tags["http.status_code"] == "429"
    assert sentry_span.status == "resource_exhausted"

    assert sentry_span._data["http.method"] == "GET"
    assert sentry_span._data["http.status_code"] == 429
    assert sentry_span._data["http.status_text"] == "xxx"
    assert sentry_span._data["http.user_agent"] == "curl/7.64.1"
    assert (
        sentry_span._data["http.url"]
        == "https://httpbin.org/status/403?password=123&username=test@example.com&author=User123&auth=1234567890abcdef"
    )


def test_update_span_with_otel_data_db_query():
    sentry_span = Span()

    otel_span = MagicMock()
    otel_span.name = "Test OTel Span"
    otel_span.attributes = {
        "db.system": "postgresql",
        "db.statement": "SELECT * FROM table where pwd = '123456'",
    }

    span_processor = SentrySpanProcessor()
    span_processor._update_span_with_otel_data(sentry_span, otel_span)

    assert sentry_span.op == "db"
    assert sentry_span.description == "SELECT * FROM table where pwd = '123456'"

    assert sentry_span._data["db.system"] == "postgresql"
    assert (
        sentry_span._data["db.statement"] == "SELECT * FROM table where pwd = '123456'"
    )


def test_on_start_transaction():
    otel_span = MagicMock()
    otel_span.name = "Sample OTel Span"
    otel_span.start_time = time.time_ns()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = MagicMock()
    otel_span.parent.span_id = int("abcdef1234567890", 16)

    parent_context = {}

    fake_client = MagicMock()
    fake_client.options = {"instrumenter": "otel"}

    current_hub = MagicMock()
    current_hub.client = fake_client

    fake_hub = MagicMock()
    fake_hub.current = current_hub

    with mock.patch(
        "sentry_sdk.integrations.opentelemetry.span_processor.Hub", fake_hub
    ):
        span_processor = SentrySpanProcessor()
        span_processor.on_start(otel_span, parent_context)

        fake_hub.current.start_transaction.assert_called_once_with(
            name="Sample OTel Span",
            span_id="1234567890abcdef",
            parent_span_id="abcdef1234567890",
            trace_id="1234567890abcdef1234567890abcdef",
            baggage=None,
            start_timestamp=datetime.fromtimestamp(otel_span.start_time / 1e9),
            instrumenter="otel",
        )

        assert len(span_processor.otel_span_map.keys()) == 1
        assert list(span_processor.otel_span_map.keys())[0] == "1234567890abcdef"


def test_on_start_child():
    otel_span = MagicMock()
    otel_span.name = "Sample OTel Span"
    otel_span.start_time = time.time_ns()
    otel_span.context = MagicMock()
    otel_span.context.trace_id = int("1234567890abcdef1234567890abcdef", 16)
    otel_span.context.span_id = int("1234567890abcdef", 16)
    otel_span.parent = MagicMock()
    otel_span.parent.span_id = int("abcdef1234567890", 16)

    parent_context = {}

    fake_client = MagicMock()
    fake_client.options = {"instrumenter": "otel"}

    current_hub = MagicMock()
    current_hub.client = fake_client

    fake_hub = MagicMock()
    fake_hub.current = current_hub

    with mock.patch(
        "sentry_sdk.integrations.opentelemetry.span_processor.Hub", fake_hub
    ):
        fake_span = MagicMock()

        span_processor = SentrySpanProcessor()
        span_processor.otel_span_map["abcdef1234567890"] = fake_span
        span_processor.on_start(otel_span, parent_context)

        fake_span.start_child.assert_called_once_with(
            span_id="1234567890abcdef",
            description="Sample OTel Span",
            start_timestamp=datetime.fromtimestamp(otel_span.start_time / 1e9),
            instrumenter="otel",
        )

        assert len(span_processor.otel_span_map.keys()) == 2
        assert "abcdef1234567890" in span_processor.otel_span_map.keys()
        assert "1234567890abcdef" in span_processor.otel_span_map.keys()


def test_on_end_no_sentry_span():
    """
    If on_end is called on a span that is not in the otel_span_map, it should be a no-op.
    """
    otel_span = MagicMock()
    otel_span.name = "Sample OTel Span"
    otel_span.end_time = time.time_ns()
    otel_span.context = MagicMock()
    otel_span.context.span_id = int("1234567890abcdef", 16)

    span_processor = SentrySpanProcessor()
    span_processor.otel_span_map = {}
    span_processor._get_otel_context = MagicMock()
    span_processor._update_span_with_otel_data = MagicMock()

    span_processor.on_end(otel_span)

    span_processor._get_otel_context.assert_not_called()
    span_processor._update_span_with_otel_data.assert_not_called()


def test_on_end_sentry_transaction():
    """
    Test on_end for a sentry Transaction.
    """
    otel_span = MagicMock()
    otel_span.name = "Sample OTel Span"
    otel_span.end_time = time.time_ns()
    otel_span.context = MagicMock()
    otel_span.context.span_id = int("1234567890abcdef", 16)

    fake_sentry_span = MagicMock(spec=Transaction)
    fake_sentry_span.set_context = MagicMock()
    fake_sentry_span.finish = MagicMock()

    span_processor = SentrySpanProcessor()
    span_processor._get_otel_context = MagicMock()
    span_processor._update_span_with_otel_data = MagicMock()
    span_processor.otel_span_map["1234567890abcdef"] = fake_sentry_span

    span_processor.on_end(otel_span)

    fake_sentry_span.set_context.assert_called_once()
    span_processor._update_span_with_otel_data.assert_not_called()
    fake_sentry_span.finish.assert_called_once()


def test_on_end_sentry_span():
    """
    Test on_end for a sentry Span.
    """
    otel_span = MagicMock()
    otel_span.name = "Sample OTel Span"
    otel_span.end_time = time.time_ns()
    otel_span.context = MagicMock()
    otel_span.context.span_id = int("1234567890abcdef", 16)

    fake_sentry_span = MagicMock(spec=Span)
    fake_sentry_span.set_context = MagicMock()
    fake_sentry_span.finish = MagicMock()

    span_processor = SentrySpanProcessor()
    span_processor._get_otel_context = MagicMock()
    span_processor._update_span_with_otel_data = MagicMock()
    span_processor.otel_span_map["1234567890abcdef"] = fake_sentry_span

    span_processor.on_end(otel_span)

    fake_sentry_span.set_context.assert_not_called()
    span_processor._update_span_with_otel_data.assert_called_once_with(
        fake_sentry_span, otel_span
    )
    fake_sentry_span.finish.assert_called_once()