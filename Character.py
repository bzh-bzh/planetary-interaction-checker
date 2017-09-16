import http.server
import urllib.parse
import webbrowser
import datetime
from pg import DB
from oauthlib.oauth2 import MismatchingStateError
from requests_oauthlib import OAuth2Session

import PlanetaryColony

return_url = ''


class Character:
    class ParameterParseHtTTPRequestHandler(http.server.BaseHTTPRequestHandler):
        http.server.BaseHTTPRequestHandler.close_connection = True

        # noinspection PyPep8Naming
        def do_GET(self):
            global return_url
            return_url = self.path
            self.send_response(200, "Received.")
            self.end_headers()
            return

        def log_message(self, log_format, *args):
            return

    # TODO: If this is gonna be a webapp, we have to make it stateless with memcache and maybe nosql.
    # noinspection PyArgumentList
    planetary_interaction_db = DB(dbname='planetary_interaction_checker')

    # TODO: hide the client secret
    __client_id = ''
    __client_secret = ''
    __token_url = 'https://login.eveonline.com/oauth/token'
    __redirect_uri = 'http://localhost:7192'
    __esi_base_url = 'https://esi.tech.ccp.is/latest/'

    def __init__(self, character_id=None):
        if character_id is None:
            self.insert_new_character()
            self.upsert_into_database()
        else:
            character_id_list = [int(i[0]) for i in
                                 self.planetary_interaction_db.query('select character_id from characters').getresult()]
            if character_id not in character_id_list:
                raise ValueError

            # load it from the db.
            character_query = self.planetary_interaction_db.get('characters', character_id)

            self.character_id = character_id
            self.character_name = character_query['character_name']
            self.scopes = character_query['scopes']
            # this token only exists for the oauth2 session. when the token is refreshed, this value isn't updated.
            self.__initial_token = {
                'access_token': character_query['access_token'],
                'token_type': character_query['token_type'],
                # convert it back from datetime to unix timestamp. why does psql have to be so backwards...
                'expires_at': character_query['token_expiry'].replace(tzinfo=datetime.timezone.utc).timestamp(),
                'expires_in': (character_query['token_expiry'] - datetime.datetime.utcnow()).total_seconds(),
                'refresh_token': character_query['refresh_token']
            }
            self.expires_at = character_query['token_expiry']

        # create a new oauth2 session
        refresh_auth_kwargs = {
            'client_id': self.__client_id,
            'client_secret': self.__client_secret
        }
        self.oauth2session = OAuth2Session(client_id=self.__client_id, token=self.__initial_token,
                                           auto_refresh_url=self.__token_url, auto_refresh_kwargs=refresh_auth_kwargs,
                                           token_updater=self.upsert_into_database)

        # get a list of planetary colonies
        planet_request = self.auto_refresh_get(
            self.__esi_base_url + 'characters/' + str(self.character_id) + '/planets/')

        self.colony_list = []

        for planet in planet_request.json():
            # get the planet's layout(pins, routes, links, details of all such)
            planet_layout_request = self.auto_refresh_get(self.__esi_base_url + 'characters/' + str(self.character_id) +
                                                          '/planets/' + str(planet['planet_id']) + '/')
            planet['colony_layout'] = planet_layout_request.json()

            # get the planet's name
            planet_name_request = self.auto_refresh_get(self.__esi_base_url + 'universe/planets/' +
                                                        str(planet['planet_id']) + '/')
            planet['name'] = planet_name_request.json()['name']

            self.colony_list.append(PlanetaryColony.PlanetaryColony(planet))

    def upsert_into_database(self, token=None):
        if token is None:
            token = self.__initial_token
        new_values = {
            'character_id': self.character_id,
            'character_name': self.character_name,
            'scopes': self.scopes,
            'access_token': token['access_token'],
            'token_type': token['token_type'],
            # this is in the form of a unix timestamp, but we convert it to datetime before sticking it in the DB.
            'token_expiry': datetime.datetime.utcfromtimestamp(token['expires_at']),
            'refresh_token': token['refresh_token']
        }
        self.planetary_interaction_db.upsert('characters', new_values)

    def update_token_expires_in(self):
        updated_token = self.oauth2session.token
        updated_token['expires_in'] = \
            (datetime.datetime.utcfromtimestamp(updated_token['expires_at'])
             - datetime.datetime.utcnow()).total_seconds()
        self.oauth2session.token = updated_token

    def auto_refresh_get(self, url):
        # TODO: Handle the error of having auth revoked, and gracefully request a new login from the user.
        self.update_token_expires_in()
        request = self.oauth2session.get(url)

        if request.status_code is not 200:
            raise ConnectionError
        return request

    def insert_new_character(self):
        scopes = ['esi-planets.manage_planets.v1']

        oauth2_token_session = OAuth2Session(client_id=self.__client_id, redirect_uri=self.__redirect_uri, scope=scopes)

        authorization_url, state = oauth2_token_session.authorization_url('https://login.eveonline.com/oauth/authorize')

        parameter_handler = self.ParameterParseHtTTPRequestHandler
        http_server = http.server.HTTPServer(('', 7192), parameter_handler)
        webbrowser.open_new(authorization_url)
        http_server.handle_request()
        http_server.server_close()

        global return_url
        callback_parameters = urllib.parse.parse_qsl(urllib.parse.urlparse(return_url).query, strict_parsing=True)

        # check that we received all the right parameters in return.
        callback_parameter_headers = [h[0] for h in callback_parameters]
        if callback_parameter_headers[0] != 'code' or callback_parameter_headers[1] != 'state':
            raise ValueError

        callback_parameter_code = callback_parameters[0][1]
        callback_parameter_state = callback_parameters[1][1]

        if callback_parameter_state != state:
            raise MismatchingStateError

        # this token only exists for the oauth2 session. when the token is refreshed, this value isn't updated.
        self.__initial_token = oauth2_token_session.fetch_token(token_url=self.__token_url,
                                                                client_secret=self.__client_secret,
                                                                code=callback_parameter_code)

        character_info_request = oauth2_token_session.get('https://login.eveonline.com/oauth/verify')

        if character_info_request.status_code is not 200:
            raise ConnectionError

        self.character_id = character_info_request.json()['CharacterID']
        self.character_name = character_info_request.json()['CharacterName']
        self.scopes = scopes
