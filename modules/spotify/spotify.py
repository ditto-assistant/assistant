"""
Spotify application build around the Spotify Web API.

refs:
1) https://developer.spotify.com/documentation/general/guides/authorization/
2) https://github.com/plamere/spotipy
"""

from lib2to3.pytree import Base
import os
import json
import random
import webbrowser

import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import spotipy.util as util


class Spotify():
    
    def __init__(self, path):

        self.path = path 
        self.load_configs(path)
        self.play_mode = self.config['play_mode']
        if self.play_mode == 'local':
            webbrowser.open('https://open.spotify.com/')
            self.auth = spotipy.SpotifyOAuth(
                redirect_uri='http://127.0.0.1:8124'
            )
            sp = spotipy.Spotify(auth_manager=self.auth)
            self.grab_active_id(sp)
        if not self.user_values['client-id'] == 'ID': # only run if configured correctly
            # pre-save user data
            self.get_user_details()
            pass
        else:
            print("\n[Configure client ID and Secret ID in spotify.json ...]")

        

    def load_configs(self, path):
        # first time set up (automated as much as possible)
        l = []
        for x in os.listdir(path):
            l.append(x)

        if not 'resources' in l:
            os.system('mkdir resources')

        l = []
        for x in os.listdir(path + '/resources'):
            l.append(x)
        if 'spotify.json' not in l:
            print('no spotify json found...')
            s = json.dumps({"client-id": "ID", "client-secret": "ID", "username": "ID"})
            with open(path +'/resources/spotify.json', 'w') as f:
                f.write(s)
            print('created spotify.json in resources/')
            print('please fill in client app IDs')
        
        with open(path +'/resources/spotify.json') as f:
            s = ""
            for x in f.readlines():
                s += x
        self.user_values = json.loads(s)

        try:
            with open(path +'/resources/config.json', 'r') as f:
                self.config = json.load(f)
        except:
            self.config = json.loads('{"play_mode": "local"}')
            with open('config.json', 'w') as f:
                f.write('{"play_mode": "local"}')

    def remote(self, command, *args):
        scope = "user-read-playback-state,user-modify-playback-state"
        username = self.user_values['username']
        self.token = util.prompt_for_user_token(
            username, scope=scope, 
            redirect_uri='http://127.0.0.1:8124'
        )
        self.auth = spotipy.SpotifyOAuth(
            redirect_uri='http://127.0.0.1:8124', username=username
        )
        sp = spotipy.Spotify(auth_manager=self.auth)
        try:
            if command == "resume":
                sp.start_playback(self.user_values['device-id'])
                print('\n[resume]')
            elif command == "pause":
                sp.pause_playback(self.user_values['device-id'])
                print('\n[pause]')
            elif command == "next":
                print('\n[next]')
                sp.next_track(self.user_values['device-id'])
            elif command == "previous":
                print('\n[previous]')
                sp.previous_track(self.user_values['device-id'])
            else:
                pass
        except:
            pass


    def play_spotify(self, uri):
        if 'playlist' in uri: context_mode = 'playlist'
        else: context_mode = 'song'
        scope = "user-read-playback-state,user-modify-playback-state"
        username = self.user_values['username']
        self.token = util.prompt_for_user_token(
            username, scope=scope, 
            redirect_uri='http://127.0.0.1:8124'
        )
        self.auth = spotipy.SpotifyOAuth(
            redirect_uri='http://127.0.0.1:8124', username=username
        )
        sp = spotipy.Spotify(auth_manager=self.auth)
        self.grab_active_id(sp) # update device-id with latest active player
        try:
            if context_mode=='playlist':
                for x in self.user_playlists:
                    if uri in x: # find playist 
                        offset_max = x[2] # grab tack count
                        shuffle_val = random.randint(0,offset_max)
                    else:
                        offset_max = 0
                sp.start_playback(context_uri=uri, offset={"position":shuffle_val}, device_id=self.user_values["device-id"])
            if context_mode=='song':
                sp.start_playback(uris=[uri], device_id=self.user_values["device-id"])
            return 1
        except:
            print("invalid uri: %s" % uri)
            return -1

    def get_uri_spotify(self, artist_song, song=None):
        
        if self.top_songs:
            for track in self.top_songs:
                track_song = track[0].lower()
                track_artist = track[1].lower()
                track_uri = track[2]
                if song==None and (artist_song.lower() in track_song or artist_song.lower() in track_artist):
                    print('found %s in top songs\n' % artist_song.title())
                    return track_uri
                if not song==None and artist_song.lower() in track_artist:
                    print('found %s by %s in top songs\n' % (song.title(), artist_song.title()))
                    return track_uri     

        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id = self.user_values["client-id"],
                client_secret = self.user_values["client-secret"],
            )
        )
        try:
            results = sp.search(q=artist_song, limit=30) # change limit for more results
            for idx, track in enumerate(results['tracks']['items']): 
                print(track)
                if song.lower() in track['name'].lower():
                    return track['external_urls']['spotify']
            return -1
        except:
            print('invalid search')
            return -1
    
    def get_user_details(self):
        scope = 'user-top-read, playlist-read-private, user-read-playback-state, user-modify-playback-state'
        username = self.user_values['username']
        self.token = util.prompt_for_user_token(
            username, scope=scope, 
            redirect_uri='http://127.0.0.1:8124'
        )
        self.auth = spotipy.SpotifyOAuth(
            redirect_uri='http://127.0.0.1:8124', username=username
        )
        sp = spotipy.Spotify(auth_manager=self.auth)

        # grab top songs
        ranges = ['short_term', 'medium_term', 'long_term']
        self.top_songs = []
        for sp_range in ranges:
            results = sp.current_user_top_tracks(time_range=sp_range, limit=75)
            for i, item in enumerate(results['items']):
                self.top_songs.append([item['name'], item['artists'][0]['name'], item['uri']]) # save ext url

        # grab top playlists
        user_id = sp.me()['id']
        self.user_playlists = []
        playlists = sp.current_user_playlists(limit=50)
        for playlist in playlists['items']:
            self.user_playlists.append([playlist['name'], playlist['uri'], playlist['tracks']['total']]) # save ext url

        # grab active or prev saved spotify player's device id
        self.grab_active_id(sp)
        

    def grab_active_id(self, sp):
        '''grab active or prev saved spotify player's device id
        \nparam:
        sp: spotipy.Spotify() object
        '''
        # grab device-id
        self.devices = sp.devices()
        if not self.devices['devices'] == []:
            device_id = self.devices['devices'][0]['id'] # grab id
            self.user_values['device-id'] = device_id
            with open(self.path+'/resources/spotify.json', 'w') as f: # store to json
                json.dump(self.user_values, f)

if __name__ == "__main__":
    spotify_app = Spotify(os.getcwd())

    # uri = spotify_app.get_uri_spotify("the mars volta")
    # spotify_app.play_spotify(uri)

    # spotify_app.next_song()

    # spotify_app.play_spotify('spotify:playlist:2PT7ZGFsCmFpRUBrzXFZGT')
