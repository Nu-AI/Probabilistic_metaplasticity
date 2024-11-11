import numpy as np
import matplotlib.pyplot as plt
import numpy.matlib
import multiprocessing
from tqdm import notebook
import json
import copy
from tqdm import trange, tqdm
from multiprocessing import Pool, RLock
import tensorflow as tf
import keras
from keras.datasets import fashion_mnist
from keras.utils import to_categorical

import time
def res_param_config(mean_res, std_res, n_cross, w_hid_max, w_out_max):
	# creating the array with n_cross res states
	states = []
	for i in range(len(mean_res)-1):
		temp = np.ones(n_cross)*mean_res[i]
		for j in range(n_cross):
			temp1 = copy.deepcopy(temp)
			states.append(temp1)
			temp[n_cross-j-1] = mean_res[i+1]
	states.append(np.ones(n_cross)*mean_res[len(mean_res)-1])

	# calculate the parallel equivalent resistance
	p = []
	for state in states:
		temp = 0
		for j in range(len(state)):
			temp = temp + 1/state[j]
		p.append(1/temp)

	# compute the feedback and bias resistance for given weight range
	b_h = np.array([[w_hid_max], [-w_hid_max]])
	b_o = np.array([[w_out_max], [-w_out_max]])
	A = np.array([[1/p[len(p)-1], -1], [1/p[0], -1]])
	x_h = np.matmul(np.linalg.inv(A), b_h)
	x_o = np.matmul(np.linalg.inv(A), b_o)

	R_fh = x_h[0][0]
	R_bh = R_fh/x_h[1][0]
	R_fo = x_o[0][0]
	R_bo = R_fo/x_o[1][0]
	
	return R_fh, R_bh, R_fo, R_bo
	
def res_to_weight(r, R_f, R_b):   
	max_axis = len(r.shape)-1
	r_tot = 1/(np.sum(1/r, axis = max_axis))    
	weight = R_f/r_tot - R_f/R_b
	return weight


def weight_initialize_var(n1, n2, R_f, R_b, n_cross, w_max):
	states = []
	statesP = []
	for i in range(len(mean_res)-1):
		temp = np.ones(n_cross)*mean_res[i]
		tempP = np.ones(n_cross)*i
		for j in range(n_cross):
			temp1 = copy.deepcopy(temp)
			temp1P = copy.deepcopy(tempP)
			states.append(temp1)
			statesP.append(temp1P)
			temp[n_cross-j-1] = mean_res[i+1]
			tempP[n_cross-j-1] = i+1
	states.append(np.ones(n_cross)*mean_res[len(mean_res)-1])
	statesP.append(np.ones(n_cross)*(len(mean_res)-1))
	states = np.array(states)
	statesP = np.array(statesP)             
	w_list = res_to_weight(states, R_f, R_b)
	n_tot = n1*n2
	n_ind1 = np.where((w_list<=-0.5)&(w_list>=-1))
	n_ind2 = np.where((w_list<0)&(w_list>=-0.5))
	n_ind3 = np.where((w_list>=0)&(w_list<0.5))
	n_ind4 = np.where((w_list<=1)&(w_list>=0.5))
	s1 = numpy.random.choice( n_ind1[0] , size = int(n_tot/4), replace = True, p = None)
	s2 = numpy.random.choice( n_ind2[0] , size = int(n_tot/4), replace = True, p = None)
	s3 = numpy.random.choice( n_ind3[0] , size = int(n_tot/4), replace = True, p = None)
	s4 = numpy.random.choice( n_ind4[0] , size = int(n_tot/4), replace = True, p = None)
	ind = numpy.concatenate ((s1, s2, s3, s4), axis = 0, out = None)
	ind_rand = numpy.random.choice( ind , size = int(n_tot), replace = False, p = None)
	r = np.zeros((n_tot, n_cross))
	rP = np.zeros((n_tot, n_cross))
	rP = statesP[ind_rand]
	for i in range(n_res_level):
		loc = np.where(rP==i)
		if len(loc[0])!=0:
			r[loc] = np.random.normal(mean_res[i], std_res[i], len(loc[0]))
	r = np.reshape(r, [n1, n2, n_cross])
	rP = np.reshape(rP, [n1, n2, n_cross])
	w = res_to_weight(r, R_f, R_b)
	return w, r

def infer_level(r_up):
	temp_res = np.matlib.repmat(np.reshape(r_up, (len(r_up),1)),1, n_res_level)
	diff = abs(temp_res-mean_res)
	inferred_level = np.argmin(diff, axis =1)
	return inferred_level

def res_program(r, up_dir):
	r_P = infer_level(r)
	r_P = r_P + up_dir
	r_P[np.where(r_P > len(mean_res)-1)] = len(mean_res)-1
	r_P[np.where(r_P < 0)] = 0
	r = np.zeros_like(r_P)
	for i in range(n_res_level):
		loc = np.where(r_P==i)
		r[loc] = np.random.normal(mean_res[i], std_res[i], len(loc[0]))
	return r 
	
def data_load(load_type):
	if load_type == "p_mnist":
		from mnist.loader import MNIST
		
		loader = MNIST('/home/fatima/Documents/Spiking Code/MNIST') # replace with your MNIST path
		TrainIm_, TrainL_ = loader.load_training()
		TestIm_, TestL_ = loader.load_testing()
	
	if load_type == "mnist":
		import mnist
		
		TrainIm_ = mnist.train_images()
		TrainL_ = mnist.train_labels()
		TestIm_ = mnist.test_images()
		TestL_ = mnist.test_labels()

		TrainIm_ = np.reshape(TrainIm_, [TrainIm_.shape[0],TrainIm_.shape[1]*TrainIm_.shape[2]])
		TestIm_ = np.reshape(TestIm_,[TestIm_.shape[0],TestIm_.shape[1]*TestIm_.shape[2]])
	
	return TrainIm_, TrainL_, TestIm_, TestL_
	
def make_spike_trains(freqs, n_steps):
	''' Create an array of Poisson spike trains
		Parameters:
			freqs: Array of mean spiking frequencies.
			n_steps: Number of time steps
	'''
	r = np.random.rand(len(freqs), n_steps)
	spike_trains = np.where(r <= np.reshape(freqs, (len(freqs),1)), 1, 0)
	return spike_trains

def MNIST_to_Spikes(maxF, im, t_sim, dt):
	''' Generate spike train array from MNIST image.
		Parameters:
			maxF: max frequency, corresponding to 1.0 pixel value
			FR: MNIST image (784,)
			t_sim: duration of sample presentation (seconds)
			dt: simulation time step (seconds)
	'''
	n_steps = int(t_sim / dt) #  sample presentation duration in sim steps
	freqs = im * maxF * dt # scale [0,1] pixel values to [0,maxF] and flatten
	SpikeMat = make_spike_trains(freqs, n_steps)
	return SpikeMat
	
class NumpyEncoder(json.JSONEncoder):
	""" Special json encoder for numpy types """
	def default(self, obj):
		if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
							np.int16, np.int32, np.int64, np.uint8,
							np.uint16, np.uint32, np.uint64)):
			return int(obj)
		elif isinstance(obj, (np.float_, np.float16, np.float32,
							  np.float64)):
			return float(obj)
		elif isinstance(obj, (np.ndarray,)):
			return obj.tolist()
		return json.JSONEncoder.default(self, obj)
		
def check_accuracy(images, labels, w_in, w_out):
	"""Present a set of labeled images to the network and count correct inferences
	:param images: images
	:param labels: labels
	:return: fraction of labels correctly inferred
	"""
	numCorrect = 0

	for u in range(len(images)):
		cnt = np.zeros(n_out)
		spikeMat = MNIST_to_Spikes(MaxF, images[u], tSim, dt_conv)

		# Initialize hidden layer variables
		I1 = np.zeros(n_h1)
		V1 = np.zeros(n_h1)

		# Initialize output layer variables
		I2 = np.zeros(n_out)
		V2 = np.zeros(n_out)

		# Initialize firing time variables
		ts1 = np.full(n_h1, -t_refr)
		ts2 = np.full(n_out, -t_refr)


		for t in range(nBins):
			# Update hidden neuron synaptic currents
			I1 += (dt/t_syn) * (w_in.dot(spikeMat[:, t]) - I1)

			# Update hidden neuron membrane potentials
			V1 += (dt/t_m) * ((V_rest - V1) + I1 * R)
			V1[V1 < -Vth/10] = -Vth/10 # Limit negative potential to -Vth/10

			# Clear membrane potential of hidden neurons that spiked more
			# recently than t_refr
			V1[t*dt - ts1 <= t_refr] = 0

			## Process hidden neuron spikes
			fired = np.nonzero(V1 >= Vth) # Hidden neurons that spiked
			V1[fired] = 0 # Reset their membrane potential to zero
			ts1[fired] = t # Update their most recent spike times

			# Make array of hidden-neuron spikes
			ST1 = np.zeros(n_h1)
			ST1[fired] = 1

			# Update output neuron synaptic currents
			I2 += (dt/t_syn1)*(w_out.dot(ST1) - I2)

			# Update output neuron membrane potentials
			V2 += (dt/t_mH)*((V_rest - V2) + I2*(RH))
			V2[V2 < -VthO/10] = -VthO/10 # Limit negative potential to -Vth0/10

			# Clear V of output neurons that spiked more recently than t_refr
			refr2 = (t*dt - ts2 <= t_refr)
			V2[refr2] = 0

			## Process output spikes
			fired2 = np.nonzero(V2 >= VthO) # output neurons that spikes
			V2[fired2] = 0 # Reset their membrane potential to zero
			ts2[fired2] = t # Update their most recent spike times

			# Make array of output neuron spikes
			ST2 = np.zeros(n_out)
			ST2[fired2] = 1

			cnt += ST2
#         print("the count",cnt)
#         print("target",labels[u])
		if np.count_nonzero(cnt) != 0:  # Avoid counting no spikes as predicting label 0
			prediction = np.argmax(cnt)
			target = labels[u]

			if prediction == target:
				numCorrect += 1

	return numCorrect/len(images)
	
def train_run(params):
	ind_ = params['ind']
	seed = params["seed"]
	U_in = params["U_in"]
	U_out = params["U_out"]

	np.random.seed(2)
	Acc = np.zeros((n_tasks,n_tasks,n_runs))
	#run-stastistic variables initialized
	#up_hid_count_run = np.zeros((n_tasks, n_runs)) #hidden weights to be updated in each task and run
	#up_out_count_run = np.zeros((n_tasks, n_runs)) #output weights to be updated in each task and run
	#up_hid_loopcount_run = np.zeros((n_tasks, n_runs)) #hidden weights update loop accessed
	#up_out_loopcount_run = np.zeros((n_tasks, n_runs)) #output weights update loop accessed
	#hid_l1_count_run = np.zeros((n_tasks, n_runs)) #accumulates #times hidden layer loop 1 is accessed in a task in a run
	#out_l1_count_run = np.zeros((n_tasks, n_runs)) #accumulates #times output layer loop 1 is accessed in a task in a run
	#hid_l2_count_run = np.zeros((n_tasks, n_runs)) #accumulates #times hidden layer loop 2 is accessed in a task in a run
	#out_l2_count_run = np.zeros((n_tasks, n_runs)) #accumulates #times output layer loop 1 is accessed in a task in a run
	#mean_hid_pre_count = np.zeros((n_tasks, n_runs)) # mean #active hidden pre-synaptic neurons 
	#mean_hid_post_count = np.zeros((n_tasks, n_runs)) # mean #active hidden post-synaptic neurons 
	# mean_out_pre_count = np.zeros((n_tasks, n_runs)) # mean #active output pre-synaptic neurons 
	# mean_out_post_count = np.zeros((n_tasks, n_runs)) # mean #active output post-synaptic neurons 
	for run in range(n_runs):
		print("run", run)
		t0 = time.time()
		# Randomly select train and test samples
		trainInd = np.random.choice(len(TrainIm_), n_train, replace=False)
		TrainIm = TrainIm_[trainInd]
		TrainLabels = TrainL_[trainInd]

		testInd = np.random.choice(len(TestIm_), n_test, replace=False)
		TestIm = TestIm_[testInd]
		TestLabels = TestL_[testInd]

		


		# Generate random feedback weights
		w_err_factor = 0.15
		w_err_h1p = ((np.random.rand(n_h1,n_out))*2-1)*w_err_factor # these are random numbers from -1 to 1
		w_err_h1n = w_err_h1p

		# up_hid_count = np.zeros(n_tasks)
		# up_out_count = np.zeros(n_tasks)
		# up_hid_loopcount = np.zeros(n_tasks)
		# up_out_loopcount = np.zeros(n_tasks)

		# c_in_count = np.zeros((n_h1, n_in, n_tasks))
		# c_out_count = np.zeros((n_out, n_h1, n_tasks))

		ttt = []
		for dd in range(n_tasks):
			temp_trainInd = np.concatenate((np.where(TrainLabels == taskID[dd,0])[0],np.where(TrainLabels == taskID[dd,1])[0]),axis=0)
			ttt.append(len(temp_trainInd))
	#
	#with tqdm(total=n_tasks*maxE*int(np.mean(ttt))*nBins,desc="Run {} of params index {}".format(run,ind_),position=ind_) as pbar:




		with tqdm(total=n_tasks*maxE*int(np.mean(ttt))*nBins,desc="Run {} of params index {}".format(run,ind_),position=ind_) as pbar:
			m_in_rec = np.zeros((n_h1, n_in, n_tasks))
			m_out_rec = np.zeros((n_out, n_h1, n_tasks))
			w_in_rec = np.zeros((n_h1, n_in, n_tasks))
			w_out_rec = np.zeros(( n_out, n_h1, n_tasks))
			m_in = np.zeros((n_h1, n_in))   # every run the metaplasticity factors start at 0
			m_out = np.zeros((n_out, n_h1))
			cross_ind_in = 0 
			cross_ind_out = 0

			c_in_count = np.zeros((n_h1, n_in, n_tasks))
			c_out_count = np.zeros((n_out, n_h1, n_tasks))

			for d in range(n_tasks): #n_tasks

				# Generate forward pass weights
				w_in, r_in = weight_initialize_var(n_h1, n_in, R_fh, R_bh, n_cross, w_in_max)
				w_out, r_out = weight_initialize_var(n_out, n_h1, R_fo, R_bo, n_cross, w_out_max)
				# # the task-statistics variables initialized before the start of a task
				# up_hid_loopcount = 0 # accumulates #hidden weight update loop is entered
				# up_out_loopcount = 0 # accumulates #hidden weight update loop is entered
				# up_hid_list = [] #lists #hidden weights to update in a task
				# up_out_list = [] #lists #hidden weights to update in a task
				# hid_l1_count = 0 #accumulates #times hidden layer loop 1 is accessed in a task
				# hid_l2_count = 0 #accumulates #times hidden layer loop 2 is accessed in a task
				# out_l1_count = 0 #accumulates #times output layer loop 1 is accessed in a task
				# out_l2_count = 0 #accumulates #times output layer loop 2is accessed in a task
				# hid_pre_count = 0 #accumulates #hidden layer active pre-synaptic neurons in a task
				# hid_post_count = 0 #accumulates #hidden layer active post-synaptic neurons in a task
				# out_pre_count = 0 #accumulates #output layer active pre-synaptic neurons in a task
				# out_post_count = 0 #accumulates #output layer active post-synaptic neurons in a task

				trainInd = np.concatenate((np.where(TrainLabels == taskID[d,0])[0],np.where(TrainLabels == taskID[d,1])[0]),axis=0)
				n_train2 = len(trainInd)
				trainInd2 = np.random.choice(len(trainInd), n_train2, replace=False)
				trainInd = trainInd[trainInd2]
				taskLabels = TrainLabels[trainInd]
				trainSet = TrainIm[trainInd]
				taskID2 = np.where(taskLabels == taskID[d,1])
				taskLabelsF = np.zeros(len(trainInd));
				taskLabelsF[taskID2] = 1

				n_train2 = len(trainInd)

				for e in range(maxE):
					for u in range(n_train2): #n_train2
						im = trainSet[u]
						fr = im*MaxF
						spikeMat = MNIST_to_Spikes(MaxF, trainSet[u], tSim, dt_conv)
						fr_label = np.zeros(n_out)
						fr_label[int(taskLabelsF[u])] = maxFL # target output spiking frequencies
						s_label = make_spike_trains(fr_label*dt_conv, nBins) # target spikes
						#Xh_in = np.zeros(n_in)

						# Initialize hidden layer variables
						I1 = np.zeros(n_h1)
						V1 = np.zeros(n_h1)
						U1 = np.zeros(n_h1)
						#Xh_hid = np.zeros(n_h1)
						U1_s = np.zeros((n_h1, n_in))

						# Initialize output layer variables
						I2 = np.zeros(n_out)
						V2 = np.zeros(n_out)
						U2 = np.zeros(n_out)
						#Xh_out = np.zeros(n_out)
						U2_s = np.zeros((n_out, n_h1))

						# Initialize error neuron variables
						Verr1 = np.zeros(n_out)
						Verr2 = np.zeros(n_out)

						# Initialize firing time variables
						ts1 = np.full(n_h1, -t_refr)
						ts2 = np.full(n_out, -t_refr)

						for t in range(nBins):
							# Forward pass

							# Find input neurons that spike
							ST0 = spikeMat[:, t]
							fired_in = np.nonzero(ST0)
							#Xh_in = Xh_in + ST0 - Xh_in/t_tr

							# Update synaptic current into hidden layer
							I1 += (dt/t_syn) * (w_in.dot(ST0) - I1)

							# Update hidden layer membrane potentials
							V1 += (dt/t_m) * ((V_rest - V1) + I1 * R)
							V1[V1 < -Vth/10] = -Vth/10 # Limit negative potential

							# If neuron in refractory period, prevent changes to membrane potential
							refr1 = (t*dt - ts1 <= t_refr)
							V1[refr1] = 0

							fired = np.nonzero(V1 >= Vth) # Hidden neurons that spiked
							V1[fired] = 0 # Reset their membrane potential to zero
							ts1[fired] = t # Update their most recent spike times

							ST1 = np.zeros(n_h1) # Hidden layer spiking activity
							ST1[fired] = 1 # Set neurons that spiked to 1
							#Xh_hid = Xh_hid + ST1 - Xh_hid/t_tr

							# Repeat the process for the output layer
							I2 += (dt/t_syn1)*(w_out.dot(ST1) - I2)

							V2 += (dt/t_mH)*((V_rest - V2) + I2*(RH))
							V2[V2 < -VthO/10] = -VthO/10

							refr2 = (t*dt - ts2 <= t_refr)
							V2[refr2] = 0
							fired2 = np.nonzero(V2 >= VthO)

							V2[fired2] = 0
							ts2[fired2] = t

							# Make array of output neuron spikes
							ST2 = np.zeros(n_out)
							ST2[fired2] = 1
							#Xh_out = Xh_out + ST2 - Xh_out/t_tr


							# Compare with target spikes for this time step
							Ierr = (ST2 - s_label[:, t])

							# Update false-positive error neuron membrane potentials
							Verr1 += (dt/t_mE)*(Ierr*RE)
							Verr1[Verr1 < -VthE/10] = -VthE/10 # Limit negative potential to -VthE/10

							## Process spikes in false-positive error neurons
							fired_err1 = np.nonzero(Verr1 >= VthE)
							Verr1[fired_err1] -= VthE

							# Don't penalize "false positive" spikes on the target
							Verr1[int(taskLabelsF[u])] *= FPF

							# Make array of false-positive error neuron spikes
							Serr1 = np.zeros(n_out)
							Serr1[fired_err1] = 1

							# Update false-negative error neuron membrane potentials
							Verr2 -= (dt/t_mE)*(Ierr*RE)
							Verr2[Verr2 < -VthE/10] = -VthE/10

							## Process spikes in false-negative error neurons
							fired_err2 = np.nonzero(Verr2 >= VthE)
							Verr2[fired_err2] -= VthE


							# Make array of false-negative error neuron spikes
							Serr2 = np.zeros(n_out)
							Serr2[fired_err2] = 1


							# Update hidden neuron error compartments (using random weights)
							U1 += (dt/t_mU)*(-U1 + (w_err_h1p.dot(Serr1) - w_err_h1n.dot(Serr2))*RU)

							# Update output neuron error compartments
							U2 += (dt/t_mU)*(-U2 + (Serr1 - Serr2)*RU)



							if len(fired_in[0]) != 0:
								# hid_l1_count += 1
								pre_ind = fired_in
								post_ind = np.nonzero((I1>Imin) & (I1<Imax))
								if len(post_ind[0])>0:
									# hid_l2_count += 1
									UF = U1[post_ind[0]] # np.nozero wraps the array in a tuple
									# hid_post_count += len(post_ind[0])
									# hid_pre_count += len(pre_ind[0])
									#m_up = m_in[np.ix_(post_ind[0], pre_ind[0])]
									#w_up = w_in[np.ix_(post_ind[0], pre_ind[0])]
									#fm_in = np.exp(-(np.abs(m_up*w_up)))
									dw = -lr0*np.matlib.repmat(np.reshape(UF, (len(UF),1)), 1, len(pre_ind[0]))
									U1_s[np.ix_(post_ind[0], pre_ind[0])] += dw   # U1_s accumulates the gradients for hidden weights



							if len(fired[0]) != 0:
								# out_l1_count += 1
								pre_ind = fired
								post_ind = np.nonzero((I2>Imin) & (I2<Imax))
								if len(post_ind[0])>0:
									# out_l2_count += 1
									UF = U2[post_ind[0]]
									# out_post_count += len(post_ind[0])
									# out_pre_count += len(pre_ind[0])
									#m_up = m_out[np.ix_(post_ind[0], pre_ind[0])]
									#w_up = w_out[np.ix_(post_ind[0], pre_ind[0])]
									#fm_out = np.exp(-(np.abs(m_up*w_up)))
									dw = -lr1*np.matlib.repmat(np.reshape(UF, (len(UF),1)), 1, len(pre_ind[0]))
									U2_s[np.ix_(post_ind[0], pre_ind[0])] +=  dw # U2_s accumulates the gradients for hidden weights




							#UF1_ = U1_s/U_in  # dividing by U_in to check threshold crosses
							#UF1_[np.where(UF1_>=0)] = np.floor(UF1_[np.where(UF1_>=0)]).astype(int)
							#UF1_[np.where(UF1_<0)] = np.ceil(UF1_[np.where(UF1_<0)]).astype(int)
							up = np.where(abs(U1_s)>=U_in)

							if len(up[0])>0:
								c_in_count[up[0], up[1], d] += 1		
								# up_hid_loopcount += 1
								# up_hid_list.append(len(up[0]))						
								current_ind = int(cross_ind_in%n_cross)
								cross_ind_in = cross_ind_in+1 
								s = np.sign(U1_s[up]) 
								U1_s[up]=0
								r_in[up[0],up[1],current_ind] = res_program(r_in[up[0],up[1],current_ind], s)
								w_in[up]  = res_to_weight(r_in[up], R_fh, R_bh)



							up = np.where(abs(U2_s)>=U_out)
							if len(up[0])>0:
								c_out_count[up[0], up[1], d] += 1
								# up_out_loopcount += 1
								# up_out_list.append(len(up[0]))							
								current_ind = int(cross_ind_out%n_cross)
								cross_ind_out = cross_ind_out+1 
								s = np.sign(U2_s[up]) 
								U2_s[up]=0
								r_out[up[0],up[1],current_ind] = res_program(r_out[up[0],up[1],current_ind], s)
								w_out[up]  = res_to_weight(r_out[up], R_fo, R_bo)
							pbar.update(1)
						# h_in = np.where(Xh_in>m_th_in)[0]
						# h_hid = np.where(Xh_hid>m_th_hid)[0]
						# h_out = np.where(Xh_out>m_th_out)[0]
						# m_in[np.ix_(h_hid,h_in)] = m_in[np.ix_(h_hid,h_in)] + dm_in
						# m_out[np.ix_(h_out,h_hid)] = m_out[np.ix_(h_out,h_hid)] + dm_out
						# m_in[np.where(m_in > m_in_max)] = m_in_max
						# m_out[np.where(m_out > m_out_max)] = m_out_max

				# task-statistics updated after each task
				# up_hid_count_run[d, run] = np.mean(up_hid_list)
				# up_out_count_run[d, run] = np.mean(up_out_list)
				# up_hid_loopcount_run[d, run] = up_hid_loopcount
				# up_out_loopcount_run[d, run] = up_out_loopcount
				# hid_l1_count_run[d, run] = hid_l1_count
				# out_l1_count_run[d, run] = out_l1_count
				# hid_l2_count_run[d, run] = hid_l2_count
				# out_l2_count_run[d, run] = out_l2_count
				# mean_hid_pre_count[d, run] = hid_pre_count/ hid_l2_count
				# mean_hid_post_count[d, run] = hid_post_count/ hid_l2_count
				# mean_out_pre_count[d, run] = out_pre_count/ out_l2_count
				# mean_out_post_count[d, run] = out_post_count/ out_l2_count




				for d2 in range(d+1):

					testInd = np.concatenate((np.where(TestLabels == taskID[d2,0])[0],np.where(TestLabels == taskID[d2,1])[0]),axis=0)
					taskLabels = TestLabels[testInd]
					testSet = TestIm[testInd]
					taskID2 = np.where(taskLabels == taskID[d2,1])
					taskLabelsT = np.zeros(len(testInd))
					taskLabelsT[taskID2] = 1

					Acc[d2, d, run] = check_accuracy(testSet, taskLabelsT, w_in, w_out )

				m_in_rec[:, :, d] = m_in
				m_out_rec[:, :, d] = m_out
				w_in_rec[:, :, d] = w_in
				w_out_rec[:, :, d] = w_out


		t1 = time.time()
		t_elapsed = t1 - t0
	
		print("Time required to complete run", run, "is", t_elapsed/60, "minutes")
	avg_task_acc = np.mean(Acc,axis=2)
	avg_task_std = np.std(Acc,axis=2)
	class_cont_Acc= np.zeros(n_tasks)
	class_cont_std =np.zeros(n_tasks)
	for i in range(n_tasks):
		class_cont_Acc[i] = avg_task_acc[i,n_tasks-1]
		class_cont_std[i] = avg_task_std[i,n_tasks-1]

	class_Acc= np.zeros(n_tasks)
	class_std =np.zeros(n_tasks)
	for i in range(n_tasks):
		class_Acc[i] = avg_task_acc[i,i]
		class_std[i] = avg_task_std[i,i]
	#print(class_Acc.shape)
	#print(class_Acc[0])
	#print(class_Acc[1])
	cls_mean = (class_Acc[0]+class_Acc[1])/2  
	cont_acc = np.mean(Acc,axis=0)[n_tasks-1]

	mean_cont_acc = np.mean(cont_acc)
	std_cont_acc = np.std(cont_acc)



	results = {'U_in': U_in, 'U_out': U_out, 'class_Acc':class_Acc, 'class_std':class_std, 'class_cont_Acc':class_cont_Acc, 'class_cont_std':class_cont_std, 'cont_mean' : mean_cont_acc, 'cont_std' : std_cont_acc, 'c_in_count':c_in_count, 'c_out_count':c_out_count, 'Acc' : Acc}

	jsonString = json.dumps(results, indent=4, cls=NumpyEncoder)
	s1 = "U_in_"
	s2 = str(U_in)
	s2.replace(".","_")
	s3 = "U_out_"
	s4 = str(U_out)
	s4.replace(".","_")
	name= "mnist_clsacc_"+s1+s2+s3+s4
	filename = "%s.json" % name
	jsonFile = open(filename, "w")
	jsonFile.write(jsonString)
	jsonFile.close()
	#for i in range(n_tasks):
		#print("for tasks no ",i, "the mean and std is ",avg_task_acc[i,i]," ",avg_task_std[i,i])

	

	return cls_mean
	
# def run(config):
# 	return train_run(config)


#weight parameters
lr_factor = 7
w_in_max = 3
w_out_max = 1.5
bit=6
n_level=2**bit
mean_res = np.array([25014, 18022, 13360, 11085, 9118, 6620, 5387, 4670, 4008, 3534]) 
std_res = np.array([2969, 2332, 917.1, 1110, 805.6, 726.2, 412.9, 234, 198.4, 237.5])
n_res_level = len(mean_res)
n_cross = 7
R_fh, R_bh, R_fo, R_bo = res_param_config(mean_res, std_res, n_cross, w_in_max, w_out_max)

# task parameters
n_train = 60000
n_test = 10000
maxE = 1
maxM = 10
n_runs = 5
n_tasks = 5
taskID = np.array([[0, 1], [2, 3], [4, 5], [6,7], [8, 9]])

#Learning rule parameters
Imin = -4
Imax = 4
lr0 = 0.1*lr_factor
lr1 = 1e-3*lr_factor
w_scale0 = 1e-0 # Weight scale in hidden layer
w_scale1 = 1e-0 # Weight scale at output layer
FPF = 1 # inhibits punshing target neuron (only use if training a specific output spike pattern)
d_w_in = w_in_max/n_level
d_w_out = w_out_max/n_level      
# U_in = 0.75 #d_w_in/lr0
# U_out =  0.06   #d_w_out/lr1

# Simulation parameters
tSim = 0.15 # Duration of simulation (seconds)
MaxF = 250
maxFL = 100
dt = 1 # time resolution
dt_conv = 1e-3 # Data is sampled in ms
nBins = int(tSim/dt_conv) #total no. of time steps

# Network architecture parameters
n_h1 = 200  # no. of hidden neurons
dim = 28 # dim by dim is the dimension of the input images
n_in = dim*dim  # no. of input neurons
n_out = 2   # no. of output neurons 
nTrials = n_in


# Neuron parameters
t_syn = 10
t_syn1 = 25
t_m = 15
t_mH = 25
t_mU = 15
t_mE = 10
t_tr = 25
R = 1
RH = 5
RU = 5
RE = 25
Vs = 15
VsO = 10
VsE = 1
V_rest = 0 # Resting membrane potential
t_refr = 4 # Duration of refractory period

Vth = (1/t_m)*R*Vs # Hidden neuron threshold
VthO = (1/t_mH)*RH*VsO # Output neuron threshold
VthE = (1/t_mE)*RE*VsE # Error neuron threshold


U_inL = [0.5]
U_outL =  [0.06]

# loading data
load_type = "mnist"

TrainIm_, TrainL_, TestIm_, TestL_ = data_load(load_type)
TrainIm_ = np.array(TrainIm_) # convert to ndarray
TrainL_ = np.array(TrainL_)
TrainIm_ = TrainIm_ / TrainIm_.max() # scale to [0, 1] interval

TestIm_ = np.array(TestIm_) # convert to ndarray
TestL_ = np.array(TestL_)
TestIm_ = TestIm_ / TestIm_.max() # scale to [0, 1] interval


ind_ = 0
params = []
for i in U_inL:
	for j in U_outL:
		params.append({'ind':ind_, 'U_in':i, 'U_out':j, "seed" : 100})
		ind_+=1

if __name__ == '__main__':

	tqdm.set_lock(RLock())  # for managing output contention
	p = Pool(initializer=tqdm.set_lock, initargs=(tqdm.get_lock(),),processes = int(multiprocessing.cpu_count()/16))
	p.map(train_run, params) # temp_results.append(p.map(train__, params))
	p.close()
	p.join()


	
# #Creation of an hyperparameter problem
# problem = HpProblem()

# # Discrete hyperparameter (sampled with uniform prior)
# problem.add_hyperparameter((0.1, 1.0), "U_in", default_value = 0.7)
# problem.add_hyperparameter((0.01, 0.1), "U_out", default_value = 0.06)

# evaluator = Evaluator.create(
# 	run,
# 	method="thread",
# 	method_kwargs={
# 		"num_workers": 4,
# 		"callbacks": [TqdmCallback()]
# 	},
# )

# # define your search
# search = CBO(problem, evaluator,initial_points = [problem.default_configuration], log_dir = "/home/fatima/Dropbox/Fatima_Research/Server_48/FMNIST_experiments/Acc_Rule/Class/FMNIST_clsres", random_state = 42 )
# print("Starting search....")
# results = search.search(max_evals = 20)


	

