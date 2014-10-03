import zmq
from time import sleep
import msgpack as msg
import msgpack_numpy
msgpack_numpy.patch()
import numpy as np

context = zmq.Context()
socket = context.socket(zmq.PUB)
print socket.bind("tcp://*:4562")

messageDict = {"Measurement Process State": "fake measurement in progress"}

def gauss(x, mu, sigma):
    return np.exp(-(x-mu)**2/(2.*sigma**2))

print 'server online at port 4562'

xValues = np.linspace(0,100,200)

nsteps = 1000
actuatorVoltages = np.linspace(0,100,nsteps);
displacementValues = np.sin(actuatorVoltages/100 * 2*np.pi*1) * 3

i=0
while True:
    actuatorVoltage = actuatorVoltages[i%nsteps]
    displacement = displacementValues[i%nsteps]
    print dict(actuatorVoltage=actuatorVoltage, displacement=displacement)
    ipClean = gauss(xValues,30+displacement,5)+gauss(xValues,60,5)
    ip = np.random.poisson(ipClean*10000)

    messageDict['Intensity Profile'] = ip
    messageDict['Actuator Voltage'] = actuatorVoltage
    messageBytes = msg.packb(messageDict)
    socket.send(messageBytes)
    sleep(0.008)
    i+=1
    