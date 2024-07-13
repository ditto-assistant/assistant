import shutil
import os
import time
from PIL import Image
import base64
from io import BytesIO
import logging
import requests
import threading
import json
import sys

# holds strings of entities to check for in images
from entities import entities as ENTITIES
from home_assistant import HomeAssistant

log = logging.getLogger("ditto_security_vision")
logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv

load_dotenv()

import cv2
import os
from collections import deque

whitelisted_files = []


class IPCamera:
    def __init__(self):
        self.camera1_url = os.getenv("ip_camera_1", None)
        self.camera2_url = os.getenv("ip_camera_2", None)
        self.buffer_size = 20  # 20-second buffer
        self.frame_buffer = deque(
            maxlen=self.buffer_size * 30
        )  # Assuming 30 frames per second
        self.stop_buffer_loop = False

    def save_buffer(self, output_filename="output.mp4"):
        # Write the frames in the buffer to a video file
        height, width, _ = self.entitiy_detected_buffer[0].shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_filename, fourcc, 30, (width, height))

        for frame in self.entitiy_detected_buffer:
            out.write(frame)

        out.release()

    def stop_buffer(self):
        self.stop_buffer_loop = True

    def start_buffer(self):
        # start a thread that runs start_buffer_loop
        threading.Thread(target=self.start_buffer_loop).start()

    def start_buffer_loop(self):
        # Capture video from the IP cameras
        cap1 = cv2.VideoCapture(self.camera1_url)
        cap2 = cv2.VideoCapture(self.camera2_url)

        while True:
            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()

            if not ret1 or not ret2:
                break  # Break the loop if either camera is not working

            self.frame_buffer.append(frame1)
            self.frame_buffer.append(frame2)

            # Display the frames (optional)
            cv2.imshow("Camera 1", frame1)
            cv2.imshow("Camera 2", frame2)

            # Break the loop if 'q' key is pressed
            if (cv2.waitKey(1) & 0xFF == ord("q")) or self.stop_buffer_loop:
                break

        # Release video capture objects
        cap1.release()
        cap2.release()
        cv2.destroyAllWindows()

    def add_to_buffer_entity_detected(self, output_filename="output.mp4"):
        # start a thread that runs add_to_buffer_entity_detected
        ## make a folder 'entities_detected' and save the video as 'entity.mp4' if this file already exists, add a number to the end of the file name that is not already taken (entity1.mp4, entity2.mp4, etc) incrementing the number

        # copy buffer
        buffer_copy = self.frame_buffer.copy()

        # make a new buffer
        buffer = deque(maxlen=self.buffer_size * 30)  # Assuming 30 frames per second

        # Capture video from the IP cameras
        cap1 = cv2.VideoCapture(self.camera1_url)
        cap2 = cv2.VideoCapture(self.camera2_url)

        # capture another 20 seconds of video and save it to a file
        for i in range(self.buffer_size * 30):
            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()

            if not ret1 or not ret2:
                break

            buffer.append(frame1)
            buffer.append(frame2)

            # Display the frames (optional)
            cv2.imshow("Camera 1", frame1)
            cv2.imshow("Camera 2", frame2)

            # Break the loop if 'q' key is pressed
            if (cv2.waitKey(1) & 0xFF == ord("q")) or self.stop_buffer_loop:
                break

        # Release video capture objects
        cap1.release()
        cap2.release()
        cv2.destroyAllWindows()

        # concatenate the two buffers
        self.entitiy_detected_buffer = buffer_copy + buffer

        # save the buffer to a file
        self.save_buffer(output_filename=output_filename)

    def add_to_buffer(self):
        # start a thread that runs add_to_buffer_entity_detected
        ## make a folder 'entities_detected' and save the video as 'entity.mp4' if this file already exists, add a number to the end of the file name that is not already taken (entity1.mp4, entity2.mp4, etc) incrementing the number

        if not os.path.exists("entities_detected"):
            os.mkdir("entities_detected")

        if not os.path.exists("entities_detected/entity.mp4"):
            self.add_to_buffer_entity_detected()
        else:
            entity_videos = os.listdir("entities_detected")
            last_entity_video = entity_videos[-1]
            last_entity_video_number = int(
                last_entity_video.split(".")[0].split("entity")[1]
            )
            new_entity_video_number = last_entity_video_number + 1
            self.add_to_buffer_entity_detected(
                output_filename=f"entities_detected/entity{new_entity_video_number}.mp4"
            )

        log.info(
            f"Starting thread to save video buffer to entities_detected/entity{new_entity_video_number}.mp4"
        )

        threading.Thread(
            target=self.add_to_buffer_entity_detected(
                output_filename=f"entities_detected/entity{new_entity_video_number}.mp4"
            )
        ).start()


class DittoSecurityVision:
    def __init__(self, path="") -> None:
        self.path = path
        self.init_cameras()
        self.init_vision_server_endpoint()
        self.home_assistant = HomeAssistant()

    def init_cameras(self):
        if not os.path.exists(self.path + "ftp/"):
            os.mkdir(self.path + "ftp/")
        self.cameras = []
        for camera in os.listdir(self.path + "ftp/"):
            if "camera" in camera:
                self.cameras.append(camera)
        if self.cameras == []:
            log.info("No cameras found")
            exit()

    def init_vision_server_endpoint(self):
        self.vision_server_ip = os.getenv("vision_server_ip", "localhost")
        self.vision_server_port = int(os.getenv("vision_server_port", 52032))
        self.vision_server_protocol = os.getenv("vision_server_protocol", "http")
        self.vision_server_url = f"{self.vision_server_protocol}://{self.vision_server_ip}:{self.vision_server_port}"

    def qa_for_entities(self, image):
        def get_qa(prompt, image):
            try:
                url = f"{self.vision_server_url}/qa"
                files = {"image": image}
                params = {"prompt": prompt}
                raw_response = requests.post(url, files=files, params=params)
                response = json.loads(raw_response.content.decode())["response"]
                return response
            except BaseException as e:
                log.error(e)
                return None

        entities = []
        for entity_prompt, entity_name in ENTITIES:
            qa_res = get_qa(prompt=entity_prompt, image=image)
            if "yes" in str(qa_res).lower():
                entities.append(entity_name)
            else:
                continue
        return entities

    def reset_camera_folders(self):
        log.info("Resetting camera folders...")
        for camera in self.cameras:
            # delete each folder in the camera folder
            for folder in os.listdir(self.path + "ftp/" + camera):
                # iterate through each file in the folder and delete it
                for file in os.listdir(
                    self.path + "ftp/" + camera + "/" + folder + "/images/"
                ):
                    try:
                        os.remove(
                            self.path
                            + "ftp/"
                            + camera
                            + "/"
                            + folder
                            + "/images/"
                            + file
                        )
                    except BaseException as e:
                        bad_file = (
                            self.path
                            + "ftp/"
                            + camera
                            + "/"
                            + folder
                            + "/images/"
                            + file
                        )
                        log.error(f"Could not delete file: {bad_file}")
                        return bad_file
        log.info("Done.")
        return None

    def check_ftp_for_entities(self, max_retries=10):
        log.info("Waiting for images...")
        retries = 0

        global whitelisted_files

        # IP Camera object to save video buffer
        ip_camera = IPCamera()

        # start the buffer in a separate thread
        # TODO: add try / except to IPCamera.start_buffer() and handle errors before uncommenting
        # ip_camera.start_buffer()

        while True and retries < max_retries:
            time.sleep(1)
            try:
                if not os.path.exists("ftp/marked_for_deletion/"):
                    os.mkdir("ftp/marked_for_deletion/")
                if not os.path.exists("ftp/entities/"):
                    os.mkdir("ftp/entities/")
                for entity in ENTITIES:
                    if not os.path.exists("ftp/entities/" + entity[1] + "/"):
                        os.mkdir("ftp/entities/" + entity[1] + "/")
                for camera in self.cameras:
                    for camera_day in os.listdir(self.path + "ftp/" + camera + "/"):
                        # get current YMD
                        camera_day_path = (
                            self.path + "ftp/" + camera + "/" + camera_day + "/images/"
                        )
                        for image in os.listdir(camera_day_path):
                            white_listed = False
                            for f in whitelisted_files:
                                if image in str(f):
                                    # log.info(f"Skipping whitelisted file: {image}")
                                    white_listed = True
                                    break
                            if white_listed:
                                continue
                            image_path = camera_day_path + image
                            image = Image.open(image_path).convert("RGB")
                            log.info(f"Checking image: {image_path}")
                            buffered = BytesIO()
                            image.save(buffered, format="JPEG")
                            base64_str = base64.b64encode(buffered.getvalue())
                            entities = self.qa_for_entities(image=base64_str)
                            if not entities == []:
                                log.info(f"Found entities: {entities}")

                                # save video buffer to entities folder in a separate thread
                                # TODO: add try / except to IPCamera.add_to_buffer() and handle errors before uncommenting
                                # ip_camera.add_to_buffer()

                                # move image to entities folder
                                entity = " ".join(entities)
                                self.home_assistant.send_push_camera(camera_name=camera)
                                if not os.path.exists(
                                    self.path + "ftp/entities/" + entity + "/"
                                ):
                                    os.mkdir(self.path + "ftp/entities/" + entity + "/")
                                shutil.move(
                                    image_path,
                                    self.path + "ftp/entities/" + entities[0] + "/",
                                )

                            else:
                                log.info(
                                    f"No entities found, removing image: {image_path}"
                                )
                                # move into marked for deletion folder
                                shutil.move(
                                    image_path, self.path + "ftp/marked_for_deletion/"
                                )

                # remove marked for deletion folder
                shutil.rmtree(self.path + "ftp/marked_for_deletion/")

            except BaseException as e:
                log.error(e)
                time.sleep(1)
                shutil.rmtree(self.path + "ftp/marked_for_deletion/")
                bad_file = self.reset_camera_folders()
                if bad_file:
                    log.info(f"Whitelisting file: {bad_file}")
                    whitelisted_files.append(bad_file)
                continue


if __name__ == "__main__":
    ditto_security_vision = DittoSecurityVision()
    ditto_security_vision.check_ftp_for_entities(max_retries=10)
