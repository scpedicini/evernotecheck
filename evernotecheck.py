import logging
from evernote.api.client import EvernoteClient
from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
from evernote.edam.error.ttypes import (EDAMSystemException, EDAMErrorCode)
import pickle
import sys
from datetime import datetime
from time import sleep
import os


logger = logging.getLogger(__name__)


class VirtualNote:
    def __init__(self, guid, title, content_length, date_modified, largest_resource):
        self.Guid = guid
        self.Title = title
        self.ContentLength = content_length
        self.DateModified = date_modified
        self.LargestResource = largest_resource


def safe_int(x):
    return 0 if x is None else x


def evernote_wait_try_again(fptr):
    """
    Wait until mandated wait and try again
    http://dev.evernote.com/doc/articles/rate_limits.php
    """

    def f2(*args, **kwargs):
        try:
            return fptr(*args, **kwargs)
        except EDAMSystemException, e:
            if e.errorCode == EDAMErrorCode.RATE_LIMIT_REACHED:
                logger.info( "rate limit: {0} s. wait".format(e.rateLimitDuration))
                sleep(e.rateLimitDuration)
                logger("wait over")
                return fptr(*args, **kwargs)

    return f2


# Jetbrains throws TypeError: issubclass() arg 1 must be a class (because subclassing object and overwriting __getattribute__)
class RateLimitingEvernoteProxy(object):
    # based on http://code.activestate.com/recipes/496741-object-proxying/
    __slots__ = ["_obj"]

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __getattribute__(self, name):
        return evernote_wait_try_again(getattr(object.__getattribute__(self, "_obj"), name))


EVERNOTE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evernotes.p')
EVERNOTE_CREDENTIALS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evernote_credentials')

dictNotes = dict()
shrankNotes = list()
addedNotes = list()
removedNotes = list()

try:
    with open(EVERNOTE_FILE, 'rb') as f:
        dictNotes = pickle.load(f)
except Exception as e:
    print("Unexpected error:", sys.exc_info()[0])
    dictNotes = dict()

oldNoteCount = len(dictNotes)

Unmatched = set(dictNotes.keys())


with open(EVERNOTE_CREDENTIALS, 'r') as f:
    developer_token = f.read()


# Set up the NoteStore client
# client = EvernoteClient(token=dev_token, sandbox = False)
_client = EvernoteClient(token=developer_token, sandbox=False)
client = RateLimitingEvernoteProxy(_client)

note_store = client.get_note_store()

# Make API calls
# notebooks = note_store.listNotebooks()
# for notebook in notebooks:
#     print "Notebook: ", notebook.name
# '177e5d31-1868-408b-b0eb-860b5fbc34cb'
# notefilter
# notemetas = note_store.findNotesMetadata(filter=, maxNotes=250)


all_filter = NoteFilter()
result_spec = NotesMetadataResultSpec(includeContentLength=True, includeTitle=True, includeUpdated=True,
                                      includeUpdateSequenceNum=True, includeLargestResourceMime=True,
                                      includeLargestResourceSize=True, includeAttributes=True)
# authenticationToken, filter, offset, maxNotes, resultSpec
#                        findNotesMetadata(authenticationToken, filter, offset, maxNotes, resultSpec):


offset = 0
max_notes = 250
totalNotes = None

changesDetected = False

while totalNotes is None or offset < totalNotes:
    result_list = note_store.findNotesMetadata(developer_token, all_filter, offset, max_notes, result_spec)
    if totalNotes is None:
        totalNotes = result_list.totalNotes

    offset += len(result_list.notes)

    for note in result_list.notes:
        localtime = str(datetime.fromtimestamp(note.updated / 1000.0))
        if note.guid in dictNotes:
            matchedNote = dictNotes[note.guid]
            if not hasattr(matchedNote, 'LargestResource'):
                matchedNote.LargestResource = None
            if note.guid in Unmatched:
                Unmatched.remove(note.guid)
            if note.contentLength < matchedNote.ContentLength:
                print('Note: ' + note.title + ' reduced from ' + str(matchedNote.ContentLength) + ' to ' + str(note.contentLength) + ' : Reduced by ' + str(matchedNote.ContentLength - note.contentLength) + ' bytes')
                shrankNotes.append(note.guid)
            if note.largestResourceSize < matchedNote.LargestResource:
                print('Note: ' + note.title + ' embedded attachment reduced from ' + str(matchedNote.LargestResource) + ' to ' + str(note.largestResourceSize) + ' : Change ' + str(safe_int(matchedNote.LargestResource) - safe_int(note.largestResourceSize)) + ' bytes')
                shrankNotes.append(note.guid)
            if note.title != matchedNote.Title:
                print('Note: ' + matchedNote.Title + ' changed to ' + str(note.title))
            matchedNote.Title = note.title
            matchedNote.ContentLength = note.contentLength
            matchedNote.DateModified = localtime
            matchedNote.LargestResource = note.largestResourceSize
        else:
            dictNotes[note.guid] = VirtualNote(note.guid, note.title, note.contentLength, localtime, note.largestResourceSize)
            addedNotes.append(note.guid)
            print('New Note: ' + note.title)


for unmatched_guids in Unmatched:
    removed_note = dictNotes[unmatched_guids]
    print('Removed Note: ' + removed_note.Title)
    del dictNotes[unmatched_guids]

# note.title, note.guid, note.contentLength


print('Old note count: ' + str(oldNoteCount) + ' New note count: ' + str(offset))

# Guid, Title, Size
print('Evernote verification complete')

if raw_input("To save changes, type (Y): ").lower() == "y":
    try:
        with open(EVERNOTE_FILE, 'wb') as f:
            pickle.dump(dictNotes, f)
        print('Local store updated')
    except Exception as e:
        print("Unexpected error:", sys.exc_info()[0])
        print(e)











