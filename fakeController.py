import zmq
import msgpack as msg
import time

def controller():
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.bind("tcp://*:4568")
    print "controller online"
    while True:        
        method = raw_input("method: ")
        rpc = dict(method=method)
        socket.send(msg.packb(rpc))
        print "rpc sent"
        
if __name__=="__main__":
    controller()