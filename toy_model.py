import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits import mplot3d
import matplotlib.cm as cm
from scipy import stats
import itertools

import numba


# speed of light
c = 0.3 # m / ns

# Helper functions

def r2(x, y, x_src, y_src, b_src):
	'''
	path length from src_x, src_y, src_b to sensor at position x, y
	(r_src - r_sensor)^2
	includes finite size of sensor to avoid divide by 0 when scanning (x, y, b)
	'''
	return (x_src-x)**2 + (y_src-y)**2 + b_src**2 + 0.05**2

def arrival_time(x, y, t_src, x_src, y_src, b_src, v=c):
	'''
	expected light arrival time at position x, y given a source at t_src, (x_src, y_src, b_src)
	'''
	return t_src + np.sqrt(r2(x, y, x_src, y_src, b_src))/v

def lambda_d(x, y, x_src, y_src, b_src, N_src):
	'''
	Lambda_d (expected charge) for detector at position x, y given source at (x_src, y_src, b_src) with "energy" N_src
	'''
	return N_src/r2(x, y, x_src, y_src, b_src)


class toy_experiment():

	def __init__(self, detector_xs = np.linspace(-5, 5, 11), num_sen = 121, t_std = 1, noise_lookback=50, noise_lookahead=50, noise_rate=3000):
		self.detector_xs = detector_xs
		self.t_std = t_std
		self.num_sen = int(len(self.detector_xs)**2)
		self.num_row = int(len(self.detector_xs))
		self.noise_lookback = noise_lookback
		self.noise_lookahead = noise_lookahead
		self.noise_rate = noise_rate
		# time PDF factory
		self.time_dist = lambda t: stats.norm(loc=t, scale=self.t_std)

	# PDFs for event generation and likelihood calculation

	def get_p_d(self, x, y, t_src, x_src, y_src, b_src):
		'''
		returns function p_d(t) for detector at position x, y given source at t_src, (x_src, y_src, b_src)
		'''
		return self.time_dist(arrival_time(x, y, t_src, x_src, y_src, b_src))

	def generate_event(self, x_src, y_src, t_src=0, N_src=10, b=1):
		'''
		generates one event

		Parameters:

		x_src : float
			Source x-position
		y_src : float
			Source y-position
		t_src : float
			Source time
		N_src : int
			Amount of photons sent out
		b : float
			Perpendicaulr distance off of sensor plane

		Returns:

		Ns : array
			observed number of photons per detector, observed photon times, x-position of detectors, y-position of detectors, indices of detectors, noise flags
		'''
		Ns = []
		ts = []
		Ns_sensor_idx = []
		Ns_sensor_x = []
		Ns_sensor_y = []
		Ns_sensor_f = []
		for i in range(self.num_sen):
			x_idx = i//self.num_row
			x = self.detector_xs[x_idx]
			y_idx = i%self.num_row
			y = self.detector_xs[y_idx]
			N_exp = lambda_d(x, y, x_src, y_src, b, N_src)
			N_obs = stats.poisson(mu=N_exp).rvs()
			if N_obs > 0:
				Ns.append(N_obs)
				Ns_sensor_x.append(x)
				Ns_sensor_y.append(y)
				Ns_sensor_idx.append(i)
				Ns_sensor_f.append(0)
				pulse_times = self.get_p_d(x, y, t_src, x_src, y_src, b).rvs(size=N_obs)
				pulse_time = np.min(pulse_times)
				ts.append(pulse_time)
		t_min = np.min(ts)
		ts -= t_min
		ts = list(ts)
		t_max = np.max(ts)
		noise_begin = -self.noise_lookback
		noise_end = t_max + self.noise_lookahead
		noise_window_width = noise_end - noise_begin
		#dark_count = self.noise_rate*noise_window_width*self.num_sen*1e-9
		noise_hits = stats.poisson(mu=200).rvs()
		for j in range(noise_hits):
			noise_sen = int(stats.uniform.rvs()*self.num_sen)
			noise_sen_x = self.detector_xs[noise_sen//self.num_row]
			noise_sen_y = self.detector_xs[noise_sen%self.num_row]
			noise_charge = stats.poisson(mu=1).rvs()
			if noise_charge == 0:
				noise_charge = 1
			noise_time = noise_begin + stats.uniform.rvs()*noise_window_width
			if Ns_sensor_idx.count(noise_sen):
				index = Ns_sensor_idx.index(noise_sen)
				Ns_sensor_x[index] = noise_sen_x
				Ns_sensor_y[index] = noise_sen_y
				Ns_sensor_f[index] = 1
				Ns[index] = noise_charge
				ts[index] = noise_time
			else:
				Ns_sensor_x.append(noise_sen_x)
				Ns_sensor_y.append(noise_sen_y)
				Ns_sensor_f.append(1)
				Ns_sensor_idx.append(noise_sen)
				Ns.append(noise_charge)
				ts.append(noise_time)
		N = np.array([Ns, ts, Ns_sensor_x, Ns_sensor_y, Ns_sensor_f]).T
		N = N.astype(np.float32)
		np.random.shuffle(N)
		event = N[:,:-1]
		labels = N[:,-1]
		return event, labels
		#return np.array([Ns, Ns_sensor_x, Ns_sensor_y, Ns_sensor_idx, Ns_sensor_f]).T


	def generate_events(self, N_events, xlims=(-5, 5), ylims = (-5, 5), blims=(-2,2), N_lims=(1,20)):
		'''
		sample source parameters from uniform distribution of x, y, b, and N
		and generate events using those.
		N_events : int
			number of desired events
		*_lims : tuple
			lower and upper bount of the uniform to sample from
		Returns:
		events : list of generated events
		truth : true parameters
		'''

		# truth array x, y, b, N

		x = np.random.uniform(*xlims, N_events)
		y = np.random.uniform(*ylims, N_events)
		b = np.random.uniform(*blims, N_events)
		N = np.random.uniform(*N_lims, N_events)

		truth = np.vstack([x, y, b, N]).T

		events = []
		labels = []

		for i in range(N_events):
			event, label = self.generate_event(x[i], y[i], b=b[i], N_src=N[i])
			events.append(event)
			labels.append(label)
			if (i+1)%100 == 0:
				print(i+1)

		return np.array(events, dtype=object), np.array(labels, dtype=object), truth

	def plot_event(self, event):
		'''
		Plot 3D bar chart of event where bar height is observed energy of a sensor and color is observed pulse time.
		'''
		N = event
		N = N[N[:,3].argsort()]
		x = N[:,2]
		y = N[:,3]
		z = np.zeros_like(x)
		dx = 1
		dy = 1
		dz = N[:,0]
		ts = N[:,1]
		max = np.max(ts)
		min = np.min(ts)
		window = max - min
		labels = [min + window*x for x in np.linspace(0,1,6)]
		labels = [f'{i:.2f}' for i in labels]
		cmap = cm.get_cmap('jet')
		colors = [cmap((k - min)/(max - min)) for k in ts]
		fig = plt.figure()
		ax = plt.axes(projection='3d')
		cbar = fig.colorbar(plt.cm.ScalarMappable(cmap='jet'), ax=ax)
		cbar.ax.set_yticklabels(labels)
		cbar.set_label('Hit Time [ns]', rotation=270)
		ax.bar3d(x, y, z, dx, dy, dz, color=colors)
		ax.set_xlim([-6, 6])
		ax.set_ylim([-6, 6])
		ax.set_xlabel('x-position [m]')
		ax.set_ylabel('y-position [m]')
		ax.set_zlabel('# of photons')
		plt.show()

	def plot_noise(self, event, label):
		'''
		Plot 2D array of sensors with indicators for noise. Color indicates hit time.
		'''
		N = event
		times = N[:,1]
		min = np.min(times)
		max = np.max(times)
		window = max - min
		labels = [min + window*x for x in np.linspace(0,1,6)]
		labels = [f'{i:.2f}' for i in labels]
		x = N[:,2]
		y = N[:,3]
		noise = np.argwhere(label)
		noise_x = N[noise,2]
		noise_y = N[noise,3]
		cmap = cm.get_cmap('jet')
		fig, ax = plt.subplots()
		colors = [cmap((k - min)/(max - min)) for k in times]
		cbar = fig.colorbar(plt.cm.ScalarMappable(cmap='jet'), ax=ax)
		cbar.ax.set_yticklabels(labels)
		cbar.set_label('Hit Time [ns]', rotation=270)
		ax.scatter(x, y, c=colors, s=250)
		ax.plot(noise_x, noise_y, 'k*', markersize=10, label='noise')
		ax.set_xlim([-6, 6])
		ax.set_ylim([-6, 6])
		ax.set_xlabel('x-position [m]')
		ax.set_ylabel('y-position [m]')
		ax.legend()
		plt.show()

	def plot_times(self, event, label, pred_label):
		'''
		Plots hit times and noise times on a 1D plot
		'''
		sig_idx = np.nonzero((pred_label<0.5) & (label<0.5))
		sig = event[0,sig_idx,1].ravel()
		noise_idx = np.nonzero((pred_label>0.5) & (label>0.5))
		noise = event[0,noise_idx,1].ravel()
		bad_sig_idx = np.nonzero((pred_label>0.5) & (label<0.5))
		bad_sig = event[0,bad_sig_idx,1].ravel()
		bad_noise_idx = np.nonzero((pred_label<0.5) & (label>0.5))
		bad_noise = event[0,bad_noise_idx,1].ravel()
		plt.hlines(1, np.min(event[0,:,1])-1, np.max(event[0,:,1])+1)
		plt.eventplot(sig, colors='b', label=f'signal tagged correctly: {len(sig)}', linewidths=0.5)
		plt.eventplot(noise, colors='r', label=f'noise tagged correctly: {len(noise)}', linewidths=0.5)
		plt.eventplot(bad_sig, colors='g', label=f'signal tagged incorrectly: {len(bad_sig)}', linewidths=0.5)
		plt.eventplot(bad_noise, colors='c', label=f'noise tagged incorrectly: {len(bad_noise)}', linewidths=0.5)
		plt.xlabel('ns')
		plt.title('Hit Times')
		plt.legend(loc='best')
		plt.show()

	def plot_energies(self, event, label, pred_label):
		'''
		Plots hit energies and noise energies on a 1D plot
		'''
		sig_idx = np.nonzero((pred_label<0.5) & (label<0.5))
		sig = event[0,sig_idx,0].ravel()
		noise_idx = np.nonzero((pred_label>0.5) & (label>0.5))
		noise = event[0,noise_idx,0].ravel()
		bad_sig_idx = np.nonzero((pred_label>0.5) & (label<0.5))
		bad_sig = event[0,bad_sig_idx,0].ravel()
		bad_noise_idx = np.nonzero((pred_label<0.5) & (label>0.5))
		bad_noise = event[0,bad_noise_idx,0].ravel()
		plt.hlines(1, np.min(event[0,:,0]), np.max(event[0,:,0]))
		plt.eventplot(sig, colors='b', label=f'signal identified correctly: {len(sig)}', linewidths=0.5)
		plt.eventplot(noise, colors='r', label=f'noise identified correctly: {len(noise)}', linewidths=0.5)
		plt.eventplot(bad_sig, colors='g', label=f'signal identified incorrectly: {len(bad_sig)}', linewidths=0.5)
		plt.eventplot(bad_noise, colors='c', label=f'noise identified inccorectly: {len(bad_noise)}', linewidths=0.5)
		plt.xlabel('Energy [arb]')
		plt.title('Energies of Hits')
		plt.legend(loc='best')
		plt.show()

	def plot_q_vs_t(self, event, label, pred_label):
		'''
		Plots hit energy vs hit time
		'''
		sig_idx = np.nonzero((pred_label<0.5) & (label<0.5))
		sig_t = event[0, sig_idx, 1].ravel()
		sig_q = event[0, sig_idx, 0].ravel()
		noise_idx = np.nonzero((pred_label>0.5) & (label>0.5))
		noise_t = event[0, noise_idx, 1].ravel()
		noise_q = event[0, noise_idx, 0].ravel()
		bad_noise_idx = np.nonzero((pred_label<0.5) & (label>0.5))
		bad_noise_t = event[0, bad_noise_idx, 1].ravel()
		bad_noise_q = event[0, bad_noise_idx, 0].ravel()
		bad_sig_idx = np.nonzero((pred_label>0.5) & (label<0.5))
		bad_sig_t = event[0, bad_sig_idx, 1].ravel()
		bad_sig_q = event[0, bad_sig_idx, 0].ravel()

		plt.scatter(sig_t, sig_q, s=2, c='b', label=f'signal tagged correctly: {len(sig_t)}')
		plt.scatter(noise_t, noise_q, s=2, c='r', label=f'noise tagged correctly: {len(noise_t)}')
		plt.scatter(bad_sig_t, bad_sig_q, s=2, c='g', label=f'signal tagged incorrectly: {len(bad_sig_t)}')
		plt.scatter(bad_noise_t, bad_noise_q, s=2, c='c', label=f'noise tagged incorrectly: {len(bad_noise_t)}')
		plt.title('Energy vs Hit Time')
		plt.xlabel('Hit Time [ns]')
		plt.ylabel('Energy [pe]')
		plt.legend(loc='best')
		plt.show()

def pad_events(events):
	'''
	Zero pads each event so that all events have the same dimensions.
	'''
	n_events = len(events)
	n_max = max([event.shape[0] for event in events])
	padded = np.zeros((n_events, n_max, events[0].shape[1]))
	for i in range(n_events):
		slc = (i,) + tuple(slice(shp) for shp in events[i].shape)
		padded[slc] = events[i]
	return padded.astype(np.float32)

def pad_labels(labels):
	'''
	Zero pads each label so that all labels have the same length.
	'''
	n_labels = len(labels)
	n_max = max([label.shape[0] for label in labels])
	padded = np.zeros((n_labels, n_max))
	for i in range(n_labels):
		slc = (i,) + tuple(slice(shp) for shp in labels[i].shape)
		padded[slc] = labels[i]
	return padded.astype(np.float32)

def normalize(events):
	'''
	Normalizes event features by subtracting the mean and dividing by the standard deviation of each event feature
	'''
	means = []
	stds = []
	for i in range(events[0].shape[1]):
		all = [e[:,i] for e in events]
		mean = np.mean(list(itertools.chain(*all)))
		means.append(mean)
		std = np.std(list(itertools.chain(*all)))
		stds.append(std)
	norm_events = [(e - means)/stds for e in events]
	return np.array(norm_events, dtype=object)
