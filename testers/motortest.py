import time
from BrickPi import *

port=PORT_D

BrickPiSetup()
BrickPi.MotorEnable[port]=1
#BrickPi.MotorEnable[PORT_D] = 1
BrickPiSetupSensors()


BrickPi.MotorSpeed[port]=-200
#BrickPi.MotorSpeed[PORT_A] = -200
ot = time.time()
while(time.time() - ot < 2):    #running while loop for 3 seconds
	BrickPiUpdateValues()       # Ask BrickPi to update values for sensors/motors
	time.sleep(.1)
	

BrickPi.MotorSpeed[port]=200
#BrickPi.MotorSpeed[PORT_A] = -200
ot = time.time()
while(time.time() - ot < 2):    #running while loop for 3 seconds
	BrickPiUpdateValues()       # Ask BrickPi to update values for sensors/motors
	time.sleep(.1)
	

BrickPi.MotorSpeed[port]=-200
#BrickPi.MotorSpeed[PORT_A] = -200
ot = time.time()
while(time.time() - ot < 2):    #running while loop for 3 seconds
	BrickPiUpdateValues()       # Ask BrickPi to update values for sensors/motors
	time.sleep(.1)

