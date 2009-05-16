#!/usr/bin/env python
# Dan Siemon <dan@coverfire.com>
# April 2009
# License: Affero GPLv3
import pickle
import random
import getopt
import sys
import time
from subprocess import Popen, PIPE
import re
from multiprocessing import Process, Queue

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

class Colors(object):
	"""Class to manage a list of colors for the graph."""
	def __init__(self):
		# Pick the first few colors so at least they look good.
		self.colors=['#3194e0', '#49db50', '#e03131', '#e1a127', '#bf35e1', '#3db7b0']

	def _expand_list(self, num_elements):
		"""Function to expand the color list with random colors so that there are at least num_elements colors."""
		for i in range(len(self.colors), num_elements):
			c = "#%02x%02x%02x" %(random.randrange(0,255,1), random.randrange(0,255,1), random.randrange(0, 255, 1))
			self.colors.append(c)

	def __getitem__(self, index):
		self._expand_list(index+1) # Need index+1 elements in the array to get element at index.

		return self.colors[index]

	def list(self, size):
		"""Function to return a list of colors of length size."""
		# First ensure the list has enough elements.
		self._expand_list(size)

		return self.colors[:size]

def ping(host, qos=0, interval=1, count=5, flood=False, debug_prefix=''):
	"""Function to run the ping command and extract the results; may be Linux specific."""
	result = {}
	result['responses'] = []

	# Regular expressions to obtain the information from ping's output.
	response_re = re.compile('icmp_seq=(?P<icmp_seq>\d+) ttl=(?P<ttl>\d+) time=(?P<time>\d+(\.\d+|)) ms')
	summary_re = re.compile('(?P<transmitted>\d+) packets transmitted, (?P<received>\d+) received, (\+(?P<errors>\d+) errors, |)(?P<packet_loss>\d+)% packet loss, time (?P<time>\d+(\.\d+|))ms')
	rtt_summary_re = re.compile('rtt min/avg/max/mdev = (?P<min>\d+(\.\d+|))/(?P<avg>\d+(\.\d+|))/(?P<max>\d+(\.\d+|))/(?P<mdev>\d+(\.\d+|)) ms')

	# Construct the arguments to Popen.
	args = ['ping'] # The binary to execute.
	args.append('-i %.3f'%(interval))
	args.append('-Q %i'%(int(qos)))
	args.append('-c %i'%(count))
	if flood:
		args.append('-f')
	args.append(host)

	# Run the ping command.
	try:
		p = Popen(args, shell=False, stdout=PIPE, stderr=PIPE)
	except OSError:
		# Could not execute
		return None

	# Extract the required fields as they are output by ping.
	for line in p.stdout.readlines():
		line = line.rstrip()
		#print debug_prefix, line

		# Match the response lines.
		m = response_re.search(line)
		if m != None:
			result['responses'].append((int(m.group('icmp_seq')), int(m.group('ttl')), float(m.group('time'))))

		# Match the packet summary line.
		m = summary_re.search(line)
		if m != None:
			result['summary'] = {'transmitted': int(m.group('transmitted')),
						'received': int(m.group('received')),
						'packet_loss': int(m.group('packet_loss')),
						'time': float(m.group('time'))}

		# Match the RTT summary line.
		m = rtt_summary_re.search(line)
		if m != None:
			result['rtt_summary'] = {'min': float(m.group('min')),
						'avg': float(m.group('avg')),
						'max': float(m.group('max')),
						'mdev': float(m.group('mdev'))}

	# Wait for ping to exit (which is should have already happened since readlines got an EOF).
	# 0 - At least one response received.
	# 1 - No responses received. DNS lookup etc was OK. Still get summary line.
	# 2 - Error.
	ret = p.wait()
	if ret >= 2:
		# Ping failed. Dump the output ping sent to stderr.
		for line in p.stderr.readlines():
			print line

		return None # No results.
	elif ret == 1:
		# Need to populate empty summary result fields since ping doesn't output them in this case.
		result['rtt_summary'] = {'min': 0.0, 'avg': 0.0, 'max': 0.0, 'mdev': 0.0}

	return result

def do_ping(results_q, experiment_id, host, qos=0, interval=1, count=5, flood=False):
	"""Function which is executed as a process to run the ping experiment."""
	results = ping(host, qos=qos, interval=interval, count=count, flood=flood, debug_prefix=experiment_id)

	# Store details about this experiment in the results.
	results['host'] = host
	results['qos'] = qos

	results_q.put((experiment_id, results))

def graph(results, line_graph=False, image_file=None):
	"""Function to graph the results of a ping experiment."""
	TITLE_FONT = {'family': 'sans-serif', 'weight': 'bold', 'size': 14}
	colors = Colors()

	# Create the figure.
	fig = plt.figure(figsize=(10,6), facecolor='w')
	fig.subplots_adjust(left=0.09, right=0.96, top=0.92, bottom=0.07, wspace=.4, hspace=.4)

	# Create the response time graph.
	ax = fig.add_subplot(2,1,1)
	ax.set_title('Latency vs time', TITLE_FONT)
	ax.set_xlabel('Time (s)')
	ax.set_ylabel('Latency (ms)')

	# Create the packet loss bar graph.
	loss_graph = fig.add_subplot(2,4,5)
	loss_graph.set_title('Packet loss', TITLE_FONT)
	loss_graph.set_xlabel('Traffic class')
	loss_graph.set_ylabel('Packet loss (%)')
	loss_graph.set_xticks([])

	# Create the average latency graph.
	latency_graph = fig.add_subplot(2,4,6)
	latency_graph.set_title('Latency avg', TITLE_FONT)
	latency_graph.set_xlabel('Traffic class')
	latency_graph.set_ylabel('Average (ms)')
	latency_graph.set_xticks([])

	# Create the mean deviation bar graph.
	mdev_graph = fig.add_subplot(2,4,7)
	mdev_graph.set_title('Latency mdev', TITLE_FONT)
	mdev_graph.set_xlabel('Traffic class')
	mdev_graph.set_ylabel('Mean deviation (ms)')
	mdev_graph.set_xticks([])

	# For convenience get a ref to the experiment results.
	experiments = results['experiments']

	# Plot the response time data.
	for num,result in enumerate(sorted(experiments)):
		if len(experiments[result]['responses']) == 0:
			# No ping responses were received. 100% loss. No points to graph.
			continue

		points = [(icmp_seq / (1 / results['ping_interval']), time) for (icmp_seq, ttl, time) in experiments[result]['responses']]
		points = zip(*points)
		if line_graph:
			ret = ax.plot(points[0], points[1], c=colors[num], linewidth=0.6)
		else:
			ret = ax.scatter(points[0], points[1], c=colors[num], s=3, linewidths=0)

	# Set the axis since auto leaves too much padding.
	ax.axis(xmin=0,ymin=0,xmax=points[0][-1:][0])

	# Plot the packet loss graph.
	loss = [experiments[key]['summary']['packet_loss'] for key in sorted(experiments)]
	ret = loss_graph.bar([x for x in range(len(loss))], loss, width=1, color=colors.list(len(loss)))

	# Plot the average latency graph.
	latency = [experiments[key]['rtt_summary']['avg'] for key in sorted(experiments)]
	ret = latency_graph.bar([x for x in range(len(latency))], latency, width=1, color=colors.list(len(latency)))

	# Plot the latency mean deviation graph.
	mdev = [experiments[key]['rtt_summary']['mdev'] for key in sorted(experiments)]
	ret = mdev_graph.bar([x for x in range(len(mdev))], mdev, width=1, color=colors.list(len(mdev)))

	# Add the legend.
	plt.legend(ret, [key for key in sorted(experiments)], loc=(1.1,0))

	# Write out the image if requested otherwise show it.
	if image_file:
		canvas = FigureCanvas(fig)
                canvas.print_png(image_file)
	else:
		plt.show()

def experiment(ping_count, ping_interval, target_list):
	"""Function to define and run the ping experiment."""
	# Create a queue for receiving the results from the work processes.
	results_q = Queue()

	# Setup the experiments.
	experiments = []
	for target in target_list:
		experiments.append({'args': (results_q, target[0], target[1]), 'kwargs': {'qos': target[2], 'interval': ping_interval, 'count': ping_count}})

	# Start each experiment.
	for num,experiment in enumerate(experiments):
		w = Process(target=do_ping, args=experiment['args'], kwargs=experiment['kwargs'])
		w.start()

	# A place to store the results.
	results = {}
	results['experiments'] = {}
	results['start-time'] = time.time() # Store approximately when the experiment started.

	# Wait for a result from each experiment and store them.
	for num in range(len(experiments)):
		tmp = results_q.get()
		print "Got results for %(name)s" %{'name': tmp[0]}
		if tmp[1] == None:
			# The ping command failed. Bail.
			print "No results for %(name)s. Exiting." %{'name': tmp[0]}
			raise SystemExit()

		# Store all of the results.
		results['experiments'][tmp[0]] = tmp[1]

	# Store (roughly) when the experiment ends.
	results['end-time'] = time.time()

	# Store the ping_count and ping_interval in results. These are global values.
	results['ping_count'] = ping_count
	results['ping_interval'] = ping_interval

	return results

def usage(prog_name):
	output = \
	"""
Usage: %s [-t TARGET [-w FILE ] | -r FILE ] [-i INTERVAL] [-c COUNT]
	  [-l] [-o FILE]"
-t TARGET: Specify the ping target information. TARGET string is 'ID,FQDN,TOS'
	   (see below). Cannot be used with -r.
-w FILE: Write the results to FILE. Only valid with -t.
-r FILE: Read results from FILE. Cannot be used with -t.
-i INTERVAL: Time in seconds between pings. Default .2 seconds.
-c COUNT: Number of pings to transmit. Default 400.
-o FILE: Name of a file to output a PNG of the graph to.
-l: Plot a line graph instead of a scatter plot.

TARGET: Experiment identifier,host or IP to ping,TOS field value.
	""" %(prog_name)

	return output

if __name__ == '__main__':
	ping_count=400
	ping_interval=.2
	targets=[]
	line_graph=False
	write_file = False # Write the results to a file?
	read_file = False # Read results from a file?
	image_filename=None

	# Process the command line options.
	try:
		opts,args = getopt.getopt(sys.argv[1:], 't:w:r:c:i:o:l')
	except getopt.GetoptError:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: Unknown argument."
		raise SystemExit()

	for o,a in opts:
		if o == '-w':
			write_file = True
			file = a
		elif o == '-r':
			read_file = True
			file = a
		elif o == '-c':
			ping_count = int(a)
		elif o == '-i':
			ping_interval = float(a)
		elif o == '-t':
			target_info = a.split(',')
			if len(target_info) != 3:
				print >> sys.stderr, usage(sys.argv[0])
				print >> sys.stderr, "Error: Invalid target format."
				raise SystemExit()

			targets.append(a.split(','))
			targets = [(t[0].strip(),t[1].strip(),t[2].strip())  for t in targets]
			targets = [(t[0].rstrip(),t[1].rstrip(),t[2].rstrip())  for t in targets]
		elif o == '-o':
			image_filename = a
		elif o == '-l':
			line_graph = True
		else:
			assert(False)

	# It doesn't make sense to pass -r and -w at the same time.
	if write_file and read_file:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: -r and -w cannot be used together."
		raise SystemExit()

	# No sense in passing -t with -r either.
	if read_file and (targets != []):
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: -t and -r cannot be used together."
		raise SystemExit()

	# But one of -r or -t must be used.
	if not read_file and not (targets != []):
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: Must pass one of -t or -r."
		raise SystemExit()

	# Either get the results from a file or do the experiment.
	if read_file:
		f = open(file, 'r')
		results = pickle.load(f)
		f.close()
	else:
		results = experiment(ping_count, ping_interval, targets)

	# Save the results if -w was passed (this is mutally exclusive of -r).
	if write_file:
		f = open(file, 'w')
		pickle.dump(results, f)
		f.close()

	# Graph the results.
	if image_filename:
		f = open(image_filename, 'w')
		graph(results, line_graph=line_graph, image_file=f)
		f.close()
	else:
		graph(results, line_graph=line_graph)
