#!/usr/bin/env python
import pickle
import getopt
import sys
from subprocess import Popen, PIPE
import re
from multiprocessing import Process, Queue
import matplotlib.pyplot as plt

COLORS=['#3194e0', '#49db50', '#e03131']
TITLE_FONT = {'family': 'sans-serif', 'weight': 'bold', 'size': 14}

# Specific to ping on Linux?
def ping(host, qos=0, interval=1, count=5, flood=False, debug_prefix=''):
	"""Method to obtain some basic information about the capture file using the capinfos command."""
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

	# Wait for ping to exit (which is should have already done since readlines got an EOF).
	ret = p.wait()
	if ret != 0:
		# Failed to execute ping. Dump the output ping sent to stderr.
		for line in p.stderr.readlines():
			print line

		return None # No results.

	return result

def do_ping(results_q, experiment_id, host, qos=0, interval=1, count=5, flood=False):
	results = ping(host, qos=qos, interval=interval, count=count, flood=flood, debug_prefix=experiment_id)

	results_q.put((experiment_id, results))

def graph(results):
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
	latency_graph.set_title('Latency', TITLE_FONT)
	latency_graph.set_xlabel('Traffic class')
	latency_graph.set_ylabel('Average (ms)')
	latency_graph.set_xticks([])

	# Create the mean deviation bar graph.
	mdev_graph = fig.add_subplot(2,4,7)
	mdev_graph.set_title('Latency', TITLE_FONT)
	mdev_graph.set_xlabel('Traffic class')
	mdev_graph.set_ylabel('Mean deviation')
	mdev_graph.set_xticks([])

	# For convenience get a ref to the experiment results.
	experiments = results['experiments']

	# Plot the response time data.
	for num,result in enumerate(sorted(experiments)):
		points = [(icmp_seq / (1 / results['ping_interval']), time) for (icmp_seq, ttl, time) in experiments[result]['responses']]
		points = zip(*points)
		ret = ax.scatter(points[0], points[1], c=COLORS[num], s=3, linewidths=0)
		#ret = ax.plot(points[0], points[1], c=COLORS[num])

	# Set the axis since auto leaves too much padding.
	ax.axis(xmin=0,ymin=0,xmax=points[0][-1:][0])

	# Plot the packet loss graph.
	loss = [experiments[key]['summary']['packet_loss'] for key in sorted(experiments)]
	ret = loss_graph.bar([x for x in range(len(loss))], loss, width=1, color=COLORS)

	# Plot the average latency graph.
	latency = [experiments[key]['rtt_summary']['avg'] for key in sorted(experiments)]
	ret = latency_graph.bar([x for x in range(len(latency))], latency, width=1, color=COLORS)

	# Plot the mean deviation graph.
	mdev = [experiments[key]['rtt_summary']['mdev'] for key in sorted(experiments)]
	ret = mdev_graph.bar([x for x in range(len(mdev))], mdev, width=1, color=COLORS)

	# Add the legend.
	plt.legend(ret, [key for key in sorted(experiments)], loc=(1.1,.2))

	plt.show()

def experiment(host, ping_count, ping_interval):
	# Create a queue for receiving the results from the work processes.
	results_q = Queue()

	# Setup the experiments.
	experiments = []
	experiments.append({'args': (results_q, 'Default', '%s'%(host)), 'kwargs': {'qos': 0, 'interval': ping_interval, 'count': ping_count}})
	experiments.append({'args': (results_q, 'High priority', '%s'%(host)), 'kwargs': {'qos': 16, 'interval': ping_interval, 'count': ping_count}})
	experiments.append({'args': (results_q, 'Low priority', '%s'%(host)), 'kwargs': {'qos': 8, 'interval': ping_interval, 'count': ping_count}})

	# Start each experiment.
	for num,experiment in enumerate(experiments):
		w = Process(target=do_ping, args=experiment['args'], kwargs=experiment['kwargs'])
		w.start()

	# A place to store the results.
	results = {}
	results['experiments'] = {}

	# Wait for a result from each experiment and store them.
	for num in range(len(experiments)):
		tmp = results_q.get()
		print "Got results for %(name)s" %{'name': tmp[0]}
		if tmp[1] == None:
			# The ping command failed. Bail.
			print "No results for %(name)s. Exiting." %{'name': tmp[0]}
			raise SystemExit()

		# Store all of the results.
		#results[tmp[0]] = tmp[1]
		results['experiments'][tmp[0]] = tmp[1]

	# Store the host, ping_count and ping_interval in results.
	results['host'] = host
	results['ping_count'] = ping_count
	results['ping_interval'] = ping_interval

	return results

def usage(prog_name):
	output = "Usage: %s [-h HOST [-w FILE ] | -r FILE ] [-i INTERVAL] [-c COUNT]\n" %(prog_name)
	output += "-h HOST: Address of host to ping. Cannot be used with -r.\n"
	output += "-w FILE: Write the results to FILE. Only valid with -h.\n"
	output += "-r FILE: Read results from FILE. Cannot be used with -h.\n"
	output += "-i INTERVAL: Time in seconds between pings. Default .2 seconds.\n"
	output += "-c COUNT: Number of pings to transmit. Default 400.\n"

	return output

if __name__ == '__main__':
	ping_count=400
	ping_interval=.2
	host=None
	write_file = False # Write the results to a file?
	read_file = False # Read results from a file?

	# Process the command line options.
	try:
		opts,args = getopt.getopt(sys.argv[1:], 'h:w:r:c:i:')
	except getopt.GetoptError:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: Unknown argument"
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
		elif o == '-h':
			host = a
		else:
			assert(False)

	# It doesn't make sense to pass -r and -w at the same time.
	if write_file and read_file:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: -r and -w cannot be used together."
		raise SystemExit()

	# No sense in passing -h with -r either.
	if read_file and host:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: -h and -r cannot be used together."
		raise SystemExit()

	# But one of -r or -h must be used.
	if not read_file and not host:
		print >> sys.stderr, usage(sys.argv[0])
		print >> sys.stderr, "Error: Must pass one of -h or -r."
		raise SystemExit()

	# Either do the experiment of get the results from a file.
	if read_file:
		f = open(file, 'r')
		results = pickle.load(f)
		f.close()
	else:
		results = experiment(host, ping_count, ping_interval)

	# Save the results if -w was passed (this is mutally exclusive of -r).
	if write_file:
		f = open(file, 'w')
		pickle.dump(results, f)
		f.close()

	# Grpah the results.
	graph(results)
