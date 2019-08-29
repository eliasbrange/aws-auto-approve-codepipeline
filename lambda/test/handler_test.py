import pytest
import json
import unittest.mock as um
import os

import handler

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture
def mocked_client(monkeypatch):
    mock = um.MagicMock()
    monkeypatch.setattr(handler.boto3, 'client', lambda x: mock)

    return mock


def _mocked_event(event='event'):
    path = os.path.join(CURRENT_DIR, 'events', '{}.json'.format(event))
    with open(path, 'r') as f:
        return json.loads(f.read())


def _get_mocked_response(response):
    path = os.path.join(CURRENT_DIR, 'responses', '{}.json'.format(response))
    with open(path, 'r') as f:
        return json.loads(f.read())


class TestHelpers:
    @pytest.mark.parametrize('input,expected',
        [
            ('ActionToCheck=CreateChangeSetDev', 'CreateChangeSetDev'),
            ('ActionToCheck=', None),
            ('', None),
            ('random-string', None),
            (None, None)
        ])
    def test_get_action_from_custom_data(self, input, expected):
        res = handler._get_action_from_custom_data(input)

        assert res == expected


class TestHandler:
    def test_missing_custom_data(self, mocked_client):
        response = _get_mocked_response('correct-token')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event('event-without-custom-data'), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_missing_stage(self, mocked_client):
        response = _get_mocked_response('missing-stage')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_missing_approval_action(self, mocked_client):
        response = _get_mocked_response('missing-approval-action')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_missing_changeset_action(self, mocked_client):
        response = _get_mocked_response('missing-changeset-action')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_missing_latestexection_key(self, mocked_client):
        handler.MAX_WAIT_FOR_RESPONSE = 0
        handler.WAIT_INCREMENT = 1
        response = _get_mocked_response('missing-latestexecution-key')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_no_token(self, mocked_client):
        response = _get_mocked_response('no-token')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_correct_token(self, mocked_client):
        response = _get_mocked_response('correct-token')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_called_once()

    def test_incorrect_token(self, mocked_client):
        response = _get_mocked_response('incorrect-token')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_changeset_with_failed_status(self, mocked_client):
        response = _get_mocked_response('failed-changeset')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

    def test_changeset_with_changes(self, mocked_client):
        response = _get_mocked_response('changeset-with-changes')
        mocked_client.get_pipeline_state.return_value = response

        handler.handler(_mocked_event(), {})
        mocked_client.put_approval_result.assert_not_called()

