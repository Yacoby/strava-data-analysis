import json
import os
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, request, redirect, jsonify
from stravalib.client import Client

import config

app = Flask(__name__)
strava_client = Client()

@app.route('/')
def index():
    if not strava_client.access_token:
        return redirect('/auth')
    return app.send_static_file('index.html')

@app.route('/auth')
def auth():
    state = request.args.get('state')
    [s, nl, path, q, frag] = urlsplit(request.url)
    redir_url = urlunsplit([s, nl, 'code_grant', '', ''])

    authorize_url = strava_client.authorization_url(client_id=config.STRAVA_CLIENT_ID,
                                                    redirect_uri=redir_url, state=state)
    return redirect(authorize_url)

@app.route('/code_grant')
def code_grant():
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

    activity_ids = [a.id for a in strava_client.get_activities()]
    with open(os.path.join('cached_activities', 'activities.json'), 'w') as fh:
        json.dump(activity_ids, fh)

    for activity_id in activity_ids:
        streams = strava_client.get_activity_streams(activity_id, types=types, resolution='high')
        streams = {k: list(v.data) for k, v in streams.items()}
        with open(os.path.join('cached_activities', str(activity_id) + '.json'), 'w') as fh:
            json.dump(streams, fh)
    return jsonify(True)

@app.route('/activities')
def activities():
    with open(os.path.join('cached_activities', 'activities.json'), 'r') as fh:
        ids = json.load(fh)

    activity_data = {}
    for act_id in ids:
        with open(os.path.join('cached_activities', str(act_id) + '.json'), 'r') as fh:
            activity_data[act_id] = json.load(fh)
    return jsonify(activity_data)


if __name__ == "__main__":
    app.run()

