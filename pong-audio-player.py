"""
    # PONG PLAYER EXAMPLE

    HOW TO CONNECT TO HOST AS PLAYER 1
    > python pong-audio-player.py p1 --host_ip HOST_IP --host_port 5005 --player_ip YOUR_IP --player_port 5007

    HOW TO CONNECT TO HOST AS PLAYER 2
    > python pong-audio-player.py p2 --host_ip HOST_IP --host_port 5006 --player_ip YOUR_IP --player_port 5008

    about IP and ports: 127.0.0.1 means your own computer, change it to play across computer under the same network. port numbers are picked to avoid conflits.

    DEBUGGING:
    
    You can use keyboards to send command, such as "g 1" to start the game, see the end of this file

"""
#native imports
import time
from playsound import playsound
import argparse

from pythonosc import osc_server
from pythonosc import dispatcher
from pythonosc import udp_client

# threading so that listenting to speech would not block the whole program
import threading
# speech recognition (default using google, requiring internet)
import speech_recognition as sr
# pitch & volume detection
import aubio
import numpy as num
import pyaudio
import wave
import pyttsx3
import queue
import numpy as np

mode = ''
debug = False
quit = False

host_ip = "127.0.0.1"
host_port_1 = 5005 # you are player 1 if you talk to this port
host_port_2 = 5006
player_1_ip = "127.0.0.1"
player_2_ip = "127.0.0.1"
player_1_port = 5007
player_2_port = 5008

player_ip = "127.0.0.1"
player_port = 0
host_port = 0

if __name__ == '__main__' :

    parser = argparse.ArgumentParser(description='Program description')
    parser.add_argument('mode', help='host, player (ip & port required)')
    parser.add_argument('--host_ip', type=str, required=False)
    parser.add_argument('--host_port', type=int, required=False)
    parser.add_argument('--player_ip', type=str, required=False)
    parser.add_argument('--player_port', type=int, required=False)
    parser.add_argument('--debug', action='store_true', help='show debug info')
    args = parser.parse_args()
    print("> run as " + args.mode)
    mode = args.mode
    if (args.host_ip):
        host_ip = args.host_ip
    if (args.host_port):
        host_port = args.host_port
    if (args.player_ip):
        player_ip = args.player_ip
    if (args.player_port):
        player_port = args.player_port
    if (args.debug):
        debug = True

    #text to speech engine
    tts_queue = queue.Queue()
    engine = pyttsx3.init()
    def tts_worker():
        while True:
            text = tts_queue.get()
            if text is None:
                break
            engine.say(text)
            time.sleep(1.5)  # wait a bit to avoid overlapping
            engine.runAndWait()
            tts_queue.task_done()
    tts_thread = threading.Thread(target=tts_worker, daemon=True)
    tts_thread.start()

    # Ball position sine wave function and related things
    p_out = pyaudio.PyAudio()
    tone_stream = p_out.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=44100,
        output=True
    )
    TOP_Y = 0
    BOTTOM_Y = 450
    MAX_FREQ = 2000
    MIN_FREQ = 200
    TOP_X = 0
    BOTTOM_X = 800
    MAX_VOL = 1.05
    MIN_VOL = 0.1

    tone_queue = queue.Queue()

    def tone_worker():
        while True:
            freq, volume = tone_queue.get()
            if freq is None:
                break
            play_sine(freq, volume)
            tone_queue.task_done()

    tone_thread = threading.Thread(target=tone_worker, daemon=True)
    tone_thread.start()

    def play_sine(freq, volume, duration=0.015):
        fs = 44100
        samples = int(fs * duration)
        t = np.linspace(0, duration, samples, False)

        wave = (np.sin(2 * np.pi * freq * t) * volume).astype(np.float32)
        tone_stream.write(wave.tobytes())

    def map_y_to_freq(y):
        y = max(min(y, BOTTOM_Y), TOP_Y)
        return MAX_FREQ - (y / BOTTOM_Y) * (MAX_FREQ - MIN_FREQ)
    
    def map_x_to_vol(x):
        x = max(min(x, BOTTOM_X), TOP_X)
        return MAX_VOL - (x / BOTTOM_X) * (MAX_VOL - MIN_VOL)
# -------------------------------------#

# GAME INFO

# functions receiving messages from host
# TODO: add audio output so you know what's going on in the game

def explain_rules():
    rules_text = """
    Game Paused. Say start to begin or listen to the rules.
    Welcome to Pong! Here are the rules:
    1. Player one controls the left paddle, and player two controls the right paddle.
    2. The objective of the game is to bounce the ball past your opponent's paddle to score points.
    3. Use voice commands to control the paddles. Move your paddle up or down by changing the pitch of your voice. A higher pitch moves the paddle up, and a lower pitch moves it down.
    4. You can use your powerups by saying 'use big paddle' when you have one.
    5. Text to speech will inform you of important game events, such as scoring and powerup avaliability. 
    6. You will hear the ball position through audio cues: the pitch of the sound indicates the vertical position of the ball, and the volume indicates the horizontal position. Louder is closer to player 1!
    7. The game starts when both players are ready. You can say 'start' to begin the game.
    8. You can say 'pause' to pause the game and 'resume' to continue.
    """
    tts_queue.put(rules_text)

def on_receive_game(address, *args):
    print("> game state: " + str(args[0]))
    if args[0] == 0:
        explain_rules()
    elif args[0] == 1:
        tts_queue.put("Game started")
    # 0: menu, 1: game starts

def on_receive_ball(address, *args):
    # print("> ball position: (" + str(args[0]) + ", " + str(args[1]) + ")")
    x = args[0]
    y = args[1] 
    freq = map_y_to_freq(y)
    vol = map_x_to_vol(x)
    tone_queue.put((freq, vol))

def on_receive_paddle(address, *args):
    # print("> paddle position: (" + str(args[0]) + ", " + str(args[1]) + ")")
    pass

def on_receive_hitpaddle(address, *args):
    # example sound
    paddle_hit()
    print("> ball hit at paddle " + str(args[0]) )

def on_receive_ballout(address, *args):
    print("> ball went out on left/right side: " + str(args[0]) )
    if args[0] == 1:
        tts_queue.put("Player two scores")
    elif args[0] == 2:
        tts_queue.put("Player one scores")

def on_receive_ballbounce(address, *args):
    # example sound
    hit()
    print("> ball bounced on up/down side: " + str(args[0]) )

def on_receive_scores(address, *args):
    print("> scores now: " + str(args[0]) + " vs. " + str(args[1]))
    tts_queue.put("The score is " + str(args[0]) + " to " + str(args[1]))

def on_receive_level(address, *args):
    print("> level now: " + str(args[0]))
    tts_queue.put("Level " + str(args[0]))

def on_receive_powerup(address, *args):
    print("> powerup now: " + str(args[0]))
    if args[0] == 0:
        tts_queue.put("No power up")
    elif args[0] == 1:
        tts_queue.put("Player one is frozen")
    elif args[0] == 2:
        tts_queue.put("Player two is frozen")
    elif args[0] == 3:
        tts_queue.put("Player one can use big paddle")
    elif args[0] == 4:
        tts_queue.put("Player two can use big paddle")
    # 1 - freeze p1
    # 2 - freeze p2
    # 3 - adds a big paddle to p1, not use
    # 4 - adds a big paddle to p2, not use

def on_receive_p1_bigpaddle(address, *args):
    print("> p1 has a big paddle now")
    tts_queue.put("Player one has big paddle now")
    # when p1 activates their big paddle

def on_receive_p2_bigpaddle(address, *args):
    print("> p2 has a big paddle now")
    tts_queue.put("Player two has big paddle now")
    # when p2 activates their big paddle

def on_receive_hi(address, *args):
    print("> opponent says hi!")
    tts_queue.put("Your opponent says hi!")

dispatcher_player = dispatcher.Dispatcher()
dispatcher_player.map("/hi", on_receive_hi)
dispatcher_player.map("/game", on_receive_game)
dispatcher_player.map("/ball", on_receive_ball)
dispatcher_player.map("/paddle", on_receive_paddle)
dispatcher_player.map("/ballout", on_receive_ballout)
dispatcher_player.map("/ballbounce", on_receive_ballbounce)
dispatcher_player.map("/hitpaddle", on_receive_hitpaddle)
dispatcher_player.map("/scores", on_receive_scores)
dispatcher_player.map("/level", on_receive_level)
dispatcher_player.map("/powerup", on_receive_powerup)
dispatcher_player.map("/p1bigpaddle", on_receive_p1_bigpaddle)
dispatcher_player.map("/p2bigpaddle", on_receive_p2_bigpaddle)
# -------------------------------------#

# CONTROL

# TODO add your audio control so you can play the game eyes free and hands free! add function like "client.send_message()" to control the host game
# We provided two examples to use audio input, but you don't have to use these. You are welcome to use any other library/program, as long as it respects the OSC protocol from our host (which you cannot change)

# example 1: speech recognition functions using google api
# -------------------------------------#
def listen_to_speech():
    global quit
    while not quit:
        # obtain audio from the microphone
        r = sr.Recognizer()
        with sr.Microphone() as source:
            print("[speech recognition] Say something!")
            audio = r.listen(source)
        # recognize speech using Google Speech Recognition
        try:
            # for testing purposes, we're just using the default API key
            # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
            # instead of `r.recognize_google(audio)`
            recog_results = r.recognize_google(audio)
            print("[speech recognition] Google Speech Recognition thinks you said \"" + recog_results + "\"")
            
            if recog_results == "play" or recog_results == "start" or recog_results == "resume":
                client.send_message('/setgame', 1)
            if recog_results == "pause" or recog_results == "stop":
                client.send_message('/setgame', 0)
                print("[speech recognition] game paused")
            if recog_results == "insane":
                client.send_message("/setlevel", 3)
            if recog_results == "hard":
                client.send_message("/setlevel", 2)
            if recog_results == "easy":
                client.send_message("/setlevel", 1)
            if recog_results == "use big paddle" or recog_results == "big paddle":
                client.send_message("/setbigpaddle", 0)
            if recog_results == "say hi" or recog_results == "hi" or recog_results == "hello":
                client.send_message("/hi", 0)
            if recog_results == "quit" or recog_results == "exit":
                quit = True
                print("[speech recognition] quitting...")
                exit(0)
            
        
        # if recognizing quit and exit then exit the program
        except sr.UnknownValueError:
            print("[speech recognition] Google Speech Recognition could not understand audio")
        except sr.RequestError as e:
            print("[speech recognition] Could not request results from Google Speech Recognition service; {0}".format(e))
# -------------------------------------#

# example 2: pitch & volume detection
# -------------------------------------#
# PyAudio object.
p = pyaudio.PyAudio()
# Open stream.
stream = p.open(format=pyaudio.paFloat32,
    channels=1, rate=44100, input=True,
    frames_per_buffer=1024)
# Aubio's pitch detection.
pDetection = aubio.pitch("default", 2048,
    2048//2, 44100)
# Set unit.
pDetection.set_unit("Hz")
pDetection.set_silence(-40)

# function to turn microphone pitch into paddle position
def pitch_to_paddle(pitch) -> float: # 600 to 150 is good ig
    position = 0
    if pitch != 0:
        position = pitch - 175
        if pitch >= 375 and pitch < 600:
            difference = (pitch - 375) 
            position = 225 - difference
            if position < 25:
                position = 25
        if pitch < 375 and pitch >= 150:
            difference = (375 - pitch) * 1.5
            position = 225 + difference
            if position > 425:
                position = 425
        if pitch < 150:
            position = 425
        if pitch > 600: 
            position = 25
    return position

def sense_microphone():
    global quit
    global debug
    while not quit:
        data = stream.read(1024,exception_on_overflow=False)
        samples = num.frombuffer(data,
            dtype=aubio.float_type)

        # Compute the pitch of the microphone input
        pitch = pDetection(samples)[0]
        # Compute the energy (volume) of the mic input
        volume = num.sum(samples**2)/len(samples)
        # Format the volume output so that at most
        # it has six decimal numbers.
        volume = "{:.6f}".format(volume)

        # uncomment these lines if you want pitch or volume
        #print("pitch "+str(pitch)+" volume "+str(volume))
        # send paddle position based on pitch
        paddle_pos = pitch_to_paddle(pitch)
        client.send_message("/setpaddle", int(paddle_pos))
        #print("[microphone] pitch: " + str(int(pitch)) + " Hz -> paddle position: " + str(int(paddle_pos)))
# -------------------------------------#



# -------------------------------------#

# Play some fun sounds?
# -------------------------------------#
def hit():
    playsound('hit.wav', False)

def paddle_hit():
    playsound('tennis-smash-100733.mp3', False)

hit()
paddle_hit()
# -------------------------------------#

# OSC connection
# -------------------------------------#
# used to send messages to host
if mode == 'p1':
    host_port = host_port_1
if mode == 'p2':
    host_port = host_port_2

if (mode == 'p1') or (mode == 'p2'):
    client = udp_client.SimpleUDPClient(host_ip, host_port)
    print("> connected to server at "+host_ip+":"+str(host_port))

# speech recognition thread
# -------------------------------------#
# start a thread to listen to speech
speech_thread = threading.Thread(target=listen_to_speech, args=())
speech_thread.daemon = True
speech_thread.start()

# pitch & volume detection
# -------------------------------------#
# start a thread to detect pitch and volume
microphone_thread = threading.Thread(target=sense_microphone, args=())
microphone_thread.daemon = True
microphone_thread.start()

# OSC thread
# -------------------------------------#
# Player OSC port
if mode == 'p1':
    player_port = player_1_port
if mode == 'p2':
    player_port = player_2_port

player_server = osc_server.ThreadingOSCUDPServer((player_ip, player_port), dispatcher_player)
player_server_thread = threading.Thread(target=player_server.serve_forever)
player_server_thread.daemon = True
player_server_thread.start()
# -------------------------------------#
client.send_message("/connect", player_ip)

# MAIN LOOP
# manual input for debugging
# -------------------------------------#
while True:
    m = input("> send: ")
    cmd = m.split(' ')
    if len(cmd) == 2:
        client.send_message("/"+cmd[0], int(cmd[1]))
    if len(cmd) == 1:
        client.send_message("/"+cmd[0], 0)
    
    # this is how client send messages to server
    # send paddle position 200 (it should be between 0 - 450):
    
    # set level to 3:
    # client.send_message('/l', 3)
    # start the game:
    # client.send_message('/g', 1)
    # pause the game:
    # client.send_message('/g', 0)
    # big paddle if received power up:
    # client.send_message('/b', 0)
