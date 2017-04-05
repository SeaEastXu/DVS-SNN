#########
# IMPORTS
#########
import sys
import paer
from brian2 import *
import matplotlib as mpl
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

###########
# FUNCTIONS
###########
def get_data(file, max=10**60):
    aefile = paer.aefile(file, max_events=max+1)
    aedata = paer.aedata(aefile)
    aetime = (aefile.timestamp[-1]-aefile.timestamp[0])
    print 'Points: %i, Time: %0.2f us' % (len(aefile.data), aetime)
    return aedata, aetime

######
# MAIN
######

# start the scope for Brian
start_scope()
defaultclock.dt = 1*us


# INPUTS ########################################################################################
'''Assumptions: - Polarity not taken into account'''

# do we consider the polarity of the data?
polarity = False

# read the DVS dile
filename = 'mnist_0_scale16_0001.aedat'
data, aetime = get_data('DVS-datasets/' + filename)

# number of input neurons (2*128*128)
DVSlen  = 128
DVSsize = DVSlen**2
indices = []
spikes  = []
limit   = DVSsize - 1
minSpikes = min(data.ts)
if polarity:
    for x in xrange(0, len(data.y)):
        if data.t[x] == 0: # P = 0
            indices.append(int(((data.y[x] - 1) * DVSlen + data.x[x]) - 1))
            spikes.append(int(data.ts[x] - minSpikes + 1000))

        else: # P = 1
            indices.append(int(((data.y[x] - 1) * DVSlen + data.x[x]) - 1 + limit))
            spikes.append(int(data.ts[x] - minSpikes + 1000))

else:
    for x in xrange(0, len(data.y)):
        indices.append(int(((data.y[x] - 1) * DVSlen + data.x[x]) - 1))
        spikes.append(int(data.ts[x] - minSpikes + 1000))


# correct the data file for possible errors (repetitions)
indicesSameTime = []
indices2 = []
spikes2  = []
cntError = 0
timeDt   = spikes[0]
for x in xrange(0, len(spikes)-1):

    # extend the vector with the neurons firing in this dt
    if spikes[x] == timeDt:
        indicesSameTime.append(indices[x])

    # check for repetitions in the current dt
    if spikes[x+1] != timeDt:

        # vector of unique neurons
        uniqueIndices = []
        for z in xrange(0, len(indicesSameTime)):
            flag = 0
            for zz in xrange(0, len(uniqueIndices)):
                if indicesSameTime[z] == uniqueIndices[zz]:
                    flag = 1
                    break
            if flag == 0:
                uniqueIndices.append(indicesSameTime[z])

        indices2.extend(uniqueIndices)
        spikes2.extend([timeDt for z in xrange(0, len(uniqueIndices))])
        if len(uniqueIndices) != len(indicesSameTime):
            cntError +=1
        indicesSameTime = []
        timeDt = spikes[x+1]
print "Errors: %s\n" % cntError

# create Brian group for the inputs
if polarity: I = SpikeGeneratorGroup(2*DVSsize, indices2, spikes2*us)
else:        I = SpikeGeneratorGroup(DVSsize, indices2, spikes2*us)

# monitor the input spike train
Minput = SpikeMonitor(I)

# report state of the script
print "-> I: Input layer created."


# FIRST CONVOLUTIONAL LAYER #####################################################################
'''Receptive fields: 4x4 with overlap 1
   Neuronal maps: 8'''

RFc1len    = 4              # length of the side of the receptive field
RFc1size   = RFc1len**2     # size of the receptive field
RFc1lenmax = 32             # max length of the side of the receptive field
nMapsc1    = 8              # number of neural maps in this convolutional layer
overlap    = 2              # overlap type for the receptive fields of this layer

# check receptive fields
if RFc1len%2 != 0 or RFc1len > RFc1lenmax:
    print "\nError: the length of the RF has to be even and smaller than 32 pixels."
    sys.exit()

# number of neurons in the convolutional layer
if overlap != 1 and overlap != 2 and overlap != RFc1len:
    print "\nError: overlap can only be 1 (75%), 2 (50%), or RFc1len (0%)."
    sys.exit()
elif overlap == 1:
    nC1 = (DVSlen + 1 - RFc1len)**2 * nMapsc1
elif overlap == 2:
    nC1 = ((DVSlen - RFc1len) / 2 + 1)**2 * nMapsc1
else:
    nC1 = DVSsize / RFc1size * nMapsc1

# first layer of neurons
tau = 10*ms
eqs = '''
dv/dt = (-v)/tau : 1 (unless refractory)
'''
C1 = NeuronGroup(nC1, eqs, threshold='v>5', reset='v = 0', refractory='5*ms', method='linear')
spikemon = SpikeMonitor(C1)
M = StateMonitor(C1, 'v', record=False)

# report state of the script
print "-> C1: Convolutional layer created."


# SYNAPSES: INPUT - C1 ##########################################################################

# synapses between the input and first convolutional (neural maps not included)
idxRF  = 0
connectIC1     = np.zeros((RFc1size * nMapsc1, DVSsize))
cntConnections = np.zeros(DVSsize)
connectIC1.fill(-1)

cntRow = 0
cntCol = 0
flapOverlapCol = 1
cntOverlapCol  = 0
flapOverlapRow = 1
cntOverlapRow  = 0
for nIdx in xrange(0, DVSsize):

    # check if a new RF should be included here
    if flapOverlapCol and flapOverlapRow:

        # get the location on the image
        DVSrow = nIdx / DVSlen
        DVScol = nIdx - DVSrow * DVSlen

        # check if we can fit a new RF at this location
        if DVScol + RFc1len <= DVSlen and DVSrow + RFc1len <= DVSlen:

            # check the indices included in this RF
            for rRF in xrange(0, RFc1len):
                for cRF in xrange(0, RFc1len):
                    auxIdx = (DVSrow + rRF) * DVSlen + (DVScol + cRF)
                    connectIC1[cntConnections[auxIdx]][auxIdx] = idxRF
                    cntConnections[auxIdx] += 1

            # update the RF counter
            idxRF += 1

    # update flagOverlap
    cntOverlapCol += 1
    if cntOverlapCol != overlap and flapOverlapCol:
        flapOverlapCol = 0
    elif cntOverlapCol == overlap:
        flapOverlapCol = 1
        cntOverlapCol  = 0

    # update counters
    if cntCol == DVSlen - 1:
        cntCol  = 0
        cntRow += 1
        flapOverlapCol = 1
        cntOverlapCol  = 0

        cntOverlapRow += 1
        if cntOverlapRow != overlap and flapOverlapRow:
            flapOverlapRow = 0
        elif cntOverlapRow == overlap:
            flapOverlapRow = 1
            cntOverlapRow = 0
    else:
        cntCol += 1

# augment the indices to other neural maps
for nIdx in xrange(0, DVSsize):
    aux = int(cntConnections[nIdx])
    for mIdx in xrange(1, nMapsc1):
        for l in xrange(0, aux):
            connectIC1[int(cntConnections[nIdx])][nIdx] = nC1 / nMapsc1 * mIdx + connectIC1[l, nIdx]
            cntConnections[nIdx] += 1

# prepare data for the simulator
# connectIC1dir = []
# connectIC1inp = []
# for nIdx in xrange(0, DVSsize):
#     connectIC1inp.append(nIdx)
#     aux = []
#     for c1Idx in xrange(0, int(cntConnections[nIdx])):
#         aux.append(int(connectIC1[c1Idx, nIdx]))
#     connectIC1dir.append(aux)

connectIC1dir = []
connectIC1inp = []
for nIdx in xrange(0, DVSsize):
    for c1Idx in xrange(0, int(cntConnections[nIdx])):
        connectIC1inp.append(nIdx)
        connectIC1dir.append(int(connectIC1[c1Idx, nIdx]))

# synapses (DVS-C1)
taupre  = 16.8*ms
taupost = 33.7*ms
wmax = 1
Apre = 0.03125
Apost = -0.85*Apre

S_IC1 = Synapses(I, C1,
             '''
             w : 1
             dapre/dt = -apre/taupre : 1 (event-driven)
             dapost/dt = -apost/taupost : 1 (event-driven)
             ''',
             on_pre='''
             v_post += w
             apre += Apre
             w = clip(w+apost, 0, wmax)
             ''',
             on_post='''
             apost += Apost
             w = clip(w+apre, 0, wmax)
             ''', method='linear')

S_IC1.connect(i = connectIC1inp, j = connectIC1dir)

# report state of the script
print "-> S_IC1: Synapses I-C1 created."

# we need the weights of these neural maps (WEIGHT SHARING)
weightsC1 = np.random.uniform(0, 1, 8)

# assing the weights to the synapses
for mIdx in xrange(0, nMapsc1):
    S_IC1.w[:, nC1 / nMapsc1 * mIdx : nC1 / nMapsc1 * (mIdx + 1)] = weightsC1[mIdx]

# report state of the script
print "-> S_IC1: Weight sharing."

# RUN THE SIMULATION & PLOTS ####################################################################
# run((max(spikes2) + 1000)*us, report='text')