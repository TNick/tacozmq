# -*- coding: utf-8 -*-
"""
Intermediates the access to the file sysstem for our app.
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

if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue
    unicode = str


if os.name == 'nt':
    import ctypes

    def Get_Free_Space(path):
        free_bytes = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(path), None, ctypes.pointer(total),
                                                   ctypes.pointer(free_bytes))
        return free_bytes.value, total.value

elif os.name == 'posix':

    def Get_Free_Space(path):
        try:
            data = os.statvfs(path)
            free = data.f_bavail * data.f_frsize
            total = data.f_blocks * data.f_frsize
            return free, total
        except Exception:
            return 0, 0


def Is_Path_Under_A_Share(app, path):
    return_value = False
    if os.path.isdir(os.path.normpath(path)):
        with app.settings_lock:
            for [share_name, share_path] in app.settings["Shares"]:
                dirpath = os.path.abspath(os.path.normcase(unicode(share_path)))
                dirpath2 = os.path.abspath(os.path.normcase(unicode(path)))
                if os.path.commonprefix([dirpath, dirpath2]) == dirpath:
                    return_value = True
                    break
    # logging.debug(path + " -- " + str(return_value))
    return return_value


def Convert_Share_To_Path(app, share):
    return_val = ""
    with app.settings_lock:
        for [share_name, share_path] in app.settings["Shares"]:
            if share_name == share:
                return_val = share_path
                break
    # logging.debug(share + " -- " + str(return_val))
    return return_val


class TacoFilesystemManager(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
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

    def add_listing(self, the_time, share_dir, dirs, files):
        with self.listings_lock:
            self.listings[share_dir] = [the_time, dirs, files]

    def set_status(self, text, level=0):
        if level == 1:
            logging.info(text)
        elif level == 0:
            logging.debug(text)
        elif level == 2:
            logging.warning(text)
        elif level == 3:
            logging.error(text)
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
        (share_dir, file_name, file_size, file_mod) = \
            self.client_downloading[peer_uuid]
        while self.peer_is_downloading(peer_uuid):
            (chunk_uuid, file_offset) = \
                self.client_downloading_pending_chunks[peer_uuid].pop()
            self.set_status(
                "Credits Free:" +
                str((share_dir, file_name, file_size,
                     file_mod, chunk_uuid, file_offset)))

            request = self.app.commands.Request_Get_File_Chunk(
                share_dir, file_name, file_offset, chunk_uuid)
            self.app.Add_To_Output_Queue(peer_uuid, request, 4)
            self.client_downloading_requested_chunks[peer_uuid]\
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
                "but client has never been contactable: " + peer_uuid)
            return

        if \
                abs(time.time() - incoming) > ROLLCALL_TIMEOUT or \
                abs(time.time() - outgoing) > ROLLCALL_TIMEOUT:

            self.set_status(
                "I have items in the download queue, "
                "but client has timed out rollcalls: " + peer_uuid)
            return

        # The peer is responsive.

        if len(self.app.download_q[peer_uuid]) == 0:
            self.set_status("Download Q empty for: " + peer_uuid)
            self.client_downloading[peer_uuid] = 0
            del self.app.download_q[peer_uuid]
            self.client_downloading_pending_chunks[peer_uuid] = []
            self.client_downloading_requested_chunks[peer_uuid] = []
            self.client_downloading_status[peer_uuid] = {}
            self.client_downloading_chunks_last_received = {}
            return

        (share_dir, file_name, file_size, file_mod) = \
            self.app.download_q[peer_uuid][0]
        if not peer_uuid in self.client_downloading:
            self.client_downloading[peer_uuid] = 0

        if self.client_downloading[peer_uuid] != (share_dir, file_name, file_size, file_mod):
            self.set_status(
                "Need to check on the file we should be downloading:" + str(
                    (peer_uuid, share_dir, file_name, file_size, file_mod)))
            self.client_downloading[peer_uuid] = (share_dir, file_name, file_size, file_mod)
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
                    file_name_complete = root + u"." + unicode(uuid.uuid4().hex) + u"." + ext
                    os.rename(file_name_incomplete, file_name_complete)

                with self.app.completed_q_lock:
                    self.app.completed_q.append(
                        (time.time(), peer_uuid, share_dir, file_name, file_size))

                del self.app.download_q[peer_uuid][0]

    def run(self):
        self.set_status("Starting Up Filesystem Manager")

        for i in range(FILESYSTEM_WORKER_COUNT):
            self.workers.append(TacoFilesystemWorker(self.app, i))

        for i in self.workers:
            i.start()

        while not self.stop.is_set():
            # self.set_status("FILESYS")
            self.sleep.wait(0.2)
            self.sleep.clear()
            if self.stop.is_set():
                break

            # CHECK downloadq state
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

            # send out requests for downloads
            for peer_uuid in self.client_downloading:
                if self.client_downloading[peer_uuid] == 0:
                    continue
                self.peer_download(peer_uuid)

            # check for chunk ack
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

            for peer_uuid in self.client_downloading_chunks_last_received:
                if peer_uuid in self.client_downloading and self.client_downloading[peer_uuid] != 0:
                    if abs(time.time() - self.client_downloading_chunks_last_received[peer_uuid]) > DOWNLOAD_Q_WAIT_FOR_DATA:
                        self.set_status("Download Borked for: " + peer_uuid)
                        self.client_downloading[peer_uuid] = 0

            # chunk data has been received
            while not self.chunk_requests_incoming_queue.empty():
                if self.stop.is_set():
                    break

                try:
                    (peer_uuid, chunk_uuid, data) = self.chunk_requests_incoming_queue.get(0)
                except:
                    break

                if peer_uuid in self.client_downloading_requested_chunks and chunk_uuid in \
                        self.client_downloading_requested_chunks[
                            peer_uuid] and peer_uuid in self.client_downloading_file_name:

                    if peer_uuid in self.client_downloading and self.client_downloading[peer_uuid] == 0:
                        continue

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

            if self.stop.is_set():
                break

            # chunk data has been requested
            if not self.chunk_requests_outgoing_queue.empty():
                if self.stop.is_set():
                    break

                try:
                    (peer_uuid, share_dir, file_name, offset, chunk_uuid) = self.chunk_requests_outgoing_queue.get(0)
                except:
                    break

                self.set_status(
                    "Need to send a chunk of data: " + str((peer_uuid, share_dir, file_name, offset, chunk_uuid)))

                root_share_name = share_dir.split(u"/")[1]
                root_path = os.path.normpath(u"/" + u"/".join(share_dir.split(u"/")[2:]) + u"/")
                directory = os.path.normpath(Convert_Share_To_Path(self.app, root_share_name) + u"/" + root_path)
                fullpath = os.path.normpath(directory + u"/" + file_name)

                if not Is_Path_Under_A_Share(self.app, os.path.dirname(fullpath)):
                    break

                if not os.path.isdir(directory):
                    break

                if fullpath not in self.files_r.keys():
                    self.set_status("I need to open a file for reading:" + fullpath)
                    self.files_r[fullpath] = open(fullpath, "rb")

                self.files_r_last_access[fullpath] = time.time()
                if offset < os.path.getsize(fullpath):
                    self.files_r[fullpath].seek(offset)
                    chunk_data = self.files_r[fullpath].read(FILESYSTEM_CHUNK_SIZE)
                    request = self.app.commands.Request_Give_File_Chunk(chunk_data, chunk_uuid)
                    self.app.Add_To_Output_Queue(peer_uuid, request, 3)
                    self.sleep.set()
                    self.app.clients.sleep.set()

            if self.stop.is_set():
                break

            if len(self.results_to_return) > 0:
                # self.set_status("There are results that need to be sent once they are ready")
                with self.listings_lock:
                    for [peer_uuid, share_dir, shareuuid] in self.results_to_return:
                        if share_dir in self.listings.keys():
                            self.set_status("RESULTS ready to send:" + str((share_dir, shareuuid)))
                            request = self.app.commands.Request_Share_Listing_Results(share_dir, shareuuid,
                                                                                  self.listings[share_dir])
                            self.app.Add_To_Output_Queue(peer_uuid, request, 2)
                            self.app.clients.sleep.set()
                            self.results_to_return.remove([peer_uuid, share_dir, shareuuid])
                            self.sleep.set()

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

                with self.app.share_listings_i_care_about_lock:
                    for share_listing_uuid in self.app.share_listings_i_care_about.keys():
                        the_time = self.app.share_listings_i_care_about[share_listing_uuid]
                        if abs(time.time() - the_time) > FILESYSTEM_LISTING_TIMEOUT:
                            self.set_status("Purging Filesystem listing i care about for: " + share_listing_uuid)
                            del self.app.share_listings_i_care_about[share_listing_uuid]

            with self.app.share_listing_requests_lock:
                for peer_uuid in self.app.share_listing_requests.keys():
                    while not self.app.share_listing_requests[peer_uuid].empty():
                        (share_dir, shareuuid) = self.app.share_listing_requests[peer_uuid].get()
                        self.set_status(
                            "Filesystem thread has a pending share listing request: " + str((share_dir, shareuuid)))
                        root_share_dir = os.path.normpath(share_dir)
                        root_share_name = root_share_dir.split(u"/")[1]
                        root_path = os.path.normpath(u"/" + u"/".join(root_share_dir.split(u"/")[2:]) + u"/")
                        directory = os.path.normpath(Convert_Share_To_Path(self.app, root_share_name) + u"/" + root_path)
                        if (Is_Path_Under_A_Share(self.app, directory) and os.path.isdir(directory)) or root_share_dir == u"/":
                            self.listing_work_queue.put(share_dir)
                            self.results_to_return.append([peer_uuid, share_dir, shareuuid])
                        else:
                            self.set_status("User has requested a bogus share: " + str(share_dir))

            while not self.listing_results_queue.empty():
                (success, the_time, share_dir, dirs, files) = self.listing_results_queue.get()
                self.set_status("Processing a worker result: " + share_dir)
                self.add_listing(the_time, share_dir, dirs, files)
                self.sleep.set()

        self.set_status("Killing Workers")
        for i in self.workers:
            i.stop.set()
        for i in self.workers:
            i.join()
        self.set_status("Closing Open Files")
        for file_name in self.files_r: self.files_r[file_name].close()
        for file_name in self.files_w: self.files_w[file_name].close()
        self.set_status("Filesystem Manager Exit")


class TacoFilesystemWorker(threading.Thread):
    def __init__(self, app, worker_id):
        threading.Thread.__init__(self)
        self.app = app

        self.stop = threading.Event()

        self.worker_id = worker_id

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

    def set_status(self, text, level=0):
        if level == 1:
            logging.info(text)
        elif level == 0:
            logging.debug(text)
        elif level == 2:
            logging.warning(text)
        elif level == 3:
            logging.error(text)
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
                root_share_name = root_share_dir.split(u"/")[1]
                root_path = os.path.normpath(u"/" + u"/".join(root_share_dir.split(u"/")[2:]) + u"/")
                directory = os.path.normpath(Convert_Share_To_Path(self.app, root_share_name) + u"/" + root_path)
                if root_share_dir == u"/":
                    self.set_status("Root share listing request")
                    share_listing = []
                    with self.app.settings_lock:
                        for [share_name, share_path] in self.app.settings["Shares"]:
                            share_listing.append(share_name)
                    share_listing.sort()
                    results = [1, time.time(), root_share_dir, share_listing, []]
                    self.app.filesys.listing_results_queue.put(results)
                    continue
                assert Is_Path_Under_A_Share(self.app, directory)
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
                        joined = os.path.normpath(directory + u"/" + fileobject)
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
                    logging.exception("Failed to obtain the list of files")
                    results = [0, time.time(), root_share_dir, [], []]

            self.app.filesys.listing_results_queue.put(results)
            self.app.filesys.sleep.set()

        self.set_status("Exiting Filesystem Worker #" + str(self.worker_id))
