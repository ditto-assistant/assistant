"""Synthesizes speech from the input string of text or ssml.
Make sure to be working in a virtual environment.

Note: ssml must be well-formed according to:
    https://www.w3.org/TR/speech-synthesis/
"""
from google.cloud import texttospeech
import pygame
import os
from threading import Thread


class Speak:
    def __init__(self):
        self.running = False
        self.stopped = False

        # Instantiates a client
        self.client = texttospeech.TextToSpeechClient()

        # Build the voice request, select the language code ("en-US") and the ssml
        # voice gender ("neutral")
        self.voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.MALE,
            name="en-US-Wavenet-D",
        )

        # Select the type of audio file you want returned
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        pygame.mixer.init(channels=8)

    def gtts(self, prompt):
        Thread(target=self.speak(prompt), args=()).start()
        return self

    def stop(self):
        self.stopped = True

    def speak(self, prompt):
        self.running = True
        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=prompt)

        # Perform the text-to-speech request on the text input with the selected
        # voice parameters and audio file type
        response = self.client.synthesize_speech(
            input=synthesis_input, voice=self.voice, audio_config=self.audio_config
        )
        try:
            # The response's audio_content is binary.
            with open("output.mp3", "wb") as out:
                # Write the response to the output file.
                out.write(response.audio_content)

            pygame.mixer.music.load("output.mp3")
            channel = pygame.mixer.find_channel(True)
            pygame.mixer.music.set_volume(1.0)
            channel.play(pygame.mixer.Sound("output.mp3"))
            # while channel.get_busy() == True:
            #     if self.stopped:
            #         break
            #     continue
            # os.remove('output.mp3')
        except:
            print("GTTS error...")
        self.running = False
        self.stop = True
        return


if __name__ == "__main__":
    speak = Speak()
    speak.gtts("yo")
