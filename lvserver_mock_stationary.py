import zmq
from random import randrange
from time import sleep
import msgpack as msg
import msgpack_numpy
msgpack_numpy.patch()
import numpy as np

context = zmq.Context()
socket = context.socket(zmq.PUB)
print socket.bind("tcp://*:4562")

messageDict = {"Measurement Process State": "pretending to capture a stationary profile"}

def gauss(x, mu, sigma):
    return np.exp(-(x-mu)**2/(2.*sigma**2))

print 'server online at port 4562'

xValues = np.linspace(0,100,200)

nsteps = 1000

i=0
while True:
    
    ipClean = gauss(xValues,30,5)+gauss(xValues,60,5)
    ip = np.random.poisson(ipClean*10000)

    messageDict['Intensity Profile'] = ip
    messageDict['Actuator Voltage'] = 0.0
    messageBytes = msg.packb(messageDict)
    socket.send(messageBytes)
    sleep(0.02)
    i+=1
    