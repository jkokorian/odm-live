import zmq
import msgpack as msg
import numpy as np
import msgpack_numpy
msgpack_numpy.patch()
import scipy as cp
from scipy.optimize import curve_fit
import time
import multiprocessing as mp
import sys
import pickle

class RealTimeFitter(object):
    def __init__(self):
        
        self._refFitFunction = None
        self._mpFitFunction = None
        self._xminRef = None
        self._xmaxRef = None
        self._xminMp = None
        self._xmaxMp = None
        self._refEstimates = [0.0,1.0,0.0]
        self._mpEstimates = [0.0,1.0,0.0]
        
    @property        
    def canFit(self):
        return self._mpFitFunction is not None and self._xminRef is not None and self._xmaxRef is not None and self._xminMp is not None and self._xmaxMp is not None
    
    def fit(self,intensityProfile):
        if self.canFit:
            try:
                displacement_mp, popt_mp = self._getMovingPeakDisplacement(intensityProfile)
                displacement_ref, popt_ref = self._getReferencePeakDisplacement(intensityProfile)
                return dict(displacement_mp=displacement_mp,
                            displacement_ref=displacement_ref,
                            popt_mp=popt_mp,
                            popt_ref=popt_ref,
                            fitFunction_mp=self._mpFitFunction,
                            fitFunction_ref=self._refFitFunction)
            except Exception as e:
                print e
        else:
            return dict()
    
    def _getMovingPeakDisplacement(self,intensityProfile):
        xdata = np.arange(len(intensityProfile))[self._xminMp:self._xmaxMp]
        ydata = intensityProfile[self._xminMp:self._xmaxMp]
        
        popt,pcov = curve_fit(self._mpFitFunction,xdata,ydata,p0=self._mpEstimates)
        self._mpEstimates = popt
        return self._mpFitFunction.getDisplacement(*popt), popt
        
    def _getReferencePeakDisplacement(self,intensityProfile):
        xdata = np.arange(len(intensityProfile))[self._xminRef:self._xmaxRef]
        ydata = intensityProfile[self._xminRef:self._xmaxRef]
        
        popt,pcov = curve_fit(self._refFitFunction,xdata,ydata,p0=self._refEstimates)
        self._refEstimates = popt
        return self._refFitFunction.getDisplacement(*popt), popt
    
    
    
    def setReferencePeakFitFunction(self,fitFunction):
        print "ref. fitfunction: %s" % fitFunction
        self._refFitFunction = fitFunction
        
    def setReferencePeakInterval(self,interval):
        print interval
        self._xmaxRef = int(max(interval))
        self._xminRef = int(min(interval))

    def setMovingPeakInterval(self,interval):
        print interval
        self._xmaxMp = int(max(interval))
        self._xminMp = int(min(interval))

        
    def setMovingPeakFitFunction(self,fitFunction):
        "mp. fitfunction: %s" % fitFunction
        self._mpFitFunction = fitFunction
        
        
    def reset(self):
        """
        Resets the stored curve-fit estimates to the default values.
        """
        self._refEstimates = [0.0,1.0,0.0]
        self._mpEstimates = [0.0,1.0,0.0]
    

class FittingConsumer():
    def __init__(self,producerAddress, collectorAddress, controlAddress)    :
        """
        Reads lvdata from producerAdress, uses it to do a curve fit, and sends the
        results to collectorAddress. The consumer can be controlled from controlAddress
        """
        self.context = zmq.Context()    
    
        self.control_socket = self.context.socket(zmq.PULL)
        self.control_socket.connect(controlAddress)
        
        self.producer_socket = self.context.socket(zmq.SUB)
        self.producer_socket.connect(producerAddress)
        self.producer_socket.setsockopt_string(zmq.SUBSCRIBE, u"")
        
        self.collector_socket = self.context.socket(zmq.PUSH)
        self.collector_socket.connect(collectorAddress)
        
        self.poller = zmq.Poller()
        self.poller.register(self.producer_socket,zmq.POLLIN)
        self.poller.register(self.control_socket,zmq.POLLIN)
        
        
        self.fitter = RealTimeFitter()    
        
        self.state = "idle"
        
        
    def run(self):
        print "running"
        while self.state is not "aborted":
                       
            sockets = dict(self.poller.poll(timeout=0))
            
            if self.control_socket in sockets and sockets[self.control_socket] == zmq.POLLIN:
                
                rpc = self.control_socket.recv_pyobj()
                self._handleRPC(rpc)
                
            if self.producer_socket in sockets and sockets[self.producer_socket] == zmq.POLLIN:
                # handle message from producer          
                message = self.producer_socket.recv()
                lvdata = msg.unpackb(message)
                self._handleProducerData(lvdata)
            if not sockets:
                time.sleep(1e-3)
        
        #abort logic
        self.producer_socket.close()
        self.collector_socket.close()
        self.control_socket.close()
        self.context.destroy()
            
    def _handleRPC(self,rpc):
        if rpc['method'] == 'stopFitting':
            self.state = "idle"
            
        elif rpc['method'] == 'startFitting':
            if self.fitter.canFit:
                self.state = "fitting"

        elif rpc['method'] == 'setMovingPeakFitFunction':
            self.fitter.setMovingPeakFitFunction(**rpc['params'])

        elif rpc['method'] == 'setReferencePeakFitFunction':
            self.fitter.setReferencePeakFitFunction(**rpc['params'])

        elif rpc['method'] == 'setMovingPeakInterval':
            self.fitter.setMovingPeakInterval(**rpc['params'])

        elif rpc['method'] == 'setReferencePeakInterval':
            self.fitter.setReferencePeakInterval(**rpc['params'])

        elif rpc['method'] == 'abort':
            self.state = "aborted"
        elif rpc['method'] == 'printState':
            print self.state
            

    def _handleProducerData(self,lvdata):
        if self.state == "fitting" and self.fitter.canFit:
            try:        
                fitResult = self.fitter.fit(lvdata['Intensity Profile'])
                self.collector_socket.send(msg.packb(fitResult))
            except:
                pass

def fitConsumeWorker(producerAddress, collectorAddress, controlAddress):
    fittingConsumer = FittingConsumer(producerAddress, collectorAddress, controlAddress)
    fittingConsumer.run()


class CurveFitServiceController(object):
    def __init__(self, producerAddress, collectorAddress, controlAddress=None):
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.PUSH)
        if controlAddress == None:
            port = self._socket.bind_to_random_port("tcp://localhost")
            controlAddress = "tcp://localhost:%i" % port
            print controlAddress
        else:
            self._socket.bind(controlAddress)
        
        self._socket.setsockopt(zmq.LINGER, 100)
        mp.Process(target=fitConsumeWorker,args=(producerAddress,collectorAddress,controlAddress)).start()
    
    
    def setReferencePeakFitFunction(self,fitFunction):
        rpc = dict(method="setReferencePeakFitFunction",
                   params=dict(fitFunction=fitFunction))
        self._socket.send_pyobj(rpc)
        
    def setReferencePeakInterval(self,interval):
        rpc = dict(method="setReferencePeakInterval",
                   params=dict(interval=interval))
        self._socket.send_pyobj(rpc)

    def setMovingPeakInterval(self,interval):
        rpc = dict(method="setMovingPeakInterval",
                   params=dict(interval=interval))
        self._socket.send_pyobj(rpc)
        
    def setMovingPeakFitFunction(self,fitFunction):
        rpc = dict(method="setMovingPeakFitFunction",
                   params=dict(fitFunction=fitFunction))
        self._socket.send_pyobj(rpc)
        
    def abort(self):
        rpc = dict(method="abort")
        self._socket.send_pyobj(rpc)
        
    def stopFitting(self):
        rpc = dict(method="stopFitting")
        self._socket.send_pyobj(rpc)
    
    def startFitting(self):
        rpc = dict(method="startFitting")
        self._socket.send_pyobj(rpc)
        
    def printState(self):
        rpc = dict(method="printState")
        self._socket.send_pyobj(rpc)
        

    
if __name__=="__main__":
    cfc = CurveFitServiceController("tcp://localhost:4562","tcp://localhost:4563","tcp://127.0.0.1:4568")
    time.sleep(2)    
    cfc.printState()