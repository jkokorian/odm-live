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

messageDict = dict(status="liveVideo")

def gauss(x, mu, sigma):
    return np.exp(-(x-mu)**2/(2.*sigma**2))

print 'server online at port 4562'

xValues = np.linspace(0,100,200)
ipClean = gauss(xValues,30,5)+gauss(xValues,60,5)

while True:
    ip = np.random.poisson(ipClean*10000)
    messageDict['intensityProfile'] = ip
    messageBytes = msg.packb(messageDict)
    socket.send(messageBytes)
    sleep(0.005)
    