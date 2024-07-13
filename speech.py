"""
Uses Google's Speech-to-Text API to handle speech input from Mic and output text.

author: Omar Barazanji

refrences:
1) https://cloud.google.com/speech-to-text/docs/libraries#client-libraries-install-python
2) https://www.thepythoncode.com/article/play-and-record-audio-sound-in-python

notes:
1) run the followng to setup:
    $env:GOOGLE_APPLICATION_CREDENTIALS="path_to_google_api_json"
"""

# google cloud
import sqlite3
import time
from google.cloud import speech
from modules.google_stt.google_transcript import Google
import os
import sys
from threading import Timer

# local vosk
from modules.vosk_model.activation import Activation
from modules.vosk_model.stt import STT

# from vosk import Model, KaldiRecognizer, SetLogLevel

from modules.ditto_activation.main import HeyDittoNet

# from ditto_requests import DittoRequests

# suppress Vosk logger
# SetLogLevel(-1)

# pyaudio alternative for real-time stream (supported by Vosk)
import sounddevice as sd

# used to send keypress event (keeps display on)
try:
    import pyautogui

    pyautogui.FAILSAFE = False
    headless = False
except:
    headless = True

import pyaudio
import wave
import io


class Speech:
    def __init__(self, offline_mode=False, mic="", no_mic_mode=False):
        self.offline_mode = offline_mode
        self.mic = mic
        self.no_mic_mode = no_mic_mode
        self.recording = False
        self.text = ""
        self.activation = Activation("ditto")
        self.google_instance = Google(mic=mic)
        self.heyditto = HeyDittoNet(
            model_type="HeyDittoNet-v2", path="modules/ditto_activation/", tflite=True
        )
        self.vosk_model_dir = "modules/vosk_model/model"
        self.fname = "modules/vosk_model/command.wav"
        self.skip_wake = False

        self.wake = 1

        self.inject = (
            False  # used for skipping STT by using GUI's prompt in activation loop
        )
        self.from_gui = False  # used in ditto.py to handle loop differently

        self.gesture_activation = False
        self.reset_conversation = False

        self.listening_indicator = None

    def record_audio(self, activation_mode=False):
        self.recording = True
        try:
            if activation_mode and self.skip_wake == False:
                wake = self.heyditto.listen_for_name(no_mic_mode=self.no_mic_mode)

                if self.heyditto.activation_requests.inject_prompt:
                    self.inject = True
                    self.heyditto.activation_requests.inject_prompt = False
                    self.from_gui = True  # turn off activation noise

                if self.heyditto.activation_requests.gesture_activation:
                    self.gesture_activation = True
                    self.gesture = self.heyditto.activation_requests.gesture

                if self.heyditto.activation_requests.reset_conversation:
                    self.reset_conversation = True
                    self.from_gui = True  # turn off activation noise

                if wake:
                    self.activation.activate = True
                    self.recording = False
                    if not headless:
                        pyautogui.press("ctrl")  # turns display on if asleep
                        self.listening_indicator = "listening..."

            else:
                self.skip_wake = False  # set back to false

                if self.gesture_activation:
                    self.gesture_activation = False  # set back to false
                    self.from_gui = True  # use from gui ditto loop to avoid accidental conversation loop
                    if self.gesture == "palm":
                        self.text = self.google_instance.grab_prompt()
                    else:
                        self.text = f"GestureNet: {self.gesture}"

                if self.reset_conversation:
                    self.reset_conversation = False  # set back to false
                    self.from_gui = True  # use from gui ditto loop to avoid accidental conversation loop
                    self.text = f"resetConversation"

                elif self.inject:
                    self.inject = False
                    # self.text = self.pico.prompt
                    self.text = self.heyditto.activation_requests.prompt
                    # self.pico.prompt = ""
                    self.heyditto.activation_requests.prompt = ""
                    self.from_gui = True

                else:
                    if not self.offline_mode:
                        self.text = self.google_instance.grab_prompt()
                    else:
                        self.speech_to_text = STT(os.getcwd())
                        self.speech_to_text.stt()
                        self.text = self.speech_to_text.text

                # self.activation kind of unneccesary...
                self.activation.text = self.text
                self.activation.check_input(activation_mode)
                if self.activation.activate:
                    self.recording = False
        except BaseException as e:
            print(e)
            self.recording = False

        # not used (leaving hooks for other purposes)
        def record_pyaudio(self, max_len_seconds=10):
            chunk = 1024
            fmt = pyaudio.paInt16
            chan = 1
            self.rate = 16000

            p = pyaudio.PyAudio()

            print("recording...")

            self.recording = True
            stream = p.open(
                format=fmt,
                channels=chan,
                rate=self.rate,
                input=self.recording,
                frames_per_buffer=chunk,
            )

            frames = []

            for x in range(0, int(self.rate / chunk * max_len_seconds)):
                data = stream.read(chunk)
                frames.append(data)

                if not self.recording:
                    break

            stream.stop_stream()
            stream.close()
            p.terminate()

            print("done.")

            wf = wave.open(self.fname, "wb")
            wf.setnchannels(chan)
            wf.setsampwidth(p.get_sample_size(fmt))
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(frames))
            wf.close()

        # not used (leaving hooks for other purposes)
        def process_audio_google(self):
            with io.open(self.fname, "rb") as audio_file:
                content = audio_file.read()
            client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.rate,
                language_code="en-US",
            )
            response = client.recognize(config=config, audio=audio)

            for result in response.results:
                print("\n")
                print("Transcript: {}".format(result.alternatives[0].transcript))
                self.text = "{}".format(result.alternatives[0].transcript)

    # not used (leaving hooks for other purposes)
    def process_audio_vosk(self):
        self.activation.input(self.fname, self.vosk_model_dir)
        self.text = self.activation.text


if __name__ == "__main__":
    s = Speech()
