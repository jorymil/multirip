#!/usr/bin/env python
 
# rip_cds.py
# 2014-02-17 jorymil@gmail.com
#
# A python frontend for calling abcde 
# to rip cds from a Sony VGP-XL1B CD changer.

import argparse
import re
import shlex
import subprocess
import sys
import time

MTX = '/usr/sbin/mtx'
ABCDE = '/usr/bin/abcde'
ABCDE_CDDB_CONF = '/home/john/.abcde.cddb'
ABCDE_RIP_CONF  = '/home/john/.abcde.conf'

CONSEC_ERROR_THRESHOLD = 2
UNLOAD_ERROR_THRESHOLD = 2

# Find out which scsi device to use.
# loop through /dev/sg* until we find a
# product id of 'VAIOChanger1'.
scsi_device = ''
for sgid in range(1,10):
    device = "/dev/sg%d" % sgid
    cmd = shlex.split("%s -f %s altres noattach nobarcode inquiry" % (MTX, device)) 
    try:
        out = subprocess.check_output(cmd)
        if re.search('VAIOChanger1', out):
             scsi_device = device
             print "cd changer found: %s" % scsi_device
             break
    except subprocess.CalledProcessError, e:
        sys.stderr.write("Error reading device %s: %s" % (device, e))
        sys.exit(1)


# Now that we know which scsi device to use, 
# we want to find out which slots are occupied.
occupied_slots = []
cmd = shlex.split("%s -f %s altres noattach nobarcode status" % (MTX, scsi_device))
try:
    slots = subprocess.check_output(cmd)
    # Only use slots 1 through 200: 0 (drive) and 201 (import/export slot)
    for line in slots.split('\n'):
        # line syntax: "     Storage Element xxx:Empty/Full"
        # We want to parse out the number and the Empty/Full status.
        # Regexes seem the easiest way to handle this.
        slot_regex = re.compile(r'\s*Storage Element (\d+):(\w+)')
        match_obj = re.match(slot_regex, line)
        if match_obj:
             #print "Regex matches."
             #print dir(match_obj)
             #print match_obj.groups()
             (slot_number, status) = match_obj.groups()
             if status == 'Full':
                 occupied_slots.append(slot_number)
        #print line
    print "Occupied slots: %s" % ', '.join(occupied_slots)
except subprocess.CalledProcessError, e:
    sys.stderr.write("Error scanning device %s: %s" % (scsi_device, e))
    sys.exit(1)

# We now know which slots are occupied.  Loop through them,
# loading each cd, then grabbing its cddb info
slots_with_errors = []
consec_errors = 0
for slot_num in occupied_slots:
    load_cmd = shlex.split("%s -f %s altres noattach nobarcode load %s" % (MTX, scsi_device, slot_num))
    cddb_cmd = shlex.split("%s -c %s" % (ABCDE, ABCDE_CDDB_CONF))
    cdstop_cmd = shlex.split("%s -d %s" % ('cdstop', '/dev/sr1'))
    unload_cmd = shlex.split("%s -f %s altres noattach nobarcode unload %s" % (MTX, scsi_device, slot_num))
    if consec_errors > CONSEC_ERROR_THRESHOLD:
        sys.stderr.write("Reached consecutive error %d: Aborting.\n\n" % consec_errors)
        sys.exit(1)
    print "Loading slot #%s" % slot_num
    try:
        load_proc = subprocess.check_output(load_cmd)
    except subprocess.CalledProcessError, e:
        # Discs don't always load cleanly.  If we get one error, make sure the drive is unloaded and 
        # go to the next drive.  If two errors in a row, something's probably wrong physically, and we
        # need to fix it.
        sys.stderr.write("Unable to load disc from slot #%s: %s\n\n" % (slot_num, e))
    	time.sleep(10)
        consec_errors = consec_errors + 1
        slots_with_errors.append(slot_num)
        occupied_slots.delete(slot_num)
        continue
    try:
        cddb_output = subprocess.check_output(cddb_cmd)
        print cddb_output
        consec_errors = 0
    except:
        sys.stderr.write("Unable to read disc from slot #%s.\n\n" % slot_num)
        slots_with_errors.append(slot_num)
        occupied_slots.delete(slot_num)
    time.sleep(10)
    cdstop_output = subprocess.check_output(cdstop_cmd)
    time.sleep(10)
    print "Unloading slot #%s" % slot_num
    unload_attempts = 0
    while unload_attempts <= UNLOAD_ERROR_THRESHOLD:
        try:
            unload_proc = subprocess.check_output(unload_cmd)
        except subprocess.CalledProcessError, e:
            # Discs don't always unload cleanly.  cdstop, while making sure the drive's actually stopped,
            # causes mtx to returns errors when unloading.  This isn't necessarily a problem.
            # If it happens once, then increment unload_attempts and try again.  After we hit the unload
            # threshold, just increment consec_errors and move on to the next disc.  If we still have problems
            # then, we're in trouble and should exit.
            if unload_attempts < UNLOAD_ERROR_THRESHOLD:
                unload_attempts = unload_attempts + 1
            	time.sleep(10)
            else:
                #sys.stderr.write("Unable to unload disc from slot #%s: %s\n\n" % (slot_num, e))
                consec_errors = consec_errors + 1
                break
    # If we make it this far, we're in good shape!
    consec_errors = 0
    print

