import json
import logging
import re
import time

import boto3

logger = logging.getLogger(__name__)

MAX_WAIT_FOR_RESPONSE = 10
WAIT_INCREMENT = 1


class PipelineStateError(Exception):
    pass


class PipelineStageNotFoundError(PipelineStateError):
    pass


class PipelineActionNotFoundError(PipelineStateError):
    pass


class PipelineMissingKeyError(PipelineStateError):
    pass


def _get_stage_from_response(response, stage_name):
    """ Extract information about a specific stage from a pipeline response.

    :param response: The API response
    :param stage_name: The stage to extract
    :return: The stage information
    """
    try:
        return next(s for s in response['stageStates']
                    if s['stageName'] == stage_name)
    except StopIteration:
        raise PipelineStageNotFoundError(stage_name)


def _get_action_from_stage(stage, action):
    """ Extract the latestExecution information for an action in a stage.

    :param stage: The stage from which to extract the action
    :param action: The name of the action
    :return: THe latestExecution information
    """
    try:
        action = next(a for a in stage['actionStates']
                      if a['actionName'] == action)
        return action['latestExecution']
    except StopIteration:
        raise PipelineActionNotFoundError(action)
    except KeyError as e:
        # The actions in the response only includes the key `latestExection` if
        # the action has started. Sometimes, the API does not reflect that the
        # approval action has started even though SNS has been notified.
        # If that is the case, we return a `PipelineMissingKeyError` so that the
        # caller can retry the call.
        raise PipelineMissingKeyError(e)


def _get_state(client, pipeline_name, stage_name, approval_action,
               action_to_check):
    """Fetches the state of the actions from the pipeline stage.

    Sometimes the SNS notification reaches lambda before the CodePipeline API
    has been updated with the latest execution. If that is the case we retry
    every `WAIT_INCREMENT` second(s) for a maximum of `MAX_WAIT_FOR_RESPONSE`
    second(s).

    :param client: A CodePipeline boto client
    :param pipeline_name: The name of the pipeline
    :param stage_name: The name of the stage
    :param approval_action: The name of the manual approval action
    :param action_to_check: The name of the action to check
    :return: Tuple containing (approval_action_state, action_to_check_state)
    """
    wait = 0

    while wait <= MAX_WAIT_FOR_RESPONSE:
        try:
            logger.warning('Fetching pipeline state.')
            response = client.get_pipeline_state(name=pipeline_name)

            stage = _get_stage_from_response(response, stage_name)
            approval_action_state = _get_action_from_stage(
                stage, approval_action)
            action_to_check_state = _get_action_from_stage(
                stage, action_to_check)

            return approval_action_state, action_to_check_state
        except PipelineMissingKeyError:
            logger.warning('Response does not contain latest execution yet. '
                           'Waiting for %d seconds.' % WAIT_INCREMENT)
            time.sleep(WAIT_INCREMENT)
            wait += WAIT_INCREMENT
    else:
        raise TimeoutError


def _get_action_from_custom_data(custom_data):
    """ Extracts action to check name from event customData.

    :param custom_data: The custom data received in the event
    :return: Returns the action name to check if present
    """
    if not custom_data:
        return None

    pattern = r'^ActionToCheck=(\w+)$'
    m = re.search(pattern, custom_data)

    return m.group(1) if m else None


def handler(event, context):
    sns_message = json.loads(event['Records'][0]['Sns']['Message'])

    token = sns_message['approval']['token']
    pipeline = sns_message['approval']['pipelineName']
    stage = sns_message['approval']['stageName']
    approval_action = sns_message['approval']['actionName']
    action_to_check = _get_action_from_custom_data(
        sns_message['approval']['customData'])

    if not action_to_check:
        logger.error('Missing ActionToCheck=ACTION_NAME in SNS customData.')
        return

    client = boto3.client('codepipeline')

    try:
        approval_action_state, action_to_check_state = _get_state(
            client, pipeline, stage, approval_action, action_to_check)
    except PipelineStageNotFoundError as e:
        logger.error('Pipeline response did not contain expected stage: {}'
                     .format(e))
        return
    except PipelineActionNotFoundError as e:
        logger.error('Pipeline response did not contain expected action: {}'
                     .format(e))
        return
    except TimeoutError:
        logger.error('Did not get complete pipeline response within {} seconds.'
                     .format(MAX_WAIT_FOR_RESPONSE))
        return

    state_approval_token = approval_action_state.get('token')

    if not state_approval_token:
        logger.info('Response did not include an approval token.')
        return

    if not state_approval_token == token:
        logger.info('Token in SNS event does not match token in response.')
        return

    if not action_to_check_state.get('status') == "Succeeded":
        logger.info('{} does not have a successful status.'
                    .format(action_to_check))
        return

    summary = action_to_check_state.get('summary', '')
    if summary.endswith('was created with no changes.'):
        logger.info('The change set was created without any changes. '
                    'Automatically approving approval request.')
        client.put_approval_result(
            pipelineName=pipeline,
            stageName=stage,
            actionName=approval_action,
            result={
                'summary': 'Automatically approved by Lambda.',
                'status': 'Approved'
            },
            token=token
        )
        return

    logger.info('There seems to be changes in the change set. '
                'Skipping automatic approval.')
