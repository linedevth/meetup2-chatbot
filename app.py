# -*- coding: utf-8 -*-

#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from flask import Flask, request, abort, jsonify
from argparse import ArgumentParser
import sys
import os
import errno
import json
from testresult import TestResult
from jenkins import Jenkins
from run_test import RunTest

from linebot import (
    LineBotApi, WebhookHandler
)

from linebot.exceptions import (
    LineBotApiError, InvalidSignatureError
)

from linebot.models import (
    MessageEvent, FollowEvent, UnfollowEvent, PostbackEvent, TextMessage, TextSendMessage, SourceUser,
    SourceGroup, SourceRoom, FlexSendMessage, TemplateSendMessage, VideoSendMessage, ImageSendMessage
)

app = Flask(__name__)

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
jenkins_url = os.getenv('JENKINS_URL', None)
jenkins_user = os.getenv('JENKINS_USER', None)
jenkins_user_token = os.getenv('JENKINS_USER_TOKEN', None)

failed_image = 'https://i2.wp.com/hdsmileys.com/wp-content/uploads/2017/10/sally-crying-loudly.gif'

if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)
if jenkins_url is None:
    print('Specify JENKINS_URL as environment variable.')
    sys.exit(1)
if jenkins_user is None:
    print('Specify JENKINS_USER as environment variable')
    sys.exit(1)
if jenkins_user_token is None:
    print('Specify JENKINS_USER_TOKEN as environment variable')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)
test_result = TestResult()
run_test = RunTest()
jenkins = Jenkins()

static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        print("Got exception from LINE Messaging API: %s\n" % e.message)
        for m in e.error.details:
            print("  %s: %s" % (m.property, m.message))
        print("\n")
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@app.route('/')
def home():
    return jsonify({'status': 'up'})


def make_static_tmp_dir():
    try:
        os.makedirs(static_tmp_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(static_tmp_path):
            pass
        else:
            raise


@app.route('/testresult', methods=['POST'])
def send_test_result():
    data = dict()
    data['job_url'] = request.form.get('job_url')
    data['build_no'] = request.form.get('build_no')
    data['to'] = request.form.get('to')
    result = {
        'result_code': 0,
        'result_message': 'success'
    }
    result_data = jenkins.get_test_result(data['job_url'], data['build_no'])
    messages = []
    bubble_container = test_result.generate_test_result_message(result_data)
    messages.append(FlexSendMessage(alt_text='Test Result', contents=bubble_container))
    if result_data['test_result'] != 'SUCCESS':
        failed_tests = jenkins.get_failed_tests_video(data['job_url'], data['build_no'])
        for failed_test_video in failed_tests['failed_cases']:
            messages.append(VideoSendMessage(original_content_url=failed_test_video, preview_image_url=failed_image))
    print(messages)
    line_bot_api.push_message(data['to'], messages=messages)
    return jsonify(result)


@handler.add(FollowEvent)
def handle_follow_event(event):
    user_id = event.source.user_id
    line_bot_api.unlink_rich_menu_from_user(user_id)
    rich_menu_list = line_bot_api.get_rich_menu_list()
    for rich_menu in rich_menu_list:
        if rich_menu.chat_bar_text == 'Menu':
            print('Linking Rich Menu: \'{0}\' to user_id: \'{1}\''.format(rich_menu.chat_bar_text, user_id))
            line_bot_api.link_rich_menu_to_user(user_id, rich_menu.rich_menu_id)


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    print('Got Text Message Event')
    print('user_id: {}'.format(event.source.user_id))
    if event.message.text == 'video':
        image_url = 'https://images.theconversation.com/files/124181/original/image-20160526-22086-1skmtaf.jpg?ixlib=rb-1.1.0&q=45&auto=format&w=240&h=240&fit=crop'
        # video_url = 'https://www.sample-videos.com/video/mp4/360/big_buck_bunny_360p_5mb.mp4'
        video_url = 'https://s3-ap-northeast-1.amazonaws.com/weekup2/output.mp4'
        line_bot_api.reply_message(event.reply_token, messages=VideoSendMessage(original_content_url=video_url,
                                                                                preview_image_url=image_url))


@handler.add(PostbackEvent)
def handle_postback_event(event):
    postback_data = event.postback.data
    print('postback_data: {}'.format(postback_data))
    if postback_data == 'mode=run_test':
        job_template = run_test.display_test_job_menu(data='start_test={}')
        line_bot_api.reply_message(event.reply_token, messages=TemplateSendMessage(alt_text='Job List',
                                                                                   template=job_template))
    if postback_data == 'mode=rerun_test':
        failed_job_template = run_test.display_failed_test_menu()
        line_bot_api.reply_message(event.reply_token, messages=TemplateSendMessage(alt_text='Failed Job List',
                                                                                   template=failed_job_template))
    if postback_data == 'mode=latest_result':
        job_template = run_test.display_test_job_menu(data='latest_result={}')
        line_bot_api.reply_message(event.reply_token, messages=TemplateSendMessage(alt_text='Job List',
                                                                                   template=job_template))

    if 'start_test=' in postback_data:
        job_name = postback_data.split('=')[1]
        build_result = jenkins.build_job(job_name)
        if build_result:
            line_bot_api.reply_message(event.reply_token, messages=TextSendMessage(text='Trigger Job:{0} Please Wait...'.format(job_name)))
        else:
            line_bot_api.reply_message(event.reply_token, messages=TextSendMessage(text='Trigger Job: {0} Failed!'.format(job_name)))

    if 'latest_result=' in postback_data:
        job_name = postback_data.split('=')[1]
        job_url = os.getenv('JENKINS_URL') + '/job/' + job_name + '/'
        latest_result_data = jenkins.get_test_latest_result(job_url)
        carousel_container = test_result.generate_latest_result(latest_result_data)
        line_bot_api.reply_message(event.reply_token, messages=FlexSendMessage(alt_text='Latest Result', contents=carousel_container))


if __name__ == '__main__':
    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + '[--port <port> [--help]'
    )
    arg_parser.add_argument('-p', '--port', type=int, default=8666, help='port')
    arg_parser.add_argument('-d', '--debug', default=True, help='debug')
    options = arg_parser.parse_args()

    # create tmp dir for download content
    make_static_tmp_dir()

    app.run(host='0.0.0.0',port=options.port)
