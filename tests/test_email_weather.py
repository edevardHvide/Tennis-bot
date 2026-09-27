"""Regression coverage for weather and weekdays in both email formats."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=['notifications', 'newsletter'])
def builder(request):
    kind = request.param
    spec = importlib.util.spec_from_file_location(
        f'{kind}_weather_email_builder', ROOT / 'lambdas' / kind / 'email_builder.py',
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def build(lookup=None):
        matches = [{
            'facilityId': 'frogner', 'sport': 'tennis', 'date': '2026-09-27',
            'courts': [
                {'time_slot': '16:00-17:00', 'court_name': 'Court 1'},
                {'time_slot': '18:00-19:00', 'court_name': 'Court 2'},
            ],
        }]
        args = ('user@example.com', matches)
        if kind == 'newsletter':
            args += ('2026-09-21', '2026-09-27')
        return getattr(module, f'build_{"notification" if kind == "notifications" else kind}_email')(
            *args, weather_lookup=lookup,
        )
    return build


def test_weather_at_each_time_and_weekday_in_both_formats(builder):
    lookup = Mock(side_effect=lambda facility, date, slot: {
        'emoji': '☀️' if slot.startswith('16') else '🌧️',
        'temp': 13.6 if slot.startswith('16') else 9.1,
    })
    email = builder(lookup)
    for body in (email['html_body'], email['text_body']):
        assert 'Sunday, 27 Sep' in body
        assert '☀️ 14°C' in body
        assert '🌧️ 9°C' in body
        assert body.index('16:00-17:00') < body.index('☀️ 14°C') < body.index('Court 1')
        assert body.index('18:00-19:00') < body.index('🌧️ 9°C') < body.index('Court 2')
    assert all(call.args[0:2] == ('frogner', '2026-09-27') for call in lookup.call_args_list)


@pytest.mark.parametrize('lookup', [None, Mock(return_value=None), Mock(side_effect=RuntimeError('unavailable'))])
def test_missing_weather_never_blocks_email(builder, lookup):
    email = builder(lookup)
    for body in (email['html_body'], email['text_body']):
        assert 'Sunday, 27 Sep' in body
        assert '16:00-17:00' in body
        assert 'Court 1' in body
        assert '°C' not in body


def test_zero_temperature_is_displayed(builder):
    email = builder(lambda *_: {'emoji': '❄️', 'temp': 0})
    assert '❄️ 0°C' in email['html_body']
    assert '❄️ 0°C' in email['text_body']


@pytest.mark.parametrize('kind', ['notifications', 'newsletter'])
def test_handlers_pass_weather_lookup_to_email_builder(kind, monkeypatch):
    import sys
    from types import SimpleNamespace
    from facilities import get_weather_region

    monkeypatch.setenv('AWS_DEFAULT_REGION', 'eu-north-1')
    spec = importlib.util.spec_from_file_location(
        f'{kind}_weather_handler', ROOT / 'lambdas' / kind / 'handler.py',
    )
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    match = {'userId': 'user@example.com', 'facilityId': 'frogner',
             'date': '2026-09-27', 'courts': []}
    monkeypatch.setitem(sys.modules, 'matcher', SimpleNamespace(match_preferences=Mock(return_value=[match])))
    monkeypatch.setitem(sys.modules, 'dedup', SimpleNamespace(
        filter_already_notified=Mock(return_value=[match]), record_notifications=Mock(return_value=1),
    ))
    lookup = Mock(return_value=None)
    factory = Mock(return_value=lookup)
    monkeypatch.setitem(sys.modules, 'weather', SimpleNamespace(make_weather_lookup=factory))
    build = Mock(return_value={'subject': 'test', 'html_body': 'html', 'text_body': 'text'})
    method = 'build_notification_email' if kind == 'notifications' else 'build_newsletter_email'
    monkeypatch.setitem(sys.modules, 'email_builder', SimpleNamespace(**{method: build}))
    table = Mock()
    table.get_item.return_value = {}
    dynamo = Mock()
    dynamo.Table.return_value = table
    monkeypatch.setattr(handler, '_get_dynamodb', lambda: dynamo)
    monkeypatch.setattr(handler, '_scan_all_preferences', lambda _: [{'userId': 'user@example.com'}])
    monkeypatch.setattr(handler, '_send_email', Mock(return_value=True))
    if kind == 'newsletter':
        monkeypatch.setattr(handler, 'NEWSLETTER_TEST_RECIPIENT', '')
        monkeypatch.setattr(handler, '_load_availability', lambda *_: {'frogner': {'2026-09-27': {'16:00': ['Court 1']}}})
    result = handler.lambda_handler({'diff': {'frogner': {'2026-09-27': {'16:00': ['Court 1']}}}}, None)
    assert result['summary']['emails_sent'] == 1
    dynamo.Table.assert_any_call(handler.WEATHER_TABLE)
    factory.assert_called_once_with(table, get_weather_region)
    assert build.call_args.kwargs['weather_lookup'] is lookup
