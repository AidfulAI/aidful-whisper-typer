from pynput import keyboard
import codecs
import whisper
import time
import subprocess
import threading
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import pygame
import signal
import sys
from datetime import datetime
import json
import pyperclip
from pynput.keyboard import Key

file_ready_counter=0
stop_recording=False
is_recording=False
shutdown_event = threading.Event()
pykeyboard= keyboard.Controller()

def cleanup():
    """Perform cleanup operations before shutdown"""
    global stop_recording, is_recording
    shutdown_event.set()

    if is_recording:
        stop_recording = True
        time.sleep(1)

    pygame.mixer.quit()
    print("\nCleanup complete")

def signal_handler(sig, frame):
    print('\nInitiating shutdown...')
    cleanup()
    sys.exit(0)

def play_sound(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

def load_settings():
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
            return validate_settings(settings)
    except FileNotFoundError:
        print("The setting.json file was not found. Initiating shutdown.")
        cleanup()
        sys.exit(0)

def validate_settings(settings):
    valid_models = settings["model"]["options"]
    valid_output_modes = settings["output"]["options"]

    if settings["model"]["name"] not in valid_models:
        print(f"Invalid model name. Using default 'tiny'")
        settings["model"]["name"] = "tiny"

    if settings["output"]["mode"] not in valid_output_modes:
        print(f"Invalid output mode. Using default 'type'")
        settings["output"]["mode"] = "paste"

    return settings

settings = load_settings()

print("loading model...")
model_name = settings["model"]["name"]
model = whisper.load_model(model_name)
play_sound("model_loaded.wav")
print(f"{model_name} model loaded")



def handle_transcribed_text(transcribed_text):
    output_mode = settings["output"]["mode"]

    pyperclip.copy(transcribed_text)

    if output_mode == "type":
        for element in transcribed_text:
            if shutdown_event.is_set():
                break
            try:
                pykeyboard.type(element)
                time.sleep(settings["type"]["delay"])
            except:
                print("empty or unknown symbol")

    elif output_mode == "paste":
        try:
            with pykeyboard.pressed(Key.ctrl):
                pykeyboard.tap('v')
        except Exception as e:
            print(f"Error pasting text: {e}")

    elif output_mode == "clipboard":
        print("Text copied to clipboard")

    else:
        print(f"Unknown output mode: {output_mode}")

def transcribe_speech():
    global file_ready_counter
    i=1
    print("ready - start transcribing with F2 ...\n")
    while not shutdown_event.is_set():
        while file_ready_counter<i and not shutdown_event.is_set():
            time.sleep(0.01)

        if shutdown_event.is_set():
            break

        try:
            result = model.transcribe("test"+str(i)+".wav")
            transcribed_text = str(result["text"]).strip()
            print(">"+transcribed_text+"<\n")
            now = str(datetime.now()).split(".")[0]
            with codecs.open('transcribe.log', 'a', encoding='utf-8') as f:
                f.write(now+" : "+transcribed_text+"\n")
            handle_transcribed_text(transcribed_text)
            if os.path.exists("test"+str(i)+".wav"):
                os.remove("test"+str(i)+".wav")
            i=i+1
        except Exception as e:
            print(f"Error in transcription: {e}")

#keyboard events
pressed = set()

COMBINATIONS = [
    {
        "keys": [
            #{keyboard.Key.ctrl ,keyboard.Key.shift, keyboard.KeyCode(char="r")},
            #{keyboard.Key.ctrl ,keyboard.Key.shift, keyboard.KeyCode(char="R")},
            {keyboard.Key.f2},
        ],
        "command": "start record",
    },
]

#------------

#record audio
def record_speech():
    global file_ready_counter
    global stop_recording
    global is_recording

    is_recording = True
    sample_format = settings["audio"]["sample_format"]
    channels = settings["audio"]["channels"]
    fs = settings["audio"]["sample_rate"]

    frames = []  # Initialize list to store frames

    print("Start recording...\n")
    play_sound("on.wav")

    def callback(indata, frames_count, time_info, status):
        if status:
            print(status)
        frames.append(indata.copy())
        if stop_recording or shutdown_event.is_set():
            raise sd.CallbackStop()

    try:
        with sd.InputStream(samplerate=fs, channels=channels, dtype=sample_format, callback=callback):
            while not stop_recording and not shutdown_event.is_set():
                sd.sleep(100)

        if not shutdown_event.is_set():
            audio_data = np.concatenate(frames, axis=0)
            filename = "test" + str(file_ready_counter + 1) + ".wav"
            sf.write(filename, audio_data, fs)
            file_ready_counter = file_ready_counter + 1
            play_sound("off.wav")
            print('Finish recording')
    finally:
        stop_recording = False
        is_recording = False

#------------

#transcribe speech in infinite loop
t2 = threading.Thread(target=transcribe_speech, daemon=True)
t2.start()

#hot key events
def on_press(key):
    pressed.add(key)

def on_release(key):
    global pressed
    global stop_recording
    global is_recording
    for c in COMBINATIONS:
        for keys in c["keys"]:
            if keys.issubset(pressed):
                if c["command"]=="start record" and stop_recording==False and is_recording==False:
                    t1 = threading.Thread(target=record_speech)
                    t1.start()
                else:
                    if c["command"]=="start record" and is_recording==True:
                        stop_recording=True
                pressed = set()

signal.signal(signal.SIGINT, signal_handler)

try:
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
except KeyboardInterrupt:
    print("\nReceived keyboard interrupt")
except Exception as e:
    print(f"\nError occurred: {e}")
finally:
    cleanup()
    sys.exit(0)
