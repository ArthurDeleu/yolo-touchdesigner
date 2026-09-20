#Copyright (c) 2025 Blankensmithing LLC
#This file is licensed under the GNU Affero General Public License v3.0
#(or later), see https://github.com/torinmb/yolo-touchdesigner/blob/master/LICENSE.txt.

import mimetypes
import os
import datetime
import struct
import numpy as np

clients = {}

def onHTTPRequest(webServerDAT, request, response):
	uri = request['uri']

	# If root path requested, return the index file
	if uri == "/":
		response['statusCode'] = 200  # OK
		response['statusReason'] = 'OK'
		response['data'] = op('index').text
		response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
		response['Pragma'] = 'no-cache'
		response['Expires'] = '0'  
		return response

	# Extract only the filename (no folder structure in VFS)
	vfsFilename = os.path.basename(uri)

	# Try to get the file from VFS
	vfsFile = op('virtualFile').vfs[vfsFilename]

	if vfsFile:
		fileContent = vfsFile.byteArray
		fileName = vfsFile.name

		special_filenames = [
			"ort-wasm-simd-threaded.jsep.mjs",
			"ort-wasm-simd-threaded.jsep.wasm"
		]
		for fname in special_filenames:
			if uri.endswith(fname):
				fileContent = vfsFile.byteArray
				mimeType = mimetypes.guess_type(fname, strict=False)[0]
				# Some CDNs expect the correct MIME types
				if fname.endswith(".wasm"):
					mimeType = "application/wasm"
				if fname.endswith(".mjs"):
					mimeType = "application/javascript"
				if not mimeType:
					mimeType = "application/octet-stream"
				response['Content-Type'] = mimeType
				response['statusCode'] = 200
				response['statusReason'] = 'OK'
				response['data'] = fileContent
				response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
				response['Pragma'] = 'no-cache'
				response['Expires'] = '0'    
				return response

		# Guess mime type
		mimeType = mimetypes.guess_type(fileName, strict=False)[0]
		if fileName.endswith('.bin'):
			mimeType = 'application/octet-stream'
		if not mimeType:
			mimeType = 'application/octet-stream'  # fallback

		response['Content-Type'] = mimeType
		response['statusCode'] = 200
		response['statusReason'] = 'OK'
		response['data'] = fileContent
		response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
		response['Pragma'] = 'no-cache'
		response['Expires'] = '0'
		return response

	# File not found
	response['statusCode'] = 404
	response['statusReason'] = 'Not Found'
	response['data'] = b'File not found'
	return response

def ping_loop(webServerDAT, client):
	if client not in clients:
		return
	try:
		webServerDAT.webSocketSendPing(client)
	except:
		pass
	clients[client] = run(ping_loop, webServerDAT, client, delayMilliSeconds=30000)

def onWebSocketOpen(webServerDAT, client, uri):
	op('webserver1').addWarning(f"[{datetime.datetime.now().isoformat()}] Client connected: {client}")
	print(f"[{datetime.datetime.now().isoformat()}] Client connected: {client}")
	op('active_client').text = client
	
	# Start keepalive timer
	clients[client] = run(ping_loop, webServerDAT, client, delayMilliSeconds=30000)
	return

def onWebSocketClose(webServerDAT, client):
	if client in clients:
		# Kill timer
		try: clients[client].kill()
		except: pass
		
		del clients[client]
		op('webserver1').addWarning(f"[{datetime.datetime.now().isoformat()}] Client disconnected: {client}")
		print(f"[{datetime.datetime.now().isoformat()}] Client disconnected: {client}")
		op('active_client').text = ''
	return

predictions = op('predictions')
webcam_list = op('webcam_list')
tick = op('tick')
status = op('status')

def onWebSocketReceiveText(webServerDAT, client, data):
	# Flow Control: acknowledge receipt, unblocking the sender
	
	webServerDAT.store('busy', False)
	
	if '"type":"keepalive"' in data or '"type": "keepalive"' in data:
		return

	if '"type":"sync"' in data or '"type": "sync"' in data:
		if 'tick' in data:
			tick.text = data
		return

	# If we receive results data, dump it directly into the relevant DAT
	# Doing this here as TD 2022.33910 is much faster processing this at the WS server than WS client
	if('type' in data):
		predictions.text = data
	elif('webcamDevices' in data):
		webcam_list.text = data
	elif('tick' in data):
		tick.text = data
	# elif('loading' in data):
	# 	parent().par.State = "Loading"
	elif('loaded' in data):
		parent().par.Loading = 0
	elif('lastFrameTime' in data):
		status.text = data

	else:	
		print('received WS from client: ' +client)
		for key in clients.keys():
			if key != client:
				# print('forwaring WS message to client: ' +key)
				webServerDAT.webSocketSendText(key, data)
	return

segmentation_data = op('../segmentation_data')
depth_data = op('../depth_data')

BINARY_HEADER_BYTES = 16
TYPE_SEGMENTATION = 11
TYPE_DEPTH = 12
DTYPE_FLOAT32 = 2
LAYOUT_HW = 2
PROTOCOL_VERSION = 1

def _copy_float_map(target, stream_name, payload, width, height):
	if target is None or width <= 0 or height <= 0:
		return

	expected_bytes = width * height * 4
	if len(payload) != expected_bytes:
		return

	try:
		# The wire format is explicitly little-endian float32, HWC with one channel.
		arr = np.frombuffer(payload, dtype='<f4', count=width * height).reshape((height, width, 1))
		# TD 2025+: see patch_seg_receiver.py -- copy must happen inside the Script TOP's onCook
		target.store('pending_map', arr.copy())
		target.cook(force=True)
	except Exception as e:
		debug('Failed to receive {} binary map: {}'.format(stream_name, e))

def onWebSocketReceiveBinary(webServerDAT, client, data):
	if len(data) < 8:
		return

	# Versioned float-map header: <BBBBHHII
	if len(data) >= BINARY_HEADER_BYTES:
		msg_type, dtype, layout, version, height, width, _seq, _source_frame = struct.unpack_from('<BBBBHHII', data, 0)
		if (
			msg_type in (TYPE_SEGMENTATION, TYPE_DEPTH)
			and dtype == DTYPE_FLOAT32
			and layout == LAYOUT_HW
			and version == PROTOCOL_VERSION
		):
			payload = memoryview(data)[BINARY_HEADER_BYTES:]
			if msg_type == TYPE_SEGMENTATION:
				_copy_float_map(segmentation_data, 'segmentation', payload, width, height)
			else:
				_copy_float_map(depth_data, 'depth', payload, width, height)
			return

	# Legacy segmentation packet: uint32 width, uint32 height, then FP32.
	width, height = struct.unpack_from('<II', data, 0)
	payload = memoryview(data)[8:]
	_copy_float_map(segmentation_data, 'segmentation', payload, width, height)
	return

def onWebSocketReceivePing(webServerDAT, client, data):
	webServerDAT.webSocketSendPong(client, data=data)
	return

def onWebSocketReceivePong(webServerDAT, client, data):
	return

def onServerStart(webServerDAT):
	return

def onServerStop(webServerDAT):
	return

def send_pings(webServerDAT):
	global clients
	for client in list(clients.keys()):
		try:
			webServerDAT.webSocketSendPing(client)
		except Exception as e:
			# Optionally log or clean up dead clients
			pass
