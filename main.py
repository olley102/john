#!/usr/bin/env python2.7
###################################################
#//JOHN (fully automated roadside litter picker)//#
#                    //main.py//                  #
#         //Started 29.05.16//v15//13.03.17       #
#     //ANDREW WANG//  //All Rights Reserved//    #
# //BrickPi: github.com/DexterInd/BrickPi_Python//#

##########################################    SETUP    ##########################################

#Import relevant modules
import time, math, lirc, sys, pygame, os, cmpautocalib, logging
from BrickPi import *         #BrickPi script
from compassgpsutils import * #Custom interfacing script
import RPi.GPIO as GPIO       #General Purpose Input Output

#Initial setup
GPIO.setmode(GPIO.BCM)                   #set GPIO numbering
BrickPiSetup()                           #setup BrickPi interface
sockid = lirc.init("main",blocking=False)#setup infrared remote control
clock = pygame.time.Clock()              #setup FPS clock

#Port Assignments  ;    #GPIO Pins
LWHEEL = PORT_D    ;    IRIN     = 25 #yellow, in - IR sensor (when sth close, 0)
RWHEEL = PORT_A    ;    US2TRIG  = 24 #brown , out- high US sensor
GRABBER= PORT_B    ;    US2ECHO  = 23 #green , in - high US sensor
ARM    = PORT_C    ;    USNEWTRIG= 17 #purple, out- low  US sensor
''''''             ;    USNEWECHO= 22 #yellow, in - low  US sensor
''''''             ;    BUZZOUT  = 7  #brown , out- buzzer
''''''             ;    IRRCINT  = 8  #white , in - irrc interrupt pin

#Constants
XDEGREES       = 75     #angle between robot path & path (integ. degs)-MODIFIED BY SETTINGS BELOW
USSTANDARD     = 30     #low us(new) sensor detection threshold
US2STANDARD    = 50     #high us(2) detection threshold
OPTLITTERRANGE = [19,26]#the opt us distance range from which it can pick up stuff
STOPRANGE      = 15     #the allowable range for turnbear (compass)
DISTANCECUTOFF = 200    #max US detected distance before cutting off

#Extract everything from settings file
settingsfile = open('/home/pi/mainsettings.dat','r')
settingsdata = settingsfile.read().split('\n')
x_offset = int(settingsdata[0]); y_offset = int(settingsdata[1]) 
origfwdb      = int(float(settingsdata[2])) #origfwdb -> fwdb (orig stays same)
batterysaving = int(settingsdata[3])        #0=off, 1=on, 2=super
XDEGREES      = int(settingsdata[4])

settingsfile.close()
print 'origfwdb '     , origfwdb
print 'batterysaving ', batterysaving
print 'XDEGREES '     , XDEGREES

#Motor Power Constants
#if battery low, add extra juice to motors
if batterysaving   == 0: extrajuice = 0
elif batterysaving == 1: extrajuice = 20
elif batterysaving == 2: extrajuice = 50
#make sure nothing goes over 255 - highest extrajuice!
WHEELPOWER     = -(180 + extrajuice) #driving power
TURNPOWER      =   150 + extrajuice  #pos = forwards (for ease of use but not technically correct)
SHIFTPOWER     =   130 + extrajuice  #shifting left and right
BRAKEPOWER     =   -5                #braking turning
SHOOBYPOWER    = -(100 + extrajuice) #shifting fwd and bwd
GRABBERPOWER   = -(170 + extrajuice) #close grabber
OPENPOWER      =   70  + extrajuice  #open grabber
LIFTPOWER      = -(200 + extrajuice) #lift arm from fully down
SLIDEUPPOWER   = -(100 + extrajuice) #for deactivating arm
BRINGDOWNPOWER =   150 + extrajuice  #bring arm down
ACTIVATEUS2POWER=  140 + extrajuice/2#activate US2 position
BRINGDOWNBRAKEPOWER = -5

#Setup motors, sensors (encoder), GPIO Pins
BrickPi.MotorEnable[GRABBER] = 1 ; BrickPi.MotorEnable[ARM]    = 1
BrickPi.MotorEnable[LWHEEL]  = 1 ; BrickPi.MotorEnable[RWHEEL] = 1

def restart(): os.execl(sys.executable, sys.executable, *sys.argv)
try: #catch error if getty wasn't disabled on boot
	BrickPiSetupSensors()
except OSError:
	print "Getty not disabled"
	os.system("sudo sh /home/pi/stopev.sh")
	restart()

GPIO.setup(IRIN     , GPIO.IN) ; GPIO.setup(BUZZOUT  , GPIO.OUT)
GPIO.setup(USNEWECHO, GPIO.IN) ; GPIO.setup(USNEWTRIG, GPIO.OUT)
GPIO.setup(US2ECHO  , GPIO.IN) ; GPIO.setup(US2TRIG  , GPIO.OUT)
GPIO.setup(IRRCINT  , GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

#Program Runtime Variables
turnycount = 0 #keep track of which way to turn - initial: left=1 right=0
turnbears = [] ; targBear = 0 #bearing of lturn and rturn
shoobied = 'no'
debouncetimestamp = time.time()
previoususreading = 100
abandonship = False
timelimitreached = False

#Setup error logging
logging.basicConfig(filename='/home/pi/errorlogs.dat', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.debug('\n \n ---NEW SESSION---')

print "SETUP FINISHED" #print to stdout

###################################       FUNCTIONS       ########################################

try: #catch errors in case

	#Activate buzzer
	def buzz(patternofbuzz):
		patternofbuzz = patternofbuzz.split()
		for i in range(len(patternofbuzz)):
			GPIO.output(BUZZOUT, True)
			if   patternofbuzz[i] == "short" : time.sleep(0.1)
			elif patternofbuzz[i] == "long"  : time.sleep(0.3)
			GPIO.output(BUZZOUT, False)
			if len(patternofbuzz) >= 1 and i != len(patternofbuzz)-1: time.sleep(0.2)
	
	#Take reading from an ultrasonic sensor
	def takeusreading(trig, echo, repeats=3, disregardhigh=False):
		global previoususreading
		GPIO.output(trig, False) #switch everything off
		#take 4 readings then find average
		uslist=[]; durationcutoff = DISTANCECUTOFF/34000
		
		for i in range(repeats):
			distance = 0; duration = 0
			#send out signal
			GPIO.output(trig, False); time.sleep(0.001)
			GPIO.output(trig, True);  time.sleep(0.001)
			GPIO.output(trig, False)
			
			#find length of signal
			start = time.time(); stop = time.time()
			while GPIO.input(echo) == 0:
				start = time.time()
				if (start-stop) >= 0.006:
					distance = DISTANCECUTOFF
					break #bail out if waiting too long
			while GPIO.input(echo) == 1:
				stop  = time.time()
				if (stop-start) >= 0.006:
					distance = DISTANCECUTOFF
					break #bail out if waiting too long
			#breaks when cut off point is bypassed - this prevents stalling.
			
			duration = abs(stop - start)
			#find length
			if distance == 0: distance = duration * 340 * 100 #cm from speed of sound
			#if necessary, get rid of all high values
			if disregardhigh == True:
				if int(distance) >= DISTANCECUTOFF:
					continue #don't add it
			uslist += [int(distance)]
			time.sleep(0.01)
		
		if uslist == []: uslist.append(previoususreading)#just in case everything was disregarded
		uslist.sort(); usreading = uslist[len(uslist)/2] #median (get rid of anomalies)
		previoususreading = usreading
		GPIO.output(trig, False)
		print "US reading is ", str(usreading), uslist
		return usreading
	
	#Read motor position from built in encoder
	def takeencoderreading(port):
		for i in range(3): #deal with encoder glitches
			result = BrickPiUpdateValues()
			if not result: #result is 0 is sensor read is successful
				print BrickPi.Encoder[port]
				return (BrickPi.Encoder[port])
		return 0 #better than Nonetype

	#Set wheels goin'
	def drivewheels(lpower, rpower):
		BrickPi.MotorSpeed[LWHEEL] = lpower
		BrickPi.MotorSpeed[RWHEEL] = rpower
		BrickPiUpdateValues()

	#Create list of bearings for each turn according to forward direction
	def createturnbears():
		turnbears = [fwdb-XDEGREES , fwdb+XDEGREES] #l,r
		#correct to 0<b<360
		for i in range(len(turnbears)):
			if turnbears[i] > 360: turnbears[i] -= 360
			if turnbears[i] < 0  : turnbears[i] += 360
		print turnbears; return turnbears
	
	#LITTER PICKING PROCEDURE
	def pickprocedure():
		print "bringing down" #get grabber into correct position
		movelimbLENG(ARM, BRINGDOWNPOWER, 0.6)

		#preliminary grab
		movelimbLENG(GRABBER, GRABBERPOWER, 0.6, ARM, BRINGDOWNPOWER)

		print "lifting" #bring litter up
		movelimbLENG(ARM, LIFTPOWER, 0.7, GRABBER, GRABBERPOWER) #grabber grips as well
		time.sleep(0.5)
		
		print "opening" #dump litter
		movelimbLENG(GRABBER, OPENPOWER, 0.5); time.sleep(0.5)	

	#TURNING PROCEDURE
	def turnprocedure():
		global turnycount; global turnbears; global targBear
		time.sleep(0.5)

		#setup wheels depending on direction to turn
		if turnycount%2 == 1: #odd=left
			wheel1 = RWHEEL; wheel2 = LWHEEL
			targBear = turnbears[0]
		else: #right
			wheel1 = LWHEEL; wheel2 = RWHEEL
			targBear = turnbears[1]

		#while turning, use compass for guidance, and search litter too
		print "turning", turnycount
		movelimbENC(wheel1, -TURNPOWER, targBear, wheel2, TURNPOWER, detection=True, compass=True)
		movelimbLENG(wheel1, BRAKEPOWER, 0.1, wheel2, -BRAKEPOWER) #brake

		turnycount += 1 #next time turns other way
		time.sleep(0.5)	

	
	#Move motor based on time length
	def movelimbLENG(limb, speed, length, limb2=None, speed2=None):
		#set speed(s)
		BrickPi.MotorSpeed[limb] = speed
		if limb2 != None: BrickPi.MotorSpeed[limb2] = speed2 #opt. simultaneous 2nd motor movement

		#time movement
		ot = time.time()
		while(time.time() - ot < length): BrickPiUpdateValues()
		time.sleep(0.1)

		#stop
		BrickPi.MotorSpeed[limb] = 0
		if limb2 != None: BrickPi.MotorSpeed[limb2] = 0
		BrickPiUpdateValues()
	
	#Move motor based on encoder OR COMPASS guidance
	def movelimbENC(limb, speed, deg, limb2=None, speed2=None, detection=False, compass=False):
		#this turns a motor until it reaches certain encoder position OR John faces certain dir.
		#deg is the change in: encoder degrees (scalar) OR compass deg if compass=True
		#for encoder, positive speed is positive encoder increase
		#for compass, turning  right is positive bearing increase
		
		startpos = takeencoderreading(limb)
		#set directions
		if   speed > 0: modifier=1
		elif speed < 0: modifier=-1

		if compass == False: #in this instance turn based on encoder
			while True:
				#carry on turning till limb reaches correct pos
				modifiedreading = (takeencoderreading(limb) - startpos) * modifier
				if modifiedreading >= deg: break #at final position

				BrickPi.MotorSpeed[limb] = speed
				if limb2 != None: BrickPi.MotorSpeed[limb2]=speed2 #opt. simultan. 2nd motor mvmt

		elif compass == True: #in this instance turn based on COMPASS
			while True:
				#carry on turning till reaches correct bearing
				modifiedreading = (takeencoderreading(limb) - startpos) * modifier #encoder shiz
				if abs(takebearing()-deg) <= STOPRANGE: break #at final bearing

				BrickPi.MotorSpeed[limb] = speed
				if limb2 != None: BrickPi.MotorSpeed[limb2]=speed2 #opt. simultan. 2nd motor mvmt

				if detection==True: #litter detection while turning
					if modifiedreading >= 120: #turned enough so safe to start measuring 4 litter
						detectprocedure(True)

		#stop
		BrickPi.MotorSpeed[limb] = 0
		if limb2 != None: BrickPi.MotorSpeed[limb2] = 0
		
		BrickPiUpdateValues()
	
	#Drive/turn depending on US sensor
	def movewhilecondition(formofmovement, trig, echo, op, val, power, wallprevention=False, llote=False, disregardhigh=False):
		global abandonship; global timelimitreached
		time.sleep(0.4)
		wheel1pwr,wheel2pwr = -1,1 #for turning
		b = 0
		#determine what the movement is
		if   formofmovement == "turnback":    b = 1
		elif formofmovement == "notturnback": b = 0
		elif formofmovement == "forwards": wheel1pwr,wheel2pwr = 1,1 #modify for driving
		elif formofmovement == "backwards":wheel1pwr,wheel2pwr = -1,-1
		
		#set wheel directions
		if turnycount%2 == b: #direction is inputted by user
			wheel1 = LWHEEL; wheel2 = RWHEEL
		else:
			wheel1 = RWHEEL; wheel2 = LWHEEL
		
		extraparameters=""
		if llote == True: extraparameters += ", repeats=1" #don't repeat readings
		if disregardhigh == True: extraparameters += ", disregardhigh=True"
		
		ot = time.time()
		while eval("takeusreading(trig, echo" + extraparameters + ")" + op + "val"):
			if wallprevention == True:
				#just stop turning when there's a wall no matter what, if necessary
				if takeusreading(US2TRIG, US2ECHO) < US2STANDARD: break
			
			if time.time()-ot >= 1:
				timelimitreached = True
				break #time limit so it doesn't turn forever
			
			if GPIO.input(IRIN) == 1: #cliff!
				drivewheels(0,0) #stop
				movelimbENC(LWHEEL, -WHEELPOWER, 130, RWHEEL, -WHEELPOWER) #reverse
				buzz("long")
				abandonship = True
			
			if abandonship == True:
				break
				
			#turn until condition is met
			BrickPi.MotorSpeed[wheel1]=wheel1pwr*power; BrickPi.MotorSpeed[wheel2]=wheel2pwr*power
			BrickPiUpdateValues()

		movelimbLENG(wheel1, BRAKEPOWER, 0.1, wheel2, -BRAKEPOWER) #brake
		drivewheels(0,0) #stop
		time.sleep(0.4)
	
	#Reset arm and grabber back to base pos of up and open
	def resetarmandgrabber():
		print "sliding up, deactivate, opening grabber"
		movelimbLENG(ARM, SLIDEUPPOWER, 0.3, GRABBER, OPENPOWER)
		time.sleep(0.2)

	#DETECTION PROCEDURE
	def detectprocedure(alreadyturning):
		global abandonship; global timelimitreached
		#check LOW US for object
		tempreading = takeusreading(USNEWTRIG,USNEWECHO)
		
		if tempreading < USSTANDARD:
			#detected something!
			drivewheels(0,0) #stop
			print "object detected"; buzz("short")

			#activate HIGH US(2) pos
			if alreadyturning == False: #I'm not turning (so I want to activate us2 pos)
				print "sliding down bit by bit, activate"
				movelimbENC(ARM, ACTIVATEUS2POWER, 70)
				movelimbLENG(ARM, BRINGDOWNBRAKEPOWER, 0.1) #brake to prevent coast
				time.sleep(0.7)

			#check HIGH US(2) for big thing	
			if takeusreading(US2TRIG, US2ECHO) > US2STANDARD:
				#Nothing detected -> low lying object -> LITTER
				buzz("short"); print "low-lying object detected"; time.sleep(0.5)

				#DETECTION CORRECTION PROCEDURES
				#these procedures centre John on litter.
				abandonship = False; timelimitreached = False
				
				#if while turning, turn back a wee until it's in sight, then make verify
				messedup = True
				
				if alreadyturning == True:
					for i in range(2):
						
						print "turn back until in sight"
						movewhilecondition("turnback", USNEWTRIG, USNEWECHO, ">", USSTANDARD, SHIFTPOWER, llote=True)
						print "turn not back until in sight"
						movewhilecondition("notturnback", USNEWTRIG, USNEWECHO, ">", USSTANDARD, SHIFTPOWER, llote=True)
						
						messedup = False
						#in case it's monumentally messed up, turn back!
						if takeusreading(USNEWTRIG,USNEWECHO,repeats=7) > USSTANDARD: #messed up
							print "turning back, cos monumentally failed"
							movewhilecondition("turnback", USNEWTRIG, USNEWECHO, ">", USSTANDARD, SHIFTPOWER, llote=True)
							messedup = True
						
						if messedup == False: break

				#if not turning, turn dir A until out of sight, turn away in dir B until in sight,
				#then carry on in B until out of sight, then back in A until in sight again
				else:
					
					print "Turning direction until no longer in sight"
					movewhilecondition("notturnback", USNEWTRIG, USNEWECHO, "<", USSTANDARD, SHIFTPOWER, wallprevention=True, llote=True)
					print "Turning other direction until in sight again"
					movewhilecondition("turnback",    USNEWTRIG, USNEWECHO, ">", USSTANDARD, SHIFTPOWER, llote=True)
					print "Turning other direction until no longer in sight"
					movewhilecondition("turnback",    USNEWTRIG, USNEWECHO, "<", USSTANDARD, SHIFTPOWER, wallprevention=True, llote=True)
					print "Turning in orginial direction to centre"
					movewhilecondition("notturnback", USNEWTRIG, USNEWECHO, ">", USSTANDARD, SHIFTPOWER, llote=True)

				#shooby closer/further if litter is not in optimum range to pick up
				shoobied = 'no'; print "checking shooby"
				tempreading = takeusreading(USNEWTRIG, USNEWECHO, repeats=7, disregardhigh=True)
				startpos = takeencoderreading(LWHEEL)
				
				if tempreading <= OPTLITTERRANGE[0]: #too close
					print "too close, shoobying AWAY"
					movewhilecondition("backwards", USNEWTRIG, USNEWECHO, "<", OPTLITTERRANGE[0], WHEELPOWER, disregardhigh=True)
					shoobiedenc = abs(takeencoderreading(LWHEEL) - startpos) #so we know where we've gone
					shoobied='away'
				
				elif tempreading >= OPTLITTERRANGE[1]: #too far
					print "too far, shoobying NEAR"
					movewhilecondition("forwards",  USNEWTRIG, USNEWECHO, ">", OPTLITTERRANGE[1], WHEELPOWER, disregardhigh=True)
					shoobiedenc = abs(takeencoderreading(LWHEEL) - startpos)
					shoobied='near'

				#PICK UP THE BLOODY LITTER
				if abandonship == False:
					if timelimitreached == False:
						pickprocedure()

				#move back if shoobied before
				if abandonship == False:
					if shoobied=='away':
						print "shoobying NEAR back to original pos"
						movelimbENC(LWHEEL, WHEELPOWER, shoobiedenc, RWHEEL, WHEELPOWER)
					elif shoobied=='near':
						print "shoobying AWAY back to original pos"
						movelimbENC(LWHEEL, -WHEELPOWER, shoobiedenc, RWHEEL, -WHEELPOWER)

				#turn back to original turnbear
				if alreadyturning == False:
					adjust = targBear - takebearing()
					#check which dir to turn back(depending on sgn of adjust, or if it's wrapping)
					if adjust < 0 or adjust > 180: #turn left
						wheel1 = RWHEEL; wheel2 = LWHEEL
					if adjust > 0 or adjust < 180: #turn right
						wheel1 = LWHEEL; wheel2 = RWHEEL
					print "turning back to original bear"
					movelimbENC(wheel1, -TURNPOWER, targBear, wheel2, TURNPOWER, compass=True)
					movelimbLENG(wheel1, BRAKEPOWER, 0.1, wheel2, -BRAKEPOWER) #brake
				
				abandonship = False; timelimitreached = False
				#loop back and carry on

			else:
				#Something detected -> tall object -> WALL
				print "WALL"; buzz("short") #WALL(US)

				if alreadyturning == False:
					#I'm not turning already so I want to turn and deactivate at wall
					turnprocedure()
					resetarmandgrabber()
					time.sleep(0.5)
					#loop back and carry on

				elif alreadyturning == True:
					#I am already turning so I want to get away from this goddamn wall
					print "turning away from goddamn wall"
					#turn until wall is not in sight (to get rid of stalling)(screw detection)
					movewhilecondition("notturnback",US2TRIG,US2ECHO, "<=", US2STANDARD,TURNPOWER)
 	
	#Debounce interrupt, restart program
	def restartprogram(channel=0):
		global debouncetimestamp
		timenow = time.time()

		#handle button being pressed when main is running - restart (essentially, stop)
		if timenow - debouncetimestamp >= 0.3: #debounce ir so only 1 interrupt
			print "taking action on interrupt"
			if startmain == True: #only restart program if main is actually running!
				BrickPi.MotorSpeed[GRABBER]=0;BrickPi.MotorSpeed[ARM]=0; drivewheels(0,0)#stop all
				buzz("short long"); GPIO.cleanup()
				print "Stop pressed - Restarting program"
				restart()
		debouncetimestamp = timenow

	#Set GPIO interrupt - restart program when interrupted! (by button on RC)
	GPIO.add_event_detect(IRRCINT, GPIO.RISING, callback=restartprogram)


######################################     MAIN PROGRAM     #####################################
	buzz("short"); print "I'm ready to go!"

	startmain = False
	while True:
		clock.tick(10) #make sure constant FPS so John doesn't blow up

		#infrared remote control handling loop
		ircode = lirc.nextcode()
		if ircode:
			fwdb=0
			
			#buttons to start main program in various directions
			if ircode[0]  ==  "startmainfwdleft":  #pressed 1
				turnycount = 1 ; fwdb = origfwdb; buzz("short short")
				startmain = True; time.sleep(0.3)
			elif ircode[0] == "startmainfwdright": #pressed 2
				turnycount = 0 ; fwdb = origfwdb; buzz("short short")
				startmain = True; time.sleep(0.3)
			elif ircode[0] == "startmainbwdleft":  #pressed 4
				turnycount = 1 ; fwdb = origfwdb + 180 ; buzz("short short")
				startmain = True; time.sleep(0.3)
			elif ircode[0] == "startmainbwdright": #pressed 5
				turnycount = 0 ; fwdb = origfwdb + 180 ; buzz("short short")
				startmain = True; time.sleep(0.3)
			
			#buttons to handle batterysaving changes
			elif ircode[0] in ["batterysavingoff", "batterysavingon", "batterysavingsuper"]:
				if   ircode[0] == "batterysavingoff"  : newbatterysaving = 0 #pressed 3
				elif ircode[0] == "batterysavingon"   : newbatterysaving = 1 #pressed 6
				elif ircode[0] == "batterysavingsuper": newbatterysaving = 2 #pressed 9
				
				#write new data
				settingsfile = open('/home/pi/mainsettings.dat','w')
				for i in [x_offset, y_offset, origfwdb, newbatterysaving, XDEGREES]:
					settingsfile.write(str(i) + "\n")
				print "added newbatterysaving ", newbatterysaving
				settingsfile.close(); buzz("short"); GPIO.cleanup(); restart()
			
			#buttons to handle xdegrees changes
			elif ircode[0] in ["xdegreesdown", "xdegreesup"]:
				if   ircode[0] == "xdegreesdown": newxdegrees = XDEGREES - 5 #pressed VOLUMEDOWN
				elif ircode[0] == "xdegreesup"  : newxdegrees = XDEGREES + 5 #pressed VOLUMEUP
				
				#write new data
				settingsfile = open('/home/pi/mainsettings.dat','w')
				for i in [x_offset, y_offset, origfwdb, batterysaving, newxdegrees]:
					settingsfile.write(str(i) + "\n")
				print "added new xdegrees ", newxdegrees
				settingsfile.close(); buzz("short"); GPIO.cleanup(); restart()				
			
			#buttons to handle other things
			elif ircode[0] == "startshutdown":     #pressed 0
				print "Shutting down!"; buzz("short short short short")
				os.system('sudo shutdown -h now')
			elif ircode[0] == "startcmpautocalib": #pressed SETUP
				#start calibration procedure of compass
				print "starting calibration script"; buzz("long long")
				cmpautocalib.maincalibprogram()
				restart() #restart to reset all GPIO pins
			elif ircode[0] == "startstopev":       #pressed 7
				#stop getty (if it didn't stop at boot)
				print "deactivating getty" ; buzz("long short")
				os.system("sudo ./stopev.sh") ; print "restarting"
				GPIO.cleanup(); restart()
			elif ircode[0] == "stopmainpy":        #pressed 8
				#stop main.py program (for diagnostics)
				print "stopping main"; buzz("long long long")
				GPIO.cleanup(); sys.exit()
			elif ircode[0] == "bants":             #pressed PLAY
				buzz("long long short short long short short short long short short")

			if fwdb > 360: fwdb -= 360 #correction
			print turnycount, fwdb


		if startmain == True:
			print "main has started"
			
			#initial stuff
			turnbears = createturnbears()

			#bring arm back up and open grabber in case it's not
			resetarmandgrabber()

			#initial turn from forwards
			turnprocedure()

			############MAIN MAIN CHOW MEIN LOOP#############
			while True:
				#drive
				drivewheels(WHEELPOWER, WHEELPOWER)

				#search for object
				detectprocedure(False)

				#check IR sensor for cliff
				if GPIO.input(IRIN) == 1: #nothing close (underneath sensor)
					print "CLIFF"
					drivewheels(0,0) #stop
					#reverse!
					movelimbENC(LWHEEL, -WHEELPOWER, 130, RWHEEL, -WHEELPOWER)

					buzz("long")
					turnprocedure()
					#loop back and carry on


#ERROR HANDLERS
except (KeyboardInterrupt, SystemExit): #ensure clean exit
	logging.exception('KeyboardInterrupt or SystemExit'); print "KeyboardInterrupt or SystemExit"
	GPIO.cleanup(); raise
except: #any other error, restart!
	logging.exception('Found error in main!'); print "Found error in main!"
	GPIO.cleanup(); restart()
