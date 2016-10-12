from BrickPi import *
import time
import RPi.GPIO as GPIO
BrickPiSetup()
GPIO.setmode(GPIO.BCM)
LWHEEL = PORT_D
RWHEEL = PORT_A
GRABBER = PORT_B
ARM = PORT_C
HEAD = PORT_1
XDEGREES=260
WHEELPOWER     = -255
TURNPOWER      = 255 
SHOOBYPOWER    = -100
GRABBERPOWER   = -100
OPENPOWER      = 80
LIFTPOWER      = -200
BRINGDOWNPOWER = 100
BRINGDOWNBRAKEPOWER = -5
BrickPi.MotorEnable[GRABBER] = 1
BrickPi.MotorEnable[ARM] = 1
BrickPi.MotorEnable[LWHEEL] = 1
BrickPi.MotorEnable[RWHEEL] = 1
BrickPi.SensorType[HEAD] = TYPE_SENSOR_ULTRASONIC_CONT
BrickPiSetupSensors()
turnycount = 1 #first turn is left (excluding initial)

def takeencoderreading(port): #read motor position
	result = BrickPiUpdateValues()
	if not result :
		print "encoder reading is: " + str((BrickPi.Encoder[port]) /2)
		return ((BrickPi.Encoder[port]) /2)

#turn right
while True:
	BrickPi.MotorSpeed[RWHEEL] = 200; BrickPi.MotorSpeed[LWHEEL] = -200
	takeencoderreading(RWHEEL)