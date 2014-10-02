import zmq
import msgpack as msg
import msgpack_numpy
msgpack_numpy.patch()
from pyqtgraph import QtCore, QtGui
from threading import Thread
import time
import sys
import numpy as np


app = QtGui.QApplication(sys.argv)


class EmittingLVODMClient(QtCore.QObject):
    messageReceived = QtCore.Signal(dict)    
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.isConnected = False
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.consumer = EmittingSocketConsumer(self.socket)
            
    def abort(self):
        self.consumer.abort()
    
    def connect(self,host):
        self.socket.connect(host)
        self.socket.setsockopt_string(zmq.SUBSCRIBE,u"")
    
    def startAsync(self):
        self.consumer.messageReceived.connect(self._emitMessageReceived)
        self.consumer.start()
    
    def _emitMessageReceived(self,messageDict):
        self.messageReceived.emit(messageDict)


class ProcessingLVODMClient(EmittingLVODMClient):
    messageProcessed = QtCore.Signal(dict)
    
    def __init__(self,processingAction):
        EmittingLVODMClient.__init__(self)
        self.consumer = ProcessingSocketConsumer(self.socket,processingAction)
    
    def startAsync(self):
        self.consumer.messageProcessed.connect(self._emitMessageProcessed)
        EmittingLVODMClient.startAsync(self)
    
    def _emitMessageProcessed(self,resultDict):
        self.messageProcessed.emit(resultDict)



class EmittingSocketConsumer(QtCore.QThread):
    messageReceived = QtCore.Signal(dict)
    
    def __init__(self,socket):
        QtCore.QThread.__init__(self)        
        self.socket = socket
        self.abortRequested = False
    
    def abort(self):
        self.abortRequested = True

    def run(self):
        while not self.abortRequested:
            messageBytes = self.socket.recv()
            messageDict = msg.unpackb(messageBytes)
            self.messageReceived.emit(messageDict)
        self.socket.close()
        self.terminate()
        
            

class ProcessingSocketConsumer(QtCore.QThread):
    messageReceived = QtCore.Signal(dict)
    messageProcessed = QtCore.Signal(dict)
    
    def __init__(self,socket,processingAction):
        QtCore.QThread.__init__(self)        
        self.socket = socket
        self.abortRequested = False
        self.processingAction = processingAction
    
    def abort(self):
        self.abortRequested = True    
    
    def run(self):
        while not self.abortRequested:
            messageBytes = self.socket.recv()
            messageDict = msg.unpackb(messageBytes)
            self.messageReceived.emit(messageDict)
            result = self.processingAction(messageDict)
            self.messageProcessed.emit(result)
        self.socket.close()
        self.terminate()




if __name__=="__main__":
    
    def printMessageKeys(messageDict):
        print messageDict.keys()
    
    def showProfile(intensityProfile):
        print intensityProfile
    
    def fakeProcess(messageDict):
        time.sleep(1)
        return dict(kanker="vervelend")
    
    
    client = EmittingLVODMClient()
    client.connect("tcp://localhost:4567")
    client.messageReceived.connect(printMessageKeys)
    
    def q():
        client.abort()
        app.quit()
    
    QtCore.QTimer.singleShot(0, client.startAsync)
    QtCore.QTimer.singleShot(10000,q)
    sys.exit(app.exec_())