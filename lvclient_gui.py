# -*- coding: utf-8 -*-
"""
Demonstrates use of PlotWidget class. This is little more than a 
GraphicsView with a PlotItem placed in its center.
"""


import PyQt4.QtCore as q
import PyQt4.QtGui as qt

import numpy as np
import pyqtgraph as pg
import pyqtgraph.dockarea as dock

import zmq
import msgpack as msg
import msgpack_numpy
msgpack_numpy.patch()
from lvclient import EmittingLVODMClient,ProcessingLVODMClient

import odmanalysis as odm
from odmanalysis import fitfunctions

import time

from scipy.optimize import curve_fit


class MeanRecorder(q.QObject):
    def __init__(self):
        q.QObject.__init__(self)
        self.profile = None
        self.n = 0.0
    
    def reset(self):
        self.profile = None
        self.n = 0.0
        
    def record(self,profile):
        if self.n > 0:
            self.n+=1
            self.profile = profile/self.n + self.profile * (self.n-1)/self.n
        elif self.n == 0:
            self.n += 1
            self.profile = profile
        else:
            pass


class SplineCreatorWidget(qt.QWidget):
    movingPeakIntervalChanged = q.Signal(tuple)
    referencePeakIntervalChanged = q.Signal(tuple)
    movingPeakFitFunctionChanged = q.Signal(fitfunctions.ScaledSpline)
    referencePeakFitFunctionChanged = q.Signal(fitfunctions.ScaledSpline)
    
    def __init__(self,parent=None):        
        qt.QWidget.__init__(self,parent)
        
        layout = qt.QVBoxLayout()
        self.setLayout(layout)
        
        self.toggleButton = qt.QPushButton("record reference")
        layout.addWidget(self.toggleButton)
        
        self.plotWidget = pg.PlotWidget(name='Intensity Profile')
        layout.addWidget(self.plotWidget)
        
        self.meanRecorder = MeanRecorder()        
        
        self.refPeakSplineControl = InteractiveSplineCreatorControlsWidget(self.meanRecorder,parent=self)
        self.movingPeakSplineControl = InteractiveSplineCreatorControlsWidget(self.meanRecorder,parent=self)
        
        hLayout = qt.QHBoxLayout()
        hLayout.addWidget(self.refPeakSplineControl)
        hLayout.addWidget(self.movingPeakSplineControl)
        hLayout.addStretch()
        layout.addLayout(hLayout)
        
        pw = self.plotWidget
        self.livePlot = pw.plot()
        self.livePlot.setPen((200,200,100))
        
        self.meanPlot = pw.plot()
        self.meanPlot.setPen((100,200,200))
        
        pw.setLabel('left', 'Intensity', units='a.u.')
        pw.setLabel('bottom', 'Position', units='px')
        pw.setXRange(0, 200)
        pw.setYRange(0, 10000)
        
        self.movingPeakRegion = pg.LinearRegionItem(brush=pg.intColor(1,alpha=100))
        self.movingPeakRegion.setZValue(10)
        
        self.referencePeakRegion = pg.LinearRegionItem(brush=pg.intColor(2,alpha=100))
        self.referencePeakRegion.setZValue(10)
        # Add the LinearRegionItem to the ViewBox, but tell the ViewBox to exclude this 
        # item when doing auto-range calculations.
        pw.addItem(self.movingPeakRegion, ignoreBounds=True)
        pw.addItem(self.referencePeakRegion, ignoreBounds=True)
        #pg.dbg()
        pw.setAutoVisible(y=True)
        
        
        # connect signals and slots
        self.toggleButton.clicked.connect(self.meanRecorder.reset)
        self.referencePeakRegion.sigRegionChangeFinished.connect(self._emitReferencePeakIntervalChanged)
        self.movingPeakRegion.sigRegionChangeFinished.connect(self._emitMovingPeakIntervalChanged)
        
        self.refPeakSplineControl.splineCreator.fitFunctionCreated.connect(self._emitReferencePeakFitFunctionChanged)
        self.movingPeakSplineControl.splineCreator.fitFunctionCreated.connect(self._emitMovingPeakFitFunctionChanged)
        
        
        
    def _emitReferencePeakIntervalChanged(self):
        interval = self.referencePeakRegion.getRegion()
        self.referencePeakIntervalChanged.emit(interval)
            
    def _emitMovingPeakIntervalChanged(self):
        interval = self.movingPeakRegion.getRegion()        
        self.movingPeakIntervalChanged.emit(interval)
    
    def _emitMovingPeakFitFunctionChanged(self,spline):
        self.movingPeakFitFunctionChanged.emit(spline)
        
    def _emitReferencePeakFitFunctionChanged(self,spline):
        self.referencePeakFitFunctionChanged.emit(spline)
        
    
    
    def updateData(self, intensityProfile):
        xValues = np.arange(0,len(intensityProfile))
        self.livePlot.setData(y=intensityProfile, x=xValues)
        self.meanRecorder.record(intensityProfile)
        self.meanPlot.setData(y=self.meanRecorder.profile, x=xValues)
    


class FitGraphWidget(qt.QWidget):
    def __init__(self,parent=None):        
        qt.QWidget.__init__(self,parent)
        
        layout = qt.QVBoxLayout()
        self.setLayout(layout)
        
        
        self.plotWidget = pg.PlotWidget(name='Fit')
        layout.addWidget(self.plotWidget)
                
        self.__initializePlots()
        
        
    def __initializePlots(self):
        pw = self.plotWidget
        self.livePlot = pw.plot()
        self.livePlot.setPen((200,200,100))
        
        self.movingPeakFitPlot = pw.plot()
        self.movingPeakFitPlot.setPen((200,0,0))
        self.referencePeakFitPlot = pw.plot()
        self.referencePeakFitPlot.setPen((0,200,0))
        self.xValues = None
        
        pw.setLabel('left', 'Intensity', units='a.u.')
        pw.setLabel('bottom', 'Position', units='px')
        pw.setXRange(0, 200)
        pw.setYRange(0, 10000)
        
        pw.setAutoVisible(y=True)
    
    def updateIntensityProfile(self, intensityProfile):
        xValues = np.arange(0,len(intensityProfile))
        self.xValues = xValues
        self.livePlot.setData(y=intensityProfile, x=xValues)
        
    def updateGraphData(self, fitFunction_mp, popt_mp, fitFunction_ref,popt_ref):
        self.movingPeakFitPlot.setData(x=self.xValues,y=fitFunction_mp(self.xValues,*popt_mp))
        
        self.referencePeakFitPlot.setData(x=self.xValues,y=fitFunction_ref(self.xValues,*popt_ref))
    
class RollingChartWidget(qt.QWidget):
    def __init__(self,parent=None):
        qt.QWidget.__init__(self,parent)
        
        self.initializeBuffer(5000)
        
        layout = qt.QVBoxLayout()
        self.setLayout(layout)
        
        self.plotWidget = pg.PlotWidget()
        self.livePlot = self.plotWidget.plot()
        self.livePlot.setPen((200,200,100))
        layout.addWidget(self.plotWidget)
        
    def initializeBuffer(self,size):
        self._xBuffer = np.empty(size)   
        self._yBuffer = np.empty(size)
        self._xBuffer.fill(np.NAN)
        self._yBuffer.fill(np.NAN)
        self._bufferSize = size
        self._bufferPointer = 0
    
    @property
    def bufferSize(self):
        return self._bufferSize
        
    @bufferSize.setter
    def setBufferSize(self,size):
        self._initializeBuffer(size)
        
    def addData(self,y):
        i = self._bufferPointer % self._bufferSize
        self._yBuffer[i] = y
        self.livePlot.setData(y=self._yBuffer)
        self._bufferPointer += 1
            
    

class LVStatusDisplayWidget(qt.QWidget):
    def __init__(self,parent=None):
        qt.QWidget.__init__(self,parent)
        
        layout = qt.QGridLayout()
        self.setLayout(layout)
        
        layout.addWidget(qt.QLabel("Labview Status:"),0,0)       

        self.lvStatusLabel = qt.QLabel("")        
        layout.addWidget(self.lvStatusLabel,0,1)
        
        
    
    def updateStatus(self,status):
        if not status == self.lvStatusLabel.text:
            self.lvStatusLabel.setText(status)



        

class InteractiveSplineCreator(q.QObject):
    
    fitFunctionCreated = q.Signal(fitfunctions.ScaledSpline)
    
    def __init__(self):
        q.QObject.__init__(self)
        
        self._fitFunction = None
        self._sigma = 0
        self._intensityProfile = None
    
    @property
    def intensityProfile(self):
        return self._intensityProfile
    
    
    def setIntensityProfile(self,intensityProfile):
        self._intensityProfile = intensityProfile
    
    @property
    def sigma(self):
        return self._sigma
        
        
    def setSigma(self,sigma):
        self._sigma = sigma
        
    
    def hasFitFunction(self):
        return self._fitFunction is not None
    
    @property
    def fitFunction(self):
        return self._fitFunction
    
    def createSpline(self):
        spline = fitfunctions.ScaledSpline()
        spline.estimateInitialParameters(self.intensityProfile,
                                         filter_sigma=self.sigma)
        
        self._fitFunction = spline
        self.fitFunctionCreated.emit(spline)
        

class InteractiveSplineCreatorControlsWidget(qt.QWidget):
    def __init__(self,meanRecorder, parent=None):
        qt.QWidget.__init__(self,parent)
        
        layout=qt.QGridLayout()
        self.setLayout(layout)        
        
        layout.addWidget(qt.QLabel("Gaussian filter sigma:"),0,0)

        self.sigmaSpinBox = qt.QSpinBox()  
        self.sigmaSpinBox.setMinimum(0)
        self.sigmaSpinBox.setMaximum(10)
        layout.addWidget(self.sigmaSpinBox,0,1)
        
        self.makeFitFunctionButton = qt.QPushButton("Create")
        layout.addWidget(self.makeFitFunctionButton,1,0)
        
        self.splineCreator = InteractiveSplineCreator()        
        self.meanRecorder = meanRecorder
        
        # connect signals and slots
        self.sigmaSpinBox.valueChanged.connect(self.splineCreator.setSigma)
        self.makeFitFunctionButton.clicked.connect(self.createSpline)
    
    def createSpline(self):
        self.splineCreator.setIntensityProfile(self.meanRecorder.profile)
        self.splineCreator.createSpline()
        
        
class RealTimeFitter(q.QObject):
    def __init__(self,parent=None):
        q.QObject.__init__(self,parent)
        
        self._refFitFunction = None
        self._mpFitFunction = None
        self._xminRef = None
        self._xmaxRef = None
        self._xminMp = None
        self._xmaxMp = None
        
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
        
        popt,pcov = curve_fit(self._mpFitFunction,xdata,ydata,p0=[0.0,1.0,0.0])
        return self._mpFitFunction.getDisplacement(*popt), popt
        
    def _getReferencePeakDisplacement(self,intensityProfile):
        xdata = np.arange(len(intensityProfile))[self._xminRef:self._xmaxRef]
        ydata = intensityProfile[self._xminRef:self._xmaxRef]
        
        popt,pcov = curve_fit(self._refFitFunction,xdata,ydata,p0=[0.0,1.0,0.0])
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
        
        
    


class MainWindow(qt.QMainWindow):
    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self,parent)
        
        self.setWindowTitle("Live ODM Analysis")
        self.resize(1000,800)
        
        area=dock.DockArea()
        self.dockArea = area
        self.setCentralWidget(area)
        
        #create docks
        d1 = dock.Dock("Spline Creator", size=(500, 500))     ## give this dock the minimum possible size
        d2 = dock.Dock("LabView Status", size=(1,100))
        d3 = dock.Dock("Fit result", size=(500,400))
        d4 = dock.Dock("Displacement", size=(500,200))
        
        area.addDock(d1, 'left')      ## place d1 at left edge of dock area (it will fill the whole space since there are no other docks yet)
        area.addDock(d2, 'bottom', d1)     ## place d2 at right edge of dock area
        area.addDock(d3, 'bottom', d2)## place d3 at bottom edge of d1
        area.addDock(d4, 'right')     ## place d4 at right edge of dock area
        
        self.splineCreatorWidget = SplineCreatorWidget(self)
        d1.addWidget(self.splineCreatorWidget)        
        
        self.lvStatusDisplay = LVStatusDisplayWidget(self)
        hLayout = qt.QHBoxLayout()
        hLayout.addWidget(self.lvStatusDisplay)
        hLayout.addStretch()
        w2 = qt.QWidget()
        w2.setLayout(hLayout)        
        d2.addWidget(w2)
        
        
        
        
        self.fitGraph = FitGraphWidget(self)
        d3.addWidget(self.fitGraph)

                
        self.displacementChart = RollingChartWidget()
        d4.addWidget(self.displacementChart)
        
        
        self.fitter = RealTimeFitter()
        
        self.lvClient = EmittingLVODMClient()
        self.lvClient.connect("tcp://localhost:4562")
        
        self.fitClient = ProcessingLVODMClient(lambda d: self.fitter.fit(d['Intensity Profile']))
        self.fitClient.connect("tcp://localhost:4562")
        
        
        # connect signals and slots        
        self.lvClient.messageReceived.connect(self.handleLVData)
        self.fitClient.messageProcessed.connect(self.handleFitResult)
                
        self.splineCreatorWidget.referencePeakIntervalChanged.connect(self.fitter.setReferencePeakInterval)
        self.splineCreatorWidget.movingPeakIntervalChanged.connect(self.fitter.setMovingPeakInterval)
        
        self.splineCreatorWidget.movingPeakFitFunctionChanged.connect(self.fitter.setMovingPeakFitFunction)
        self.splineCreatorWidget.referencePeakFitFunctionChanged.connect(self.fitter.setReferencePeakFitFunction)
        
        
    def handleLVData(self,lvData):
        status = lvData['Measurement Process State']
        intensityProfile = np.array(lvData['Intensity Profile'])
        
        self.splineCreatorWidget.updateData(intensityProfile)
        self.fitGraph.updateIntensityProfile(intensityProfile)
        self.lvStatusDisplay.updateStatus(status)
    
    def handleFitResult(self,fitResult):
        if fitResult is not None and len(fitResult) != 0:
            
            self.fitGraph.updateGraphData(fitFunction_mp=fitResult['fitFunction_mp'],
                                          fitFunction_ref=fitResult['fitFunction_ref'],
                                          popt_mp=fitResult['popt_mp'],
                                          popt_ref=fitResult['popt_ref'])
            self.displacementChart.addData(y=fitResult['displacement_mp']-fitResult['displacement_ref'])                                  
    
    def show(self):
        super(MainWindow,self).show()
        self.lvClient.startAsync()
        self.fitClient.startAsync()

    def closeEvent(self,event):
        self._abortClients()
        qt.QWidget.closeEvent(self,event)        
        
    
    def _abortClients(self):
        print "aborting"
        self.lvClient.abort()
        self.fitClient.abort()
    
    

## Start Qt event loop unless running in interactive mode or using pyside.
if __name__ == '__main__':
    #QtGui.QApplication.setGraphicsSystem('raster')
    app = qt.QApplication([])
    mw = MainWindow()
    mw.show()

    import sys
    if (sys.flags.interactive != 1) or not hasattr(q, 'PYQT_VERSION'):
        
        qt.QApplication.instance().exec_()