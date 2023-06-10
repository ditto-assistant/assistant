from pygame import mixer
import os


class SoundScapes:
    '''
    Module for handling loopable soundscapes such as white noise, binaural beats, and any other custom sounds.
    '''

    def __init__(self, path=''):
        self.path = path
        self.__load_resources()

    def __load_resources(self) -> list:
        sounds = []
        self.playing = False
        self.currently_playing = ''
        self.channel = None
        try:
            sounds = os.listdir(self.path+'sounds')
        except BaseException as e:
            print('Error loading SoundScapes resources...')
            print(e)
        self.sounds = sounds
        return sounds

    def play_sound(self, sound: str):
        if 'noise' or 'white noise' in sound:
            print('Loading and playing white noise (10 hours)')

            self.playing = True
            self.currently_playing = 'white noise'
            self.channel = mixer.find_channel(True)
            mixer.music.load(self.path+'sounds/white_noise.mp3')
            mixer.music.set_volume(1.0)
            mixer.music.play()

    def stop_sound(self):
        mixer.music.stop()
        self.playing = False
        self.currently_playing = ''


if __name__ == '__main__':
    soundscapes = SoundScapes()
    # soundscapes.play_sound('white noise')