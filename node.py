import configparser
import logging
import math
import socket
import time
import sys
import random
import typing

from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

import grpc

import GHS_pb2
import GHS_pb2_grpc
import abc
from abc import abstractmethod, ABCMeta
from google.protobuf import text_format

from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
edges = {}

neighbor = []

SE = {}

BranchDict = {}

numOfNodes = 0

SLEEPING = 0

FIND = 1

FOUND = 2

BASIC = 0

BRANCH = 1

REJECTED = 2

INFINITY = 999999999

MsgQueue = deque()

fragmentLevel = int
fragmentID = int
state = int
findCount = int
waiting_to_connect_to = int
in_branch= []
best_edge = tuple()
best_wt = int
test_edge = tuple
report_edge = []

server = grpc.server(ThreadPoolExecutor(max_workers=100))
finished = False

class SleepingPolicy(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def sleep(self, try_i: int):
        """
        How long to sleep in milliseconds.
        :param try_i: the number of retry (starting from zero)
        """
        assert try_i >= 0

class ExponentialBackoff(SleepingPolicy):
    def __init__(self, *, init_backoff_ms: int, max_backoff_ms: int, multiplier: int):
        self.init_backoff = random.randint(0, init_backoff_ms)
        self.max_backoff = max_backoff_ms
        self.multiplier = multiplier

    def sleep(self, try_i: int):
        global logger
        sleep_range = min( self.init_backoff * self.multiplier ** try_i, self.max_backoff)
        sleep_ms = random.randint(0, sleep_range)
        logger.debug(f"Sleeping for {sleep_ms}")
        time.sleep(sleep_ms / 1000)

class RetryOnRpcErrorClientInterceptor(grpc.UnaryUnaryClientInterceptor, grpc.StreamUnaryClientInterceptor):
    def __init__(self, *, max_attempts: int, sleeping_policy: SleepingPolicy, status_for_retry: Optional[Tuple[grpc.StatusCode]] = None):
        self.max_attempts = max_attempts
        self.sleeping_policy = sleeping_policy
        self.status_for_retry = status_for_retry

    def _intercept_call(self, continuation, client_call_details, request_or_iterator):

        for try_i in range(self.max_attempts):
            response = continuation(client_call_details, request_or_iterator)

            if isinstance(response, grpc.RpcError):

                # Return if it was last attempt
                if try_i == (self.max_attempts - 1):
                    return response

                # If status code is not in retryable status codes
                if (
                    self.status_for_retry
                    and response.code() not in self.status_for_retry
                ):
                    return response

                self.sleeping_policy.sleep(try_i)
            else:
                return response

    def intercept_unary_unary(self, continuation, client_call_details, request):
        return self._intercept_call(continuation, client_call_details, request)

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return self._intercept_call(continuation, client_call_details, request_iterator)

class Message:
    def __init__(self, msgType, nodeNum, request):
        self.msgType = msgType
        self.nodeNum = nodeNum
        self.request = request

def FindMinBasicEdge():
    minedge = (INFINITY, INFINITY)
    for x in neighbor:
        if (SE[x] == BASIC):
            for y in edges[socket.gethostname()]:
                if (y[0] == x):
                    if (y[1] < minedge[1]):
                        minedge = (x, y[1])
    return minedge

def WakeUpIfNeeded():
    global state
    global findCount
    global INFINITY
    global SLEEPING
    global SE
    global BRANCH
    global waiting_to_connect_to
    global fragmentLevel

    if (state == SLEEPING):
            print(socket.gethostname() + " is waking up!")
            # todo: call a function that finds min-wt BASIC node instead..
            minedge = FindMinBasicEdge()

            state = FOUND

            findCount = 0

            if (minedge[0] != INFINITY):
                with grpc.insecure_channel('node' + str(minedge[0]) + ':50050') as channel:
                    interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                    intercept_channel = grpc.intercept_channel(channel, *interceptors)
                    stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                    Connect = GHS_pb2.ConnectMSG(nodename= socket.gethostname(), fragmentLevel= fragmentLevel)
                    stub.Connect(Connect)
                SE[minedge[0]] = BRANCH
                waiting_to_connect_to = minedge[0]

def ReportProc(request):
    global findCount
    global test_edge
    global state
    global FOUND
    global best_wt
    global in_branch
    global neighbor
    global report_edge
    global INFINITY
    global edges

    node = request.nodename
    if ( (findCount == 0) and (test_edge == None) ):
        state == FOUND
        for x in in_branch:
            if int(x) in neighbor:

                edge = [ int( socket.gethostname()[4:] ), int( node[4:] )]
                for y in edges[socket.gethostname()]:
                    if ( y[0] == int(node[4:]) ):
                        weightOfNode = y[1]
                        if ( ( weightOfNode == best_wt ) or (best_wt == INFINITY) ):
                            report_edge = edge

                with grpc.insecure_channel('node' + str(x) + ':50050') as channel:
                            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                            intercept_channel = grpc.intercept_channel(channel, *interceptors)
                            stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                            Report = GHS_pb2.ReportMSG(nodename = socket.gethostname(), weight = best_wt, edge = report_edge)
                            stub.Report(Report)

def TestProc(request):
    global SE
    global BASIC
    global test_edge
    global INFINITY
    global fragmentLevel
    global fragmentID

    hasBasicEdge = False
    for x in SE:
        if (SE[x] == BASIC):
            hasBasicEdge = True
    if (hasBasicEdge):
        test_edge = FindMinBasicEdge()
        if (test_edge[0] != INFINITY):
            with grpc.insecure_channel('node' + str(test_edge[0]) + ':50050') as channel:
                    interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                    intercept_channel = grpc.intercept_channel(channel, *interceptors)
                    stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                    Test = GHS_pb2.TestMSG(nodename = socket.gethostname(), fragmentLevel = fragmentLevel, fragmentID = fragmentID)
                    stub.Test(Test)
    else:
        test_edge = None
        ReportProc(request)

def ChangeCoreProc():
    global SE
    global best_edge
    global BRANCH
    global fragmentLevel
    global waiting_to_connect_to

    if (fragmentLevel > 0):

        if ( SE[ int( best_edge[1][4:] ) ] == BRANCH ):
            with grpc.insecure_channel(best_edge[1] + ':50050') as channel:
                    interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                    intercept_channel = grpc.intercept_channel(channel, *interceptors)
                    stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                    changeCore = GHS_pb2.ChangeCoreMSG(nodename= socket.gethostname())
                    stub.ChangeCore(changeCore)
        else:
            with grpc.insecure_channel(best_edge[1] + ':50050') as channel:
                        waiting_to_connect_to = best_edge[1]
                        interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                        intercept_channel = grpc.intercept_channel(channel, *interceptors)
                        stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                        Connect = GHS_pb2.ConnectMSG(nodename= socket.gethostname(), fragmentLevel= fragmentLevel)
                        stub.Connect(Connect)
            SE[ int( best_edge[1][4:] ) ] = BRANCH


class NodeMessages(GHS_pb2_grpc.MessagingServicer):

    def WakeUp(self, request, context):
        global MsgQueue
        WakeUpMSG = Message("WakeUp", None, request)
        MsgQueue.appendleft(WakeUpMSG)

        return GHS_pb2.Empty()

    def Connect(self, request, context):
        global MsgQueue
        node = request.nodename
        ConnectMSG = Message("Connect", node, request)
        MsgQueue.appendleft(ConnectMSG)

        return GHS_pb2.Empty()

    def Initiate(self, request, context):
        global MsgQueue
        node = request.nodename
        InitiateMSG = Message("Initiate", node, request)
        MsgQueue.appendleft(InitiateMSG)

        return GHS_pb2.Empty()

    def Test(self, request, context):
        global MsgQueue
        node = request.nodename
        TestMSG = Message("Test", node, request)
        MsgQueue.appendleft(TestMSG)

        return GHS_pb2.Empty()

    def AcceptReject(self, request, context):
        global MsgQueue
        node = request.nodename
        AcceptRejectMSG = Message("AcceptReject", node, request)
        MsgQueue.appendleft(AcceptRejectMSG)

        return GHS_pb2.Empty()

    def Report(self, request, context):
        global MsgQueue
        node = request.nodename
        ReportMSG = Message("Report", node, request)
        MsgQueue.appendleft(ReportMSG)

        return GHS_pb2.Empty()

    def ChangeCore(self, request, context):
        global MsgQueue
        node = request.nodename
        ChangeCoreMSG = Message("ChangeCore", node, request)
        MsgQueue.appendleft(ChangeCoreMSG)

        return GHS_pb2.Empty()

    def Branches(self, request, context):
        global BranchDict
        global numOfNodes
        global finished
        node = request.nodename
        branches =  request.branches
        BranchDict[int(node[4:])] = branches
        everyNodeHasBranch = True
        nodeList = []
        for x in BranchDict:
            nodeList.append(x)
            if (BranchDict[x] == None):
                everyNodeHasBranch = False
        if everyNodeHasBranch:
            templist = []
            templist.append(0)
            branchStack = deque()
            branchStack.append(0)
            while branchStack:
                for x in BranchDict[branchStack[0]]:
                    if (int(x) not in templist):
                        templist.append(int(x))
                        branchStack.append(int(x))
                branchStack.popleft()
            templist.sort()
            if (templist == nodeList):
                print('BranchDict = ' + str(BranchDict))
                for x in range(0, numOfNodes):
                    with grpc.insecure_channel('node' + str(x) + ':50050') as channel:
                        print('sending finish message to node' + str(x))
                        interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                        intercept_channel = grpc.intercept_channel(channel, *interceptors)
                        stub = GHS_pb2_grpc.GallagerStub(intercept_channel)
                        message = GHS_pb2.FinishedMSG(finish = 1)
                        stub.Finished(message)
                finished = True

        return GHS_pb2.Empty()

def ExecWakeup(request):
    WakeUpIfNeeded()
    return GHS_pb2.Empty()

def ExecConnect(request):
    global fragmentLevel
    global fragmentID
    global SE
    global BRANCH
    global state
    global FIND
    global findCount
    global BASIC
    global MsgQueue
    global waiting_to_connect_to
    global in_branch

    WakeUpIfNeeded()

    level = request.fragmentLevel
    node = request.nodename

    print ('recieved Connect from ' + node + ' with fragmentLevel = ' + str(level))

    if (level < fragmentLevel):
        SE[int(node[4:])] = BRANCH
        in_branch.append(node[4:])
        with grpc.insecure_channel('coordinator:50050') as channel:
            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
            intercept_channel = grpc.intercept_channel(channel, *interceptors)
            stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
            branchMSG = GHS_pb2.BranchesMSG(nodename= socket.gethostname(), branches = in_branch)
            stub.Branches(branchMSG)
        with grpc.insecure_channel(node + ':50050') as channel:
            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
            intercept_channel = grpc.intercept_channel(channel, *interceptors)
            stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
            init = GHS_pb2.InitiateMSG(nodename= socket.gethostname(), fragmentLevel= fragmentLevel, fragmentID = fragmentID, state= state)
            stub.Initiate(init)
        if (state == FIND):
            findCount = findCount + 1
    elif (SE[int(node[4:])] == BASIC):
        ConMSG = Message("Connect", node, request)
        MsgQueue.appendleft(ConMSG)
    else:
        with grpc.insecure_channel(node + ':50050') as channel:
            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
            intercept_channel = grpc.intercept_channel(channel, *interceptors)
            stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
            weightOfNode = int
            for x in edges[socket.gethostname()]:
                if ( x[0] == int(node[4:]) ):
                    weightOfNode = x[1]
            init = GHS_pb2.InitiateMSG(nodename= socket.gethostname(), fragmentLevel= (fragmentLevel + 1), fragmentID = weightOfNode, state = FIND)
            stub.Initiate(init)     

def ExecInitiate(request):
    global fragmentLevel
    global fragmentID
    global state
    global in_branch
    global best_edge
    global best_wt
    global INFINITY
    global SE
    global BRANCH
    global FIND
    global findCount

    node = request.nodename
    fragmentLevel = request.fragmentLevel
    fragmentID = request.fragmentID
    state = request.state

    print ('recieved Initiate from ' + node + ' with fragmentLevel = ' + str(fragmentLevel) + ', fragmentID = ' + str(fragmentID) + ', and state = ' + str(state) )

    in_branch.append(node[4:])
    with grpc.insecure_channel('coordinator:50050') as channel:
        interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
        intercept_channel = grpc.intercept_channel(channel, *interceptors)
        stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
        branchMSG = GHS_pb2.BranchesMSG(nodename= socket.gethostname(), branches = in_branch)
        stub.Branches(branchMSG)
    best_edge = None
    best_wt = INFINITY
    for x in SE:
        if ( (x != int(node[4:])) and (SE[x] == BRANCH) ):
            noFragEdge = False
            with grpc.insecure_channel("node" + str(x) + ':50050') as channel:
                interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                intercept_channel = grpc.intercept_channel(channel, *interceptors)
                stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                init = GHS_pb2.InitiateMSG(nodename= socket.gethostname(), fragmentLevel= fragmentLevel, fragmentID = fragmentID, state= state)
                stub.Initiate(init)
            if (state == FIND):
                findCount = findCount + 1
    if (state == FIND):
        TestProc(request) 

def ExecTest(request):
    global fragmentLevel
    global fragmentID
    global SE
    global BASIC
    global REJECTED
    global test_edge
    global MsgQueue

    WakeUpIfNeeded()
    level = request.fragmentLevel
    node = request.nodename
    ID = request.fragmentID

    print ('recieved Test from ' + node + ' with fragmentLevel = ' + str(level) + ', and fragmentID = ' + str(ID))

    if (level > fragmentLevel):
        TestMSG = Message("Test", node, request)
        MsgQueue.appendleft(TestMSG)
    elif (ID != fragmentID):
        with grpc.insecure_channel(node + ':50050') as channel:
            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
            intercept_channel = grpc.intercept_channel(channel, *interceptors)
            stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
            accept = GHS_pb2.AcceptRejectMSG(nodename= socket.gethostname(), AorR = 0) # 0 = Accept
            stub.AcceptReject(accept)
    else:
        if (SE[int(node[4:])] == BASIC):
            SE[int(node[4:])] = REJECTED
        if (test_edge[0] != int(node[4:])):
            with grpc.insecure_channel(node + ':50050') as channel:
                interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
                intercept_channel = grpc.intercept_channel(channel, *interceptors)
                stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
                reject = GHS_pb2.AcceptRejectMSG(nodename= socket.gethostname(), AorR = 1) # 1 = Reject
                stub.AcceptReject(reject)
        else:
            TestProc(request) 

def ExecAcceptReject(request):
    global test_edge
    global edges
    global best_wt
    global best_edge
    global BASIC
    global REJECTED

    node = request.nodename
    AorR = request.AorR

    print ('recieved AcceptReject from ' + node + ' with AorR = ' + str(AorR))

    if (AorR == 0): # if Accept
        test_edge = None
        for x in edges[socket.gethostname()]:
            if ( x[0] == int(node[4:]) ):
                weightOfNode = x[1]
                if ( weightOfNode < best_wt ):
                    best_edge = (socket.gethostname(), node)
                    best_wt = weightOfNode
        ReportProc(request)
    elif (AorR == 1):
        if ( SE[int(node[4:])] == BASIC ):
            SE[int(node[4:])] = REJECTED
        TestProc(request)

def ExecReport(request):
    global in_branch
    global findCount
    global best_wt
    global best_edge
    global state
    global FIND
    global INFINITY
    global MsgQueue
    global report_edge

    node = request.nodename
    weight = request.weight
    edge = request.edge

    print ('recieved Report from ' + node + ' with weight = ' + str(weight))

    if ( str(edge[1]) not in in_branch ):
        if ( (node[4:] not in in_branch) or (len(in_branch) > 1) ):
            findCount = findCount - 1
        if (weight < best_wt):
            best_wt = weight
            best_edge = (socket.gethostname(), node)
            report_edge = edge
            ReportProc(request)
        elif ( (weight >= best_wt) and (weight != INFINITY) ):
            ChangeCoreProc()
        elif ( state == FIND ):
            ReportMSG = Message("Report", node, request)
            MsgQueue.appendleft(ReportMSG)
        elif ( (weight == best_wt) and (best_wt == INFINITY) ):
            sys.exit("w = best-wt = infinity")

def ExecChangeCore(request):
    node = request.nodename

    print ('recieved ChangeCore from ' + node)

    ChangeCoreProc()
    
class GetEdges(GHS_pb2_grpc.GallagerServicer):

    def Begin(self, request, context):
        global edges
        global neighbor
        global SE
        global BASIC
        global fragmentLevel
        global fragmentID
        global state
        global SLEEPING
        global waiting_to_connect_to 
        global in_branch
        global best_edge
        global best_wt
        global test_edge
        global MsgQueue

        nodenames = request.nodename
        neighbor = request.neighbors
        weight = request.weights

        for x in neighbor:
            SE[x] = BASIC

        templist = []
        for x in range(0, len(neighbor)):
            edge = (neighbor[x], weight[x])
            templist.append(edge)
        edges[nodenames] = templist

        fragmentLevel = 0
        fragmentID = None
        state = SLEEPING
        findCount = None
        waiting_to_connect_to = None
        best_edge = None
        best_wt = None
        test_edge = None

        return GHS_pb2.MsgAck(status=1, src=nodenames, dst="coordinator" )

    def Finished(self, request, context):
        global finished
        global MsgQueue
        print('recieved finish message')
        MsgQueue.clear()
        finished = True
        return GHS_pb2.Empty()

def initializeWeights(nodename):
    """Read the config file to initialize keyes"""

    global edges
    global numOfNodes

    config = configparser.ConfigParser()
    config.read("config.ini")

    numOfNodes = int(config['gallager']['nodes'])

    for x in range(0,numOfNodes):
        temparr = [int(str_val) for str_val in config['links']['node'+str(x)].split('|')]
        templist = list()
        for y in range(0,numOfNodes):
            if (temparr[y] != 0):
                edge = (y, temparr[y])
                templist.append(edge)
        edges['node'+str(x)] = templist


# Run the server code
def runCoordinator():
    global numOfNodes
    global edges
    global BranchDict
    global finished
    global server

    logging.info(f"Starting {socket.gethostname()}...")
    initializeWeights(socket.gethostname()) 
    time.sleep(10)

    for x in range(0,numOfNodes):
        BranchDict[x] = None
        neighborNodes = []
        weight = []
        for y in edges['node' + str(x)]:
            neighborNodes.append(y[0])
            weight.append(y[1])
        with grpc.insecure_channel('node' + str(x) + ':50050') as channel:
            interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
            intercept_channel = grpc.intercept_channel(channel, *interceptors)
            stub = GHS_pb2_grpc.GallagerStub(intercept_channel)
            message = GHS_pb2.BeginRequest(nodename=('node' + str(x)))
            del message.neighbors[:]
            message.neighbors.extend(neighborNodes)
            del message.weights[:]
            message.weights.extend(weight)
            ack = stub.Begin(message)

    time.sleep(10)

    wakeUpNode = 0 #random.randint(0, numOfNodes)

    with grpc.insecure_channel('node' + str(wakeUpNode) + ':50050') as channel:
        interceptors = (RetryOnRpcErrorClientInterceptor(max_attempts=100, sleeping_policy=ExponentialBackoff(init_backoff_ms=100, max_backoff_ms=1600, multiplier=2), status_for_retry=(grpc.StatusCode.UNAVAILABLE,),),)
        intercept_channel = grpc.intercept_channel(channel, *interceptors)
        stub = GHS_pb2_grpc.MessagingStub(intercept_channel)
        wake = GHS_pb2.WakeUpMSG(nullMSG=0)
        empty = stub.WakeUp(wake)

    GHS_pb2_grpc.add_MessagingServicer_to_server(NodeMessages(), server)
    server.add_insecure_port('[::]:50050')
    server.start()

    while(finished == False):
        x = 0

# Run the client code
def runNodes():
    """The client code."""
    logging.info(f"Starting {socket.gethostname()}...")
    global edges
    global neighbor
    global SE
    global BASIC
    global BRANCH
    global REJECTED
    global finished
    global MsgQueue
    global fragmentLevel
    global fragmentID
    global state
    global waiting_to_connect_to
    global server

    GHS_pb2_grpc.add_GallagerServicer_to_server(GetEdges(), server)
    GHS_pb2_grpc.add_MessagingServicer_to_server(NodeMessages(), server)
    server.add_insecure_port('[::]:50050')
    server.start()

    # Make sure the server has time to start up

    for _ in range(1):
        logging.info(f"{socket.gethostname()}...")
        time.sleep(20)
    pass

    print(edges)

    while(finished == False):
        time.sleep(1)
        if (MsgQueue):
            message = MsgQueue.pop()
            if (message.msgType == "WakeUp"):
                ExecWakeup(request = message.request)
            if (message.msgType == "Connect"):
                ExecConnect(request = message.request)
            if (message.msgType == "Initiate"):
                ExecInitiate(request = message.request)
            if (message.msgType == "Test"):
                ExecTest(request = message.request)
            if (message.msgType == "AcceptReject"):
                ExecAcceptReject(request = message.request)
            if (message.msgType == "Report"):
                ExecReport(request = message.request)
            if (message.msgType == "ChangeCore"):
                ExecChangeCore(request = message.request)
    print ("Finished!")


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s %(message)s', level=logging.DEBUG)

    if socket.gethostname() == "coordinator":
        runCoordinator()
    else:
        # Any node that is not server is a client
        runNodes()