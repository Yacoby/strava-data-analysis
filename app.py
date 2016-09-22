import json
import os
import zipfile
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, request, redirect, jsonify
from stravalib.client import Client


app = Flask(__name__)
strava_client = Client()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/auth')
def auth():
    try:
        import config
    except ImportError:
        return (jsonify({'error': 'Not setup for auth'}), 500)
    state = request.args.get('state')
    [s, nl, path, q, frag] = urlsplit(request.url)
    redir_url = urlunsplit([s, nl, 'code_grant', '', ''])

    authorize_url = strava_client.authorization_url(client_id=config.STRAVA_CLIENT_ID,
                                                    redirect_uri=redir_url, state=state)
    return redirect(authorize_url)

@app.route('/code_grant')
def code_grant():
    try:
        import config
    except ImportError:
        return (jsonify({'error': 'Not setup for auth'}), 500)
    code = request.args.get('code')
    state = request.args.get('state')
    access_token = strava_client.exchange_code_for_token(client_id=config.STRAVA_CLIENT_ID,
                                                         client_secret=config.STRAVA_SECRET,
                                                         code=code)
    strava_client.access_token = access_token
    if state:
        return redirect(state)
    return redirect('/')

@app.route('/cache')
def cache():
    if not strava_client.access_token:
        return redirect('/auth?state=/cache')

    if strava_client.get_athlete().id != config.STRAVA_MY_ATHLETE_ID:
        return (jsonify(False), 401)

    types = ['time', 'latlng', 'altitude',]
    with zipfile.ZipFile('strava_data.zip', 'w') as data_file:
        activity_ids = [a.id for a in strava_client.get_activities()]
        data_file.writestr('activities.json', json.dumps(activity_ids), zipfile.ZIP_LZMA)

        for activity_id in activity_ids:
            streams = strava_client.get_activity_streams(activity_id, types=types, resolution='high')
            streams = {k: list(v.data) for k, v in streams.items()}
            data_file.writestr(str(activity_id), json.dumps(streams), zipfile.ZIP_LZMA)
    return jsonify(True)

@app.route('/activities')
def activities():
    with zipfile.ZipFile('strava_data.zip') as data_file:
        with data_file.open('activities.json') as fh:
            ids = json.loads(fh.read().decode('ascii'))

        activity_data = {}
        for act_id in ids:
            with data_file.open(str(act_id)) as fh:
                activity_data[act_id] = json.loads(fh.read().decode('ascii'))
    return jsonify(activity_data)


if __name__ == "__main__":
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0', port=port)
