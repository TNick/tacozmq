# -*- coding: utf-8 -*-
"""
Intermediates the access to the file system for our app.
"""
from __future__ import unicode_literals
from __future__ import print_function

import os
import logging
import time
import threading
import sys
import uuid

from taco.constants import *
from taco.utils import norm_join

logger = logging.getLogger('tacozmq.fs')
if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue

    unicode = str

if os.name == 'nt':
    import ctypes


    def get_free_space(path):
        free_bytes = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(path), None, ctypes.pointer(total),
            ctypes.pointer(free_bytes))
        return free_bytes.value, total.value


    def get_drives():
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in range(ord('A'), ord('Z') + 1):
            if bitmask & 1:
                drives.append('%s:' % chr(letter))
            bitmask >>= 1

        return drives


    def get_windows_root_directories():
        """ Retrieves a set of directories to be listed at top level. """
        result = []

        try:
            home_dir = os.environ['HOME']
        except KeyError:
            try:
                home_dir = os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
            except KeyError:
                home_dir = ""
        if os.path.isdir(home_dir):
            result.append({
                'name': "Home",
                'path': home_dir,
                'kind': 'dir'
            })

            desktop_dir = os.path.join(home_dir, 'Desktop')
            if os.path.isdir(home_dir):
                result.append({
                    'name': "Desktop",
                    'path': desktop_dir,
                    'kind': 'dir'
                })

        try:
            public_dir = os.environ['PUBLIC']
        except KeyError:
            public_dir = ""
        if os.path.isdir(public_dir):
            result.append({
                'name': "Public",
                'path': public_dir,
                'kind': 'dir'
            })

        for drive in get_drives():
            name_buffer = ctypes.create_unicode_buffer(1024)
            system_buffer = ctypes.create_unicode_buffer(1024)
            serial_number = None
            max_component_length = None
            file_system_flags = None

            rc = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive + "\\"),
                name_buffer,
                ctypes.sizeof(name_buffer),
                serial_number,
                max_component_length,
                file_system_flags,
                system_buffer,
                ctypes.sizeof(system_buffer)
            )
            label = str(name_buffer.value)
            file_system = str(system_buffer.value)

            result.append({
                'name': ('%s (%s)  %s' % (label, drive, file_system))
                if len(label) > 0 else
                '%s  %s' % (drive, file_system),
                'path': drive,
                'kind': 'dir'
            })

        try:
            temp_dir = os.environ['TEMP']
        except KeyError:
            try:
                temp_dir = os.environ['TMP']
            except KeyError:
                temp_dir = ""
        if os.path.isdir(temp_dir):
            result.append({
                'name': "Temp",
                'path': temp_dir,
                'kind': 'dir'
            })

        return result

elif os.name == 'posix':

    def get_free_space(path):
        try:
            data = os.statvfs(path)
            free = data.f_bavail * data.f_frsize
            total = data.f_blocks * data.f_frsize
            return free, total
        except Exception:
            return 0, 0


def is_path_under_share(app, path):
    return_value = False
    if os.path.isdir(os.path.normpath(path)):
        with app.settings_lock:
            for [share_name, share_path] in app.settings["Shares"]:
                dirpath = os.path.abspath(os.path.normcase(unicode(share_path)))
                dirpath2 = os.path.abspath(os.path.normcase(unicode(path)))
                if os.path.commonprefix([dirpath, dirpath2]) == dirpath:
                    return_value = True
                    break
    # logger.debug(path + " -- " + str(return_value))
    return return_value


def convert_path_to_share(app, share):
    return_val = ""
    with app.settings_lock:
        for [share_name, share_path] in app.settings["Shares"]:
            if share_name == share:
                return_val = share_path
                break
    # logger.debug(share + " -- " + str(return_val))
    return return_val


class TacoFilesystemManager(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self, name="thTacoFS")
        self.app = app

        self.stop = threading.Event()
        self.sleep = threading.Event()

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

        self.workers = []
        self.last_purge = time.time()

        self.listings_lock = threading.Lock()
        self.listings = {}

        self.listing_work_queue = Queue()
        self.listing_results_queue = Queue()
        self.chunk_requests_incoming_queue = Queue()
        self.chunk_requests_outgoing_queue = Queue()
        self.chunk_requests_ack_queue = Queue()

        self.results_to_return = []

        self.download_q_check_time = time.time()

        # Each key is a peer uuid. Entries can consist of either a single 0
        # or a tuple of (sharedir, filename, filesize, filemod).
        # This tells that we can only download a single file from a
        # peer at any given time, the same as the first one in app.download_q
        self.client_downloading = {}

        self.client_downloading_status = {}
        self.client_downloading_pending_chunks = {}
        self.client_downloading_requested_chunks = {}
        self.client_downloading_chunks_last_received = {}
        self.client_downloading_file_name = {}
        self.files_w = {}
        self.files_r = {}
        self.files_r_last_access = {}
        self.files_w_last_access = {}

    def create(self):
        """ Called at thread start to initialize the state. """
        self.set_status("Starting Up Filesystem Manager")

        for i in range(FILESYSTEM_WORKER_COUNT):
            self.workers.append(TacoFilesystemWorker(self.app, i))

        for i in self.workers:
            i.start()

    def terminate(self):
        """ Called at thread end to free resources. """
        self.set_status("Killing Workers")
        for i in self.workers:
            i.stop.set()
        for i in self.workers:
            i.join()
        self.set_status("Closing Open Files")
        for file_name in self.files_r:
            self.files_r[file_name].close()
        for file_name in self.files_w:
            self.files_w[file_name].close()
        self.set_status("Filesystem Manager Exit")

    def run(self):
        """ Thread main function. """
        self.create()

        while not self.stop.is_set():
            # self.set_status("FILESYS")
            self.sleep.wait(0.2)
            self.sleep.clear()
            if self.stop.is_set():
                break

            self.download_quque_state()
            for peer_uuid in self.client_downloading:
                if self.client_downloading[peer_uuid] == 0:
                    continue
                self.peer_download(peer_uuid)
            self.requests_ack()
            self.last_received_chunk()
            self.process_client_downloading()

            if self.stop.is_set():
                break

            if not self.outgoing_chunks():
                break

            self.return_results()
            self.cache_purge()
            self.share_listing()
            self.listing_results()

        self.terminate()

    def add_listing(self, the_time, share_dir, dirs, files):
        with self.listings_lock:
            self.listings[share_dir] = [the_time, dirs, files]

    def set_status(self, text, level=0):
        if level == 1:
            logger.info(text)
        elif level == 0:
            logger.debug(text)
        elif level == 2:
            logger.warning(text)
        elif level == 3:
            logger.error(text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time

    def peer_is_downloading(self, peer_uuid):
        return len(self.client_downloading_pending_chunks[peer_uuid]) > 0 \
               and len(self.client_downloading_requested_chunks[peer_uuid]
                       ) < FILESYSTEM_CREDIT_MAX

    def peer_download(self, peer_uuid):
        """ Send out requests for downloads. """
        (share_dir, file_name, file_size, file_mod) = \
            self.client_downloading[peer_uuid]
        while self.peer_is_downloading(peer_uuid):
            (chunk_uuid, file_offset) = \
                self.client_downloading_pending_chunks[peer_uuid].pop()
            self.set_status(
                "Credits free: share_dir=%r, file_name=%r, file_size=%r, "
                "file_mod=%r, chunk_uuid=%r, file_offset=%r" % (
                    share_dir, file_name, file_size,
                    file_mod, chunk_uuid, file_offset))

            request = self.app.commands.request_get_file_chunk_cmd(
                share_dir, file_name, file_offset, chunk_uuid)
            self.app.add_to_output_queue(peer_uuid, request, PRIORITY_FILE)
            self.client_downloading_requested_chunks[peer_uuid] \
                .append(chunk_uuid)
            (time_request_sent, time_request_ack, offset) = \
                self.client_downloading_status[peer_uuid][chunk_uuid]
            self.client_downloading_status[peer_uuid][chunk_uuid] = (
                time.time(), 0.0, offset)

    def peer_q_download(self, peer_uuid, local_copy_download_directory):

        incoming = self.app.server.get_client_last_request(peer_uuid)
        outgoing = self.app.clients.get_client_last_reply(peer_uuid)

        if incoming < 0 or outgoing < 0:
            self.set_status(
                "I have items in the download queue, "
                "but client has never been contactable: %r", peer_uuid)
            return

        if \
                abs(time.time() - incoming) > ROLLCALL_TIMEOUT or \
                abs(time.time() - outgoing) > ROLLCALL_TIMEOUT:
            self.set_status(
                "I have items in the download queue, "
                "but client has timed out rollcalls: %r", peer_uuid)
            return

        # The peer is responsive.

        if len(self.app.download_q[peer_uuid]) == 0:
            self.set_status("Download Q empty for: %r" % peer_uuid)
            self.client_downloading[peer_uuid] = 0
            del self.app.download_q[peer_uuid]
            self.client_downloading_pending_chunks[peer_uuid] = []
            self.client_downloading_requested_chunks[peer_uuid] = []
            self.client_downloading_status[peer_uuid] = {}
            self.client_downloading_chunks_last_received = {}
            return

        (share_dir, file_name, file_size, file_mod) = \
            self.app.download_q[peer_uuid][0]
        if peer_uuid not in self.client_downloading:
            self.client_downloading[peer_uuid] = 0

        if self.client_downloading[peer_uuid] != (share_dir, file_name, file_size, file_mod):
            self.set_status(
                "Need to check on the file we should be downloading: "
                "peer_uuid=%r, share_dir=%r, file_name=%r, "
                "file_size=%r, file_mod=%r" % (
                    peer_uuid, share_dir, file_name, file_size, file_mod))
            self.client_downloading[peer_uuid] = (
                share_dir, file_name, file_size, file_mod)
            self.client_downloading_pending_chunks[peer_uuid] = []
            self.client_downloading_requested_chunks[peer_uuid] = []
            if not os.path.isdir(local_copy_download_directory):
                # TODO: just ignoring this doesn't seem right
                return

            file_name_incomplete = norm_join(
                local_copy_download_directory,
                file_name + FILESYSTEM_WORKINPROGRESS_SUFFIX)

            try:
                current_size = os.path.getsize(file_name_incomplete)
            except Exception:
                current_size = 0

            if current_size != file_size:
                self.set_status("Building in memory 'torrent'")
                self.client_downloading_file_name[peer_uuid] = file_name_incomplete
                self.client_downloading_status[peer_uuid] = {}
                self.client_downloading_chunks_last_received = {}
                for file_offset in range(current_size, file_size + 1,
                                         FILESYSTEM_CHUNK_SIZE):
                    tmp_uuid = uuid.uuid4().hex
                    self.client_downloading_pending_chunks[peer_uuid].append(
                        (tmp_uuid, file_offset))
                    self.client_downloading_status[peer_uuid][tmp_uuid] = (0.0, 0.0, file_offset)
                self.client_downloading_pending_chunks[peer_uuid].reverse()
                self.set_status("Building in memory 'torrent' -- done")
        else:
            # Download in progress.
            if not os.path.isdir(local_copy_download_directory):
                # TODO: just ignoring this doesn't seem right
                return

            file_name_incomplete = norm_join(
                local_copy_download_directory,
                file_name + FILESYSTEM_WORKINPROGRESS_SUFFIX)
            file_name_complete = norm_join(
                local_copy_download_directory, file_name)

            try:
                current_size = os.path.getsize(file_name_incomplete)
            except:
                current_size = 0

            # self.set_status(str((current_size,file_size,len(self.client_downloading_pending_chunks[peer_uuid]),len(self.client_downloading_requested_chunks[peer_uuid]))))
            if current_size == file_size and len(
                    self.client_downloading_pending_chunks[peer_uuid]) == 0 and len(
                self.client_downloading_requested_chunks[peer_uuid]) == 0:

                self.set_status("FILE DOWNLOAD COMPLETE")
                if not os.path.exists(file_name_complete):
                    os.rename(file_name_incomplete, file_name_complete)
                else:
                    (root, ext) = os.path.splitext(file_name_complete)
                    file_name_complete = root + "." + unicode(uuid.uuid4().hex) + "." + ext
                    os.rename(file_name_incomplete, file_name_complete)

                with self.app.completed_q_lock:
                    self.app.completed_q.append(
                        (time.time(), peer_uuid, share_dir, file_name, file_size))

                del self.app.download_q[peer_uuid][0]

    def perform_share_listing_requests(self, peer_uuid):
        share_dir, shareuuid = \
            self.app.share_listing_requests[peer_uuid].get()
        # self.set_status(
        #     "Filesystem thread has a pending share listing request: %r, %r" %
        #     (share_dir, shareuuid))
        # share_dir = share_dir.split('/')
        # if len(share_dir) == 0:
        #     # Asking for the list of shares
        #     with self.app.settings_lock:
        #         for (share_name, share_path) in self.app.settings["Shares"]:
        #
        # else:
        #     # asking about a directory

        root_share_dir = os.path.normpath(share_dir)
        root_share_name = root_share_dir.split("/")[1]
        root_path = os.path.normpath("/" + "/".join(root_share_dir.split("/")[2:]) + "/")
        directory = os.path.normpath(convert_path_to_share(self.app, root_share_name) + "/" + root_path)
        if (is_path_under_share(self.app, directory) and os.path.isdir(directory)) or root_share_dir == "/":
            self.listing_work_queue.put(share_dir)
            self.results_to_return.append([peer_uuid, share_dir, shareuuid])
        else:
            self.set_status("User has requested a bogus share: " + str(share_dir))

    def outgoing_chunks(self):
        # chunk data has been requested
        if self.chunk_requests_outgoing_queue.empty():
            return True

        if self.stop.is_set():
            return False

        try:
            (peer_uuid, share_dir, file_name, offset, chunk_uuid) = \
                self.chunk_requests_outgoing_queue.get(0)
        except:
            return False

        self.set_status(
            "Need to send a chunk of data: " + str(
                (peer_uuid, share_dir, file_name, offset, chunk_uuid)))

        root_share_name = share_dir.split("/")[1]
        root_path = os.path.normpath(
            "/" + "/".join(share_dir.split("/")[2:]) + "/")
        directory = os.path.normpath(convert_path_to_share(
            self.app, root_share_name) + "/" + root_path)
        fullpath = os.path.normpath(directory + "/" + file_name)

        if not is_path_under_share(self.app, os.path.dirname(fullpath)):
            return False

        if not os.path.isdir(directory):
            return False

        if fullpath not in self.files_r.keys():
            self.set_status("I need to open a file for reading:" + fullpath)
            self.files_r[fullpath] = open(fullpath, "rb")

        self.files_r_last_access[fullpath] = time.time()
        if offset < os.path.getsize(fullpath):
            self.files_r[fullpath].seek(offset)
            chunk_data = self.files_r[fullpath].read(FILESYSTEM_CHUNK_SIZE)
            request = self.app.commands.request_give_file_chunk_cmd(
                chunk_data, chunk_uuid)
            self.app.add_to_output_queue(peer_uuid, request, PRIORITY_LOW)
            self.sleep.set()
            self.app.clients.sleep.set()

        if self.stop.is_set():
            return False

        return True

    def return_results(self):
        if len(self.results_to_return) > 0:
            # self.set_status("There are results that need to be sent once they are ready")
            with self.listings_lock:
                for [peer_uuid, share_dir, shareuuid] in self.results_to_return:
                    if share_dir in self.listings.keys():
                        self.set_status("RESULTS ready to send:" + str((share_dir, shareuuid)))
                        request = self.app.commands.request_share_listing_result_cmd(
                            share_dir, shareuuid, self.listings[share_dir])
                        self.app.add_to_output_queue(
                            peer_uuid, request, PRIORITY_MEDIUM)
                        self.app.clients.sleep.set()
                        self.results_to_return.remove(
                            [peer_uuid, share_dir, shareuuid])
                        self.sleep.set()

    def cache_purge(self):
        if abs(time.time() - self.last_purge) > FILESYSTEM_CACHE_PURGE:
            # self.set_status("Purging old filesystem results")
            self.last_purge = time.time()

            for file_name in self.files_r_last_access.keys():
                if abs(time.time() - self.files_r_last_access[file_name]) > FILESYSTEM_CACHE_TIMEOUT:
                    if file_name in self.files_r.keys():
                        self.set_status("Closing a file for reading due to inactivity:" + file_name)
                        self.files_r[file_name].close()
                        del self.files_r[file_name]
                    del self.files_r_last_access[file_name]

            for file_name in self.files_w_last_access.keys():
                if abs(time.time() - self.files_w_last_access[file_name]) > FILESYSTEM_CACHE_TIMEOUT:
                    if file_name in self.files_w.keys():
                        self.set_status("Closing a file for writing due to inactivity:" + file_name)
                        self.files_w[file_name].close()
                        del self.files_w[file_name]
                    del self.files_w_last_access[file_name]

            with self.app.share_listings_lock:
                for iterkey in self.app.share_listings.keys():
                    if abs(time.time() - self.app.share_listings[iterkey][0]) > FILESYSTEM_CACHE_TIMEOUT:
                        self.set_status("Purging old local filesystem cached results")
                        del self.app.share_listings[iterkey]

            with self.listings_lock:
                for share_dir in self.listings.keys():
                    [the_time, dirs, files] = self.listings[share_dir]
                    if abs(time.time() - the_time) > FILESYSTEM_CACHE_TIMEOUT:
                        self.set_status("Purging Filesystem cache for share: " + share_dir)
                        del self.listings[share_dir]

            with self.app.share_listings_mine_lock:
                for share_listing_uuid in self.app.share_listings_mine.keys():
                    the_time = self.app.share_listings_mine[share_listing_uuid]
                    if abs(time.time() - the_time) > FILESYSTEM_LISTING_TIMEOUT:
                        self.set_status("Purging Filesystem listing i care about for: " + share_listing_uuid)
                        del self.app.share_listings_mine[share_listing_uuid]

    def share_listing(self):
        with self.app.share_listing_requests_lock:
            for peer_uuid in self.app.share_listing_requests:
                while not self.app.share_listing_requests[peer_uuid].empty():
                    self.perform_share_listing_requests(peer_uuid)

    def listing_results(self):
        while not self.listing_results_queue.empty():
            (success, the_time, share_dir, dirs, files) = self.listing_results_queue.get()
            self.set_status("Processing a worker result: " + share_dir)
            self.add_listing(the_time, share_dir, dirs, files)
            self.sleep.set()

    def process_client_downloading(self):
        """ chunk data has been received. """
        while not self.chunk_requests_incoming_queue.empty():
            if self.stop.is_set():
                break
            try:
                (peer_uuid, chunk_uuid, data) = \
                    self.chunk_requests_incoming_queue.get(0)
            except:
                break

            if peer_uuid in self.client_downloading_requested_chunks and chunk_uuid in \
                    self.client_downloading_requested_chunks[
                        peer_uuid] and peer_uuid in self.client_downloading_file_name:

                if peer_uuid in self.client_downloading and self.client_downloading[peer_uuid] == 0:
                    return

                self.set_status("Chunk data has been received: " + str((peer_uuid, chunk_uuid, len(data))))
                self.client_downloading_chunks_last_received[peer_uuid] = time.time()
                (share_dir, file_name, file_size, file_mod) = self.client_downloading[peer_uuid]
                fullpath = self.client_downloading_file_name[peer_uuid]
                if fullpath not in self.files_w.keys():
                    self.files_w[fullpath] = open(fullpath, "ab")
                self.files_w_last_access[fullpath] = time.time()
                self.files_w[fullpath].write(data)
                self.files_w[fullpath].flush()
                if self.files_w[fullpath].tell() >= file_size:
                    self.files_w[fullpath].close()
                    del self.files_w[fullpath]
                del self.client_downloading_status[peer_uuid][chunk_uuid]
                self.client_downloading_requested_chunks[peer_uuid].remove(chunk_uuid)
                self.sleep.set()
            else:
                self.set_status("Got a chunk, but it's bogus:" + str((peer_uuid, chunk_uuid, len(data))))

    def last_received_chunk(self):
        for peer_uuid in self.client_downloading_chunks_last_received:
            if peer_uuid in self.client_downloading and self.client_downloading[peer_uuid] != 0:
                if abs(time.time() - self.client_downloading_chunks_last_received[
                    peer_uuid]) > DOWNLOAD_Q_WAIT_FOR_DATA:
                    self.set_status("Download Borked for: " + peer_uuid)
                    self.client_downloading[peer_uuid] = 0

    def requests_ack(self):
        """  check for chunk ack """
        time_request_sent = -1
        while not self.chunk_requests_ack_queue.empty():
            try:
                (peer_uuid, chunk_uuid) = self.chunk_requests_ack_queue.get(0)
            except:
                break

            if peer_uuid in self.client_downloading_requested_chunks and chunk_uuid in \
                    self.client_downloading_requested_chunks[
                        peer_uuid] and peer_uuid in self.client_downloading_status:

                (time_request_sent, time_request_ack, offset) = self.client_downloading_status[peer_uuid][
                    chunk_uuid]
                self.client_downloading_status[peer_uuid][chunk_uuid] = (time_request_sent, time.time(), offset)
                self.set_status(
                    "File Chunk request has been ACK'D:" + str((peer_uuid, time_request_sent, chunk_uuid)))
                self.sleep.set()
            else:
                self.set_status(
                    "File Chunk request SHOULD HAVE been ACK'D:" + str((peer_uuid, time_request_sent, chunk_uuid)))

    def download_quque_state(self):
        """ Check download queue state. """
        if time.time() >= self.download_q_check_time:
            # self.set_status("Checking if the download q is in a good state")
            with self.app.settings_lock:
                local_copy_download_directory = \
                    os.path.normpath(self.app.settings["Download Location"])
            self.download_q_check_time = time.time() + DOWNLOAD_Q_CHECK_TIME

            # check for download q items
            with self.app.download_q_lock:
                for peer_uuid in self.app.download_q.keys():
                    self.peer_q_download(
                        peer_uuid, local_copy_download_directory)


class TacoFilesystemWorker(threading.Thread):
    """ What we seem to have here is a very fancy, very threaded way of
    listing directories. No less than 4 threads are working assiduously at this
    holly task. """
    def __init__(self, app, worker_id):
        threading.Thread.__init__(self, name="thTacoFS-%r" % worker_id)
        self.app = app

        self.stop = threading.Event()

        self.worker_id = worker_id

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

    def set_status(self, text, level=0):
        if level == 1:
            logger.info(text)
        elif level == 0:
            logger.debug(text)
        elif level == 2:
            logger.warning(text)
        elif level == 3:
            logger.error(text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time

    def run(self):
        self.set_status("Starting Filesystem Worker #" + str(self.worker_id))
        while not self.stop.is_set():

            try:
                root_share_dir = self.app.filesys.listing_work_queue.get(True, 0.2)
                self.set_status(str(self.worker_id) + " -- " + str(root_share_dir))
                root_share_dir = os.path.normpath(root_share_dir)
                root_share_name = root_share_dir.split("/")[1]
                root_path = os.path.normpath("/" + "/".join(root_share_dir.split("/")[2:]) + "/")
                directory = os.path.normpath(convert_path_to_share(self.app, root_share_name) + "/" + root_path)
                if root_share_dir == "/":
                    self.set_status("Root share listing request")
                    share_listing = []
                    with self.app.settings_lock:
                        for [share_name, share_path] in self.app.settings["Shares"]:
                            share_listing.append(share_name)
                    share_listing.sort()
                    results = [1, time.time(), root_share_dir, share_listing, []]
                    self.app.filesys.listing_results_queue.put(results)
                    continue
                assert is_path_under_share(self.app, directory)
                assert os.path.isdir(directory)
            except Exception:
                continue

            self.set_status("Filesystem Worker #" + str(self.worker_id) + " -- Get Directory Listing for: " + directory)

            dirs = []
            files = []
            try:
                dir_list = os.listdir(directory)
            except Exception:
                results = [0, time.time(), root_share_dir, [], []]
            else:
                try:
                    for fileobject in dir_list:
                        joined = os.path.normpath(directory + "/" + fileobject)
                        if os.path.isfile(joined):
                            file_mod = os.stat(joined).st_mtime
                            file_size = os.path.getsize(joined)
                            files.append((fileobject, file_size, file_mod))
                        elif os.path.isdir(joined):
                            dirs.append(fileobject)
                    dirs.sort()
                    files.sort()
                    results = [1, time.time(), root_share_dir, dirs, files]
                except Exception:
                    logger.exception("Failed to obtain the list of files")
                    results = [0, time.time(), root_share_dir, [], []]

            self.app.filesys.listing_results_queue.put(results)
            self.app.filesys.sleep.set()

        self.set_status("Exiting Filesystem Worker #" + str(self.worker_id))
