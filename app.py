from geographiclib.geodesic import Geodesic
import math
import shapely.geometry
import json
import os
import zipfile
from urllib.parse import urlsplit, urlunsplit
from itertools import zip_longest

from flask import Flask, request, redirect, jsonify, send_from_directory
from flask_compress import Compress

from stravalib.client import Client

import lifts

app = Flask(__name__)
Compress(app)

strava_client = Client()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/maps/<path:filename>')
def serve_static(filename):
    return send_from_directory("static/", filename)

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
    try:
        import config
    except ImportError:
        return (jsonify({'error': 'Not setup for auth'}), 500)

    if not strava_client.access_token:
        return redirect('/auth?state=/cache')

    if strava_client.get_athlete().id != config.STRAVA_MY_ATHLETE_ID:
        return (jsonify(False), 401)

    types = ['time', 'latlng', 'altitude',]
    with zipfile.ZipFile('strava_data.zip', 'w') as data_file:
        activity_ids = [a.id for a in strava_client.get_activities()]
        data_file.writestr('activities.json', json.dumps(activity_ids), zipfile.ZIP_LZMA)

        for activity_id in activity_ids:
            print('Getting: ' + activity_id)
            streams = strava_client.get_activity_streams(activity_id, types=types, resolution='high')
            streams = {k: list(v.data) for k, v in streams.items()}
            data_file.writestr(str(activity_id), json.dumps(streams), zipfile.ZIP_LZMA)

    return jsonify(True)

@app.route('/extra_data')
def extra_data():
    polys = [lift_line_to_poly(v) for v in lifts.LIFTS.values()]
    with zipfile.ZipFile('strava_data.zip') as data_file:
        with data_file.open('activities.json') as fh:
            ids = json.loads(fh.read().decode('ascii'))

        with zipfile.ZipFile('extra_data.zip', 'w') as extra_file:
            for act_id in ids:
                print('Processing: ' + act_id)
                with data_file.open(str(act_id)) as fh:
                    streams = json.loads(fh.read().decode('ascii'))

                    points = [shapely.geometry.Point(*p) for p in streams['latlng']]
                    extra_data = {
                        'in_lift_poly' : [any((poly.contains(point) for poly in polys)) for point in points]
                    }
                    extra_file.writestr(str(act_id), json.dumps(extra_data), zipfile.ZIP_LZMA)

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


@app.route('/lift_activities')
def lift_activities():
    polys = [lift_line_to_poly(v) for v in lifts.LIFTS.values()]
    with zipfile.ZipFile('strava_data.zip') as data_file:
        with zipfile.ZipFile('extra_data.zip') as extra_file:
            with data_file.open('activities.json') as fh:
                ids = json.loads(fh.read().decode('ascii'))

            activity_data = {}
            for act_id in ids:
                with data_file.open(str(act_id)) as fh:
                    activity_data[act_id] = json.loads(fh.read().decode('ascii'))
                with extra_file.open(str(act_id)) as fh:
                    activity_data[act_id].update(json.loads(fh.read().decode('ascii')))

    for act_id, activity in activity_data.items():
        vals = zip_longest(activity['in_lift_poly'], activity['altitude'], activity['altitude'][1:])
        activity['on_lift'] = [ilp and (next_alt is None or next_alt >= alt) for ilp, alt, next_alt in vals]

    return jsonify(activity_data)

@app.route('/lift_polys')
def lift_polys():
    polys = {k:list(lift_line_to_poly(v).exterior.coords) for k, v in lifts.LIFTS.items()}
    return jsonify(polys)

def lift_line_to_poly(pts):
    # distance away from first point to lat long
    azi1 = Geodesic.WGS84.Inverse(pts[0][0], pts[0][1], pts[-1][0], pts[-1][1])['azi1']
    azi1 = (azi1 + 90) % 360
    point = Geodesic.WGS84.Direct(pts[0][0], pts[0][1], azi1, 20)

    # distance
    dist = math.sqrt((point['lat1']-point['lat2'])**2 + (point['lon1']-point['lon2'])**2)

    ls = shapely.geometry.LineString(pts)
    return ls.buffer(dist, cap_style=shapely.geometry.CAP_STYLE.flat)

if __name__ == "__main__":
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0', port=port)
