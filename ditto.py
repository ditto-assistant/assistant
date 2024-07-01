"""
Ditto Assistant main logic.

author: Omar Barazanji
"""

# handles text to speech
# import pyttsx3

# other imports
import sqlite3
import os
import time
import pygame
import requests
from speech import Speech
from command_handlers.command import Command
from modules.google_tts.speak import Speak

# from modules.security_camera.security_cam import SecurityCam
from modules.ditto_vision.eyes import Eyes
import json
import platform
from dotenv import load_dotenv
from config import AppConfig
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


# used to send keypress event (keeps display on)
try:
    import pyautogui

    pyautogui.FAILSAFE = False
    headless = False
except:
    headless = True
    print("booting headless...")


UNIX = False
if platform.system() == "Linux":
    UNIX = True

NO_MIC_MODE = False
try:
    pygame.mixer.init(channels=8)
except:
    log.info("No audio device detected... Continuing in no-mic mode.")
    NO_MIC_MODE = True

OFFLINE_MODE = False

load_dotenv(override=True)


class Assistant:
    def __init__(self, offline_mode=OFFLINE_MODE):
        log.info("[Booting...]")
        self.update_status_db("booting")
        self.config = AppConfig()
        self.speech = Speech(
            offline_mode=offline_mode,
            mic=self.config.microphone,
            no_mic_mode=NO_MIC_MODE,
        )
        self.nlp_base_url: str = self.config.base_url()
        self.vision_base_url: str = self.config.base_url_vision()
        self.ditto_eyes = Eyes(
            vision_base_url=self.vision_base_url,
            eyes_on=self.speech.heyditto.activation_requests.mic_on,
        )
        self.check_if_vision_server_running()
        self.volume = int(self.config.volume)  # percent
        # self.security_camera = SecurityCam(os.getcwd())

        self.command = Command(os.getcwd(), offline_mode, no_mic_mode=NO_MIC_MODE)
        self.speech_engine = ""
        self.google = None
        if not NO_MIC_MODE:
            self.google = Speak()
        # self.speech_engine.setProperty('voice', 'english')
        # self.speech_engine.setProperty('rate', 190)
        self.prompt = ""
        self.reply = ""
        self.activation_mode = True  # If true then idle and listening for name

        self.reset_conversation = False  # used to skip writing reset commands to DB
        self.toggle_eyes = False  # used to skip writing toggle eyes commands to DB

        self.skip_name = False  # used to skip name (conversation app)

        self.retries = 0
        # will go to false after 5 seconds of inactivity (idle)
        self.update_status_db("on")

    def load_config(self):
        config = AppConfig()

    def check_if_vision_server_running(self):
        try:
            url = f"{self.vision_base_url}/status"
            requests.get(url)
            ret = self.ditto_eyes.start()
            if ret == 1:
                log.info("[Eyes started...]")
            return True
        except BaseException as e:
            log.info("Continuing without vision server... error below:")
            log.error(e)
            return False

    def reset_loop(self):
        """
        Resets the command loop to idle.
        """
        self.activation_mode = True  # go back to idle...
        self.speech.text = ""
        self.prompt = ""
        self.speech.from_gui = False

    def play_sound(self, sound="off"):
        print(f"Gui Mode {self.speech.from_gui}")
        if self.speech.from_gui:
            return
        elif self.reset_conversation:
            return

        def play_sound_channel():
            channel = pygame.mixer.find_channel()
            pygame.mixer.music.load(f"resources/sounds/ditto-{sound}.mp3")
            channel.set_volume(self.volume / 100)
            channel.play(pygame.mixer.Sound(f"resources/sounds/ditto-{sound}.mp3"))

        playing_soundscapes = getattr(
            self.command.soundscapes_handler.soundscapes, "playing", False
        )
        playing_music = getattr(
            self.command.spotify_handler.player, "playing_music", False
        )
        if playing_soundscapes or playing_music:
            if sound == "on":
                pygame.mixer.music.set_volume(int(self.volume * 0.5) / 100)
                if not self.command.spotify_handler.player == []:
                    if self.command.spotify_handler.player.playing_music:
                        self.command.spotify_handler.player.remote(
                            "volume", int(self.volume * 0.5)
                        )
            if sound == "off":
                pygame.mixer.music.set_volume(self.volume / 100)
                if self.command.spotify_handler.player.playing_music:
                    self.command.spotify_handler.player.remote("volume", self.volume)
        play_sound_channel()

    def skip_wake(self):
        """
        For applications that require looping, we can skip wake.
        """
        self.speech.activation.activate = (
            True  # skip wake-up sequence (name is already called)
        )
        self.speech.skip_wake = True

    def prompt_intent(self, prompt):
        base_url = f"{self.nlp_base_url}/intent"
        response = requests.post(base_url, params={"prompt": prompt})
        return response.content.decode()

    def conversation_app(self, action=None):
        def conversation_flow():
            self.reply = self.command.conversation_handler.handle_response(
                self.prompt,
                self.ditto_eyes.face_name if self.ditto_eyes.face_name else "none",
            )

            if self.reply == "":
                self.reply = "..."

            if "-LLM Tools: Code Compiler-" in self.reply:  # avoid speaking code (lol)
                self.tts("[Code Compiled with LLM Tools.]")
            else:
                self.tts(self.reply)

            if not self.speech.from_gui:
                # self.skip_wake()
                self.reset_loop()
            else:
                self.reset_loop()

        if action == "exit":
            if not self.speech.from_gui:
                self.reply = "[Exiting Conversation Loop]"
                self.reset_loop()
                self.play_sound("off")
            else:
                conversation_flow()
        else:
            conversation_flow()

    def send_command(self):  # application logic
        # grab user's prompt from speech module
        self.prompt = self.speech.text

        # log the user's prompt
        # print('writing prompt to db...')
        if not self.speech.from_gui:
            self.write_prompt_to_db()
        if "GestureNet" in self.prompt:
            cat = "gesture"
            sub_cat = "none"
            action = "none"
            gesture = self.speech.gesture
        elif "resetConversation" in self.prompt:
            cat = "reset"
            sub_cat = "none"
            action = "none"
        elif "toggleEyes" in self.prompt:
            cat = "toggleEyes"
            sub_cat = "none"
            action = "none"
        else:
            # get intent from offline npl module
            self.offline_response = json.loads(self.prompt_intent(self.prompt))
            cat = self.offline_response["category"]
            sub_cat = self.offline_response["sub_category"]
            action = self.offline_response["action"]

            if (
                "exit" in action
                and self.command.soundscapes_handler.soundscapes.playing
            ):
                cat = "soundscapes"
                sub_cat = "none"
                action = "exit"

        print(cat, sub_cat, action)

        # send prompt to application / category
        if cat == "lights":
            self.reply = self.command.light_handler.handle_response(
                self.prompt, self.tts
            ).reply
            self.reset_loop()

        elif cat == "spotify":
            try:
                self.reply = self.command.spotify_handler.handle_response(self.prompt)
                self.tts(self.reply)
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "music":
            try:
                self.command.spotify_handler.player.remote(
                    self.offline_response["action"]
                )
                if self.speech.from_gui:
                    self.reply = "[Done.]"
                self.reset_loop()
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "timer":
            try:
                self.reply = self.command.timer_handler.handle_response(self.prompt)
                self.tts(self.reply)
                self.reset_loop()
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "gesture":
            if gesture == "like":
                # self.reply = f'[GestureNet: {gesture}]'
                self.prompt = "turn on the lights"
                self.reply = self.command.light_handler.handle_response(self.prompt)
                # pyautogui.press('right')
            elif gesture == "dislike":
                # self.reply = f'[GestureNet: {gesture}]'
                # pyautogui.press('left')
                self.prompt = "set the lights to sparkle"
                self.reply = self.command.light_handler.handle_response(self.prompt)
            self.tts(self.reply)
            self.reset_loop()

        elif cat == "toggleEyes":
            self.ditto_eyes.toggle()
            if self.ditto_eyes.eyes_on:
                log.info("[Eyes started...]")
            else:
                log.info("[Eyes stopped...]")
            self.reset_loop()
            self.toggle_eyes = True  # skip writing to db

        elif cat == "security":
            if not headless:
                self.reply = f"[Opening {action} camera.]"
                # self.security_camera.open_cam(action)
                self.tts(self.reply)
                self.reset_loop()
            else:
                self.reply = "[Exiting Conversation Loop]"
                self.reset_loop()
                self.play_sound("off")

        elif cat == "weather":
            ## TODO: remove because conversation app handles weather via LLM google tool
            # try:
            #     self.reply = self.command.weather_handler.handle_response(
            #         sub_cat, action
            #     )
            #     self.tts(self.reply)
            #     self.reset_loop()
            # except BaseException as e:
            #     print(e)
            self.conversation_app()

        elif cat == "soundscapes":
            try:
                self.reply = self.command.soundscapes_handler.handle_response(
                    sub_cat, action
                )
                # self.tts(self.reply)
                self.reset_loop()
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "wolfram":
            try:
                self.reply = self.command.wolfram_handler.handle_response(
                    sub_cat, self.prompt
                )
                print(f"\nWolfram Reply len: `{len(self.reply)}`\n")
                if len(self.reply) > 0 and len(self.reply) < 99:
                    self.tts(self.reply)
                    self.reset_loop()
                else:
                    self.conversation_app()
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "vacuum":
            try:
                self.reply = self.command.iot_remote_handler.handle_response(
                    action, device_name="vacuum"
                )
                self.tts(self.reply)
                self.reset_loop()
            except BaseException as e:
                self.reply = "[Error communicating with Vacuum]"
                self.reset_loop()

        elif cat == "volume":
            try:
                volume = self.command.volume_handler.handle_response(self.prompt)
                self.volume = volume
                self.reply = f"[Volume set to {volume}.]"
                self.command.spotify_handler.player.remote(cat, volume)
                self.command.soundscapes_handler.soundscapes.adjust_volume(volume)
                print(self.reply)
                # self.tts(self.reply)
                self.reset_loop()
            except BaseException as e:
                print(e)
                self.conversation_app()

        elif cat == "vision":
            if self.ditto_eyes.running:
                try:
                    url = f"{self.nlp_base_url}/users/{self.config.user_id}/image_rag"
                    image = self.ditto_eyes.latest_frame
                    if action == "caption":
                        params = {"prompt": self.prompt, "mode": "caption"}
                        response = requests.post(
                            url, files={"image": image}, params=params
                        )
                        self.reply = json.loads(response.content.decode())["response"]
                        self.tts(self.reply)
                        self.reset_loop()
                    elif action == "qa":
                        params = {"prompt": self.prompt, "mode": "qa"}
                        response = requests.post(
                            url, files={"image": image}, params=params
                        )
                        self.reply = json.loads(response.content.decode())["response"]
                        self.tts(self.reply)
                        self.reset_loop()
                    elif action == "name":
                        if self.ditto_eyes.person_in_frame == "yes":
                            # ner name
                            response = requests.post(
                                f"{self.nlp_base_url}/ner/name",
                                params={"prompt": self.prompt},
                            )
                            name = json.loads(response.content.decode())["name"]
                            # save name and image using vision server
                            requests.post(
                                f"{self.vision_base_url}/save_face",
                                params={"face_name": name},
                                files={"image": image},
                            )
                            self.conversation_app()
                            self.tts(self.reply)
                            self.reset_loop()
                    else:
                        params = {"prompt": self.prompt, "mode": "caption"}
                        response = requests.post(
                            url, files={"image": image}, params=params
                        )
                        self.reply = json.loads(response.content.decode())["response"]
                        self.tts(self.reply)
                        self.reset_loop()

                except BaseException as e:
                    print("Error in vision handler")
                    print(e)
                    self.conversation_app()
            else:
                self.conversation_app()

        elif cat == "conv":  # send to conversation handler
            log.debug("Calling conversation app; Q: %s" % self.prompt)
            self.conversation_app(action)

        elif cat == "reset":
            self.reply = "[Resetting Conversation...]"
            self.command.conversation_handler.reset_conversation()
            self.reset_loop()

        # if not self.speech.from_gui:
        self.write_response_to_db()  # log self.reply to nlp server db

    def write_response_to_db(self):
        if not self.reply:
            self.reply = "[empty]"
        if self.reset_conversation:
            self.reset_conversation = False  # set back to False
            self.reply = ""
            return
        if self.toggle_eyes == True:
            self.toggle_eyes = False  # set back to False
            self.reply = ""
            return
        try:
            requests.post(
                f"{self.nlp_base_url}/users/{self.config.user_id}/write_response?response={self.reply}",
                timeout=30,
            )
        except BaseException as e:
            print(e)
        self.reply = ""  # reset for next loop

    def write_prompt_to_db(self):
        if self.reset_conversation:
            self.reply = ""
            return
        if self.toggle_eyes:
            return
        try:
            requests.post(
                f"{self.nlp_base_url}/users/{self.config.user_id}/write_prompt?prompt={self.prompt}",
                timeout=30,
            )
        except BaseException as e:
            print(e)

    def update_status_db(self, status):
        SQL = sqlite3.connect("ditto.db")
        cur = SQL.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS status(status VARCHAR)")
        SQL.commit()
        status_arr = cur.execute("SELECT * FROM status").fetchall()
        if len(status_arr) > 3:
            cur.execute("DELETE FROM status")
            SQL.commit()
        cur.execute("INSERT INTO status VALUES('%s')" % status)
        SQL.commit()
        SQL.close()

    def activation_sequence(self):
        self.activation_mode = True
        # record audio and listen for name
        log.info("Waitng for prompt...")
        self.speech.record_audio(activation_mode=self.activation_mode)
        log.info("Done recording audio...")
        if self.speech.activation.activate:  # name has been spoken
            if self.speech.reset_conversation:
                self.reset_conversation = True
            self.play_sound("on")
            self.update_status_db(self.speech.listening_indicator)
            self.speaker_timer = 0  # reset speaker + mic timer

            self.speech.activation.activate = False
            # set listening indicator to None
            self.speech.listening_indicator = None
            self.speech.text = ""
            self.speech.activation.text = ""

            self.activation_mode = False

            # record audio and listen for command
            self.speech.record_audio(activation_mode=self.activation_mode)

            # set status back to on
            self.update_status_db("on")

            # command has been spoken (app on enter section)
            log.info("Q: %s\n" % self.speech.activation.text)
            self.speech.activation.activate = False
            self.speech.activation.text = ""

            # enter application handler ## (main loop)
            # while not self.activation_mode:
            try:
                self.send_command()

            except BaseException as e:
                err_msg = f"[Unexpected Error: {e}]"
                log.error(err_msg)
                self.reply = err_msg
                self.tts("Unexpected Error... Please try again!")
                self.reset_loop()
        else:
            log.info("No name spoken...")

    def tts(self, reply):
        if (
            not self.speech.from_gui
        ):  # only read reply aloud if command / prompt was spoken by user
            try:
                if UNIX:
                    os.system("amixer -q set Master " + str(self.volume) + "%")
                # os.system('pico2wave -w reply.wav "%s" && aplay -q reply.wav' % prompt.strip("[]"))
                if not self.speech.offline_mode:
                    soundscapes = self.command.soundscapes_handler.soundscapes
                    if soundscapes.playing:
                        speaker = self.google.gtts(reply)
                        while speaker.running:
                            time.sleep(0.2)
                            continue
                        soundscapes.play_sound(soundscapes.currently_playing)
                    else:
                        self.google.gtts(reply)
                else:
                    self.speech_engine.say(reply)
                    self.speech_engine.runAndWait()
            except BaseException as e:
                print(e)


if __name__ == "__main__":
    assistant = Assistant()
    while True:
        assistant.activation_sequence()
