import os
import time

# convert time t which is seconds since the epoch to a string parsable by excel
def time_to_Ymd_HMS(t):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))
    
#timedprogress is a class used to output a progress message every interval seconds.
#the progress method is used to provide the most recent status to be provided to the user.
#an iteration count is maintained and incremented with each call to progress.
#a progress message with the iteration count and progress message will be output every interval seconds.
class TimedProgress:
    def __init__(self, interval=5):
        self.interval = interval
        self.last_time = 0
        self.iteration = 0
        self.starttime = time.time()

    def progress(self, message):
        self.iteration += 1
        self.elapsed = time.time() - self.starttime
        ips = int(self.iteration / self.elapsed)
        if time.time() - self.last_time > self.interval:
            print(f"{ips}-{self.iteration}: {message}")
            self.last_time = time.time()

import ctypes
from ctypes import wintypes

# Define constants
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000  # Placeholder value, check for actual value in your environment

# Load the Windows DLL
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

def get_file_attributes(path):
    attrs = kernel32.GetFileAttributesW(wintypes.LPCWSTR(path))
    if attrs == -1:
        return 0
        #raise ctypes.WinError(ctypes.get_last_error())
    return attrs

def is_cloud_file(path):
    attrs = get_file_attributes(path)
    # Check for specific cloud-related attribute
    return (attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS) == FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS


class CDirEntry:
    r"""CDirEntry can be initialized with a DirEntry or a path to a file.  It returns provides a
    simplified access to DirEntry attributes including mtime, and size and owner.
    It has properties mtime, owner and modified_by that return cooked values for mtime, owner and modified_by.
    """

    def __str__(self):
        return f"{self.path} {self.size} {self.strmtime()}"
    
    def __init__(self, entry):
        #if entry is an os.DirEntry then use it to populate the properties of CDirEntry.
        if isinstance(entry, os.DirEntry):
            self.entry = entry
            self.name = entry.name
            self.path = entry.path
            self.size = entry.stat().st_size
            self._mtime = entry.stat().st_mtime
            self._cloud = is_cloud_file(self.path)
            if self._cloud:
                self.localsize = 0
            else:
                self.localsize = self.size
            self._owner = None
            self._modified_by = None
            self.type = 'D' if entry.is_dir() else 'F'
        elif isinstance(entry, str):
            # entry is a path, so fill out the properties of CDirEntry using the path
            self.path = entry
            self.name = os.path.basename(entry)
            self.size = os.stat(entry).st_size
            self._mtime = os.stat(entry).st_mtime
            self._cloud = is_cloud_file(self.path)
            if self._cloud:
                self.localsize = 0
            else:
                self.localsize = self.size
            self._owner = None
            self._modified_by = None
            self.type = 'D' if os.path.isdir(entry) else 'F'
        else:
            self.path = ""
            self.name = ""
            self.size = 0
            self._mtime = 0
            self._cloud = "x"
            self.localsize = 0
            self._owner = ""
            self._modified_by = ""
            self.type = ''
            self._modified_by = ""

    def is_dir(self):
        return self.type == 'D'

    @property
    def mtime(self):
        if self._mtime is None:
            self._mtime = self.stat().st_mtime
        return self._mtime

    def strmtime(self):
        return time_to_Ymd_HMS(self.mtime)
    @property
    def owner(self):
        if self._owner is None:
            self._owner = self._get_owner()
        return self._owner

    def _get_owner(self):
        """takes an os.DirEntry object and returns the username of the owner of the file"""
        try:
            if os.name == 'nt':
                # Windows does not support pwd module
                # Alternative method to get the owner name on Windows
                sd = win32security.GetFileSecurity(self.path, win32security.OWNER_SECURITY_INFORMATION)
                owner_sid = sd.GetSecurityDescriptorOwner()
                name, domain, type = win32security.LookupAccountSid(None, owner_sid)
                return f"{domain}\\{name}"
            else:
                # Unix-like systems
                return pwd.getpwuid(os.stat(direntry.path).st_uid).pw_name
        except Exception as e:
            return str(e)


    @property
    def modified_by(self):
        if self._modified_by is None:
            self._modified_by = self._get_owner()
        return self._modified_by

progress = TimedProgress()



class FileSystemWalker:
    r"""
    Class FileSystemWalker(path,collector) walks the hierarchy of the file system under the path.
    It adds each entry found to the collector via collector.add(path, name, size, mtime, owner, type, modified_by, error).
    type = "D" for directories and "F" for files.
    The class has a method walk() that traverses the hierarchy and calls collector.add() for each entry.
    The class has a method get_file_names(directory_path) that returns a list of file names in the specified directory.
    The class has a method get_directory_contents(directory_path) that returns a tuple of (root, dirs, files) for the specified directory.
    """
    def __init__(self, path, collector):
        self.path = path
        self.collector = collector

    def walk(self):
        srecent, ssize, slocalsize, scount = self._walk(self.path)
        entry = CDirEntry(self.path)
        entry.size = ssize
        entry.localsize = slocalsize
        self.collector.add(entry, mostrecent=srecent, filecount=scount)

    def _walk(self, path):
        entry = None
        try:
            mostrecent = CDirEntry(None) # could be optimized by creating a single CDirEntry_None object and using each pass through
            totsize = 0
            totlocalsize = 0
            filecount = 0
            for entry in self._scandir(path):
                if entry.name == 'desktop.ini':
                    continue
                if entry.is_dir():
                    srecent, ssize, slocalsize, scount = self._walk(entry.path)
                    entry.size = ssize          # size for a folder is the sum of the sizes of its contents
                    entry.localsize = slocalsize
                    self.collector.add(entry, mostrecent=srecent, filecount=scount)
                    totsize += ssize 
                    totlocalsize += slocalsize
                    filecount += scount
                    if srecent.mtime > mostrecent.mtime:
                        mostrecent = srecent
                else:
                    if entry.mtime > mostrecent.mtime:
                        mostrecent = entry
                    totsize += entry.size
                    totlocalsize += entry.localsize
                    filecount += 1
                    self.collector.add(entry)
        except OSError as e:
            self.collector.add(entry, mostrecent=mostrecent, error=str(e), path=path)
        return mostrecent, totsize, totlocalsize, filecount
    
    def _scandir(self, path):
        """returns an iterator of os.DirEntry objects corresponding to the entries in the directory given by path."""
        for entry in os.scandir(path):
            yield CDirEntry(entry)

from GDCopy.GDService import authenticate

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os

# GDWalker is a Google Drive file system walker that walks the hierarchy of the file system under the URL passed in.
# It uses the Google Drive API to access the file system.

class GDWalker(FileSystemWalker):
    def __init__(self, path, collector):
        super().__init__(path, collector)
        self.service = authenticate()[0]

    def _build_service(self):
        # Assuming 'token.json' stores the user's access and refresh tokens.
        # If modifying these scopes, delete the file token.json.
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        # If there are no (valid) credentials available, you need to log in.
        if not creds or not creds.valid:
            # Here you should add the code to handle the login flow
            # This often involves redirecting the user to a URL where they can
            # authorize the application and receive a code to exchange for a token
            raise Exception("No valid credentials available")

        self.service = build('drive', 'v3', credentials=creds)

    def _scandir(self, folder_id='root'):
        """Scans a Google Drive directory and yields entries within it.
        
        Args:
            folder_id (str): The ID of the Google Drive folder to scan. Defaults to 'root'.
        """
        # Query to get the files and folders under the specified folder_id
        query = f"'{folder_id}' in parents and trashed = false"
        try:
            
            response = self.service.files().list(q=query,
                                                spaces='drive',
                                                fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                                                pageToken=None).execute()
            for item in response.get('files', []):
                # Constructing a custom dictionary for each item
                entry = {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'type': 'folder' if item.get('mimeType') == 'application/vnd.google-apps.folder' else 'file',
                    'size': item.get('size', '0'),
                    'modifiedTime': item.get('modifiedTime')
                }
                yield entry
        except Exception as e:
            print(f"Failed to list files in folder {folder_id}: {e}")

import csv
import win32security
import pandas as pd

class Collector:
    def __init__(self, output_file='du-default.csv', path='', exclude=[]):
        self.output_file = output_file
        self.exclude = exclude
        self.entries = []
        self.root = path
        self.write_headers = ['path', 'size', 'mtime', 'localsize', 'cloud',
                                'filecount',
                                'mr_path', 'mr_size', 'mr_mtime', 
                                'error']

    def add(self, entry, mostrecent=None, path=None, error=None, filecount=None):
        adding = {}
        if entry:
            adding["path"] = entry.path
            adding["name"] = entry.name
            adding["size"] = entry.size 
            adding["mtime"] = entry.strmtime()
            adding["cloud"] = entry._cloud
            adding["localsize"] = entry.localsize  
            adding["owner"] = entry.owner
            adding["type"] = entry.type
            adding["modified_by"] = entry.modified_by
        if mostrecent:
            # make the recent path a relative path to entry.path.  
            # Assuming the left part of mostrecent.path is the same as entry.path, strip that part off.
            mr_path = mostrecent.path
            if entry and mr_path.startswith(entry.path):
                mr_path = mr_path[len(entry.path):]
            adding["mr_path"] = mr_path
            adding["mr_name"] = mostrecent.name
            adding["mr_size"] = mostrecent.size
            adding["mr_mtime"] = mostrecent.strmtime()
            adding["mr_owner"] = mostrecent.owner
            adding["mr_modified_by"] = mostrecent.modified_by

        if filecount:
            adding["filecount"] = filecount

        if error:
            adding["error"] = error

        if path:
            adding["path"] = path

        if self.root:
            lp = len(self.root)
            if "path" in adding and adding["path"].startswith(self.root):
                adding["path"] = adding["path"][lp:]
            if "mr_path" in adding and adding["mr_path"].startswith(self.root):
                adding["mr_path"] = adding["mr_path"][lp:]
        # return if any of the selements of self.exclude are in the string path
        if any([ex in adding["path"] for ex in self.exclude]):
            return
        # if we have > 1M entries, then only add the ones that have a filecount.
        if (len(self.entries) > 1000000) and not filecount:
            return
        if (len(self.entries) > 1048000):
            return
        progress.progress(f"processing {adding['path']}")
        
        self.entries.append(adding)
        
    def save(self):
        if self.output_file.endswith('.xlsx'):
            self.save_as_excel()
        else:
            self.save_as_csv()

    def save_as_excelx(self):
        data = pd.DataFrame(self.entries, columns=self.write_headers)        
        data.to_excel(self.output_file, index=False)

    def save_as_excel(self):
        import pandas as pd
        # Create a Pandas Excel writer using XlsxWriter as the engine.
        with pd.ExcelWriter(self.output_file, engine='xlsxwriter') as writer:
            # Convert the dataframe to an XlsxWriter Excel object.
            data = pd.DataFrame(self.entries, columns=self.write_headers)
            data.to_excel(writer, sheet_name='Sheet1', index=False)

            # Get the xlsxwriter workbook and worksheet objects.
            workbook  = writer.book
            worksheet = writer.sheets['Sheet1']

            # Define a format for the header: bold
            header_format = workbook.add_format({'bold': True})

            # Apply the format to the header
            for col_num, value in enumerate(data.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Define a number format for `size` and `mr_size` columns.
            num_format = workbook.add_format({'num_format': '#,##0'})

            # Get the index of `size` and `mr_size` columns to apply number format.
            # This assumes 'size' and 'mr_size' are in `self.write_headers`.
            size_col = self.write_headers.index('size') if 'size' in self.write_headers else None
            localsize_col = self.write_headers.index('localsize') if 'localsize' in self.write_headers else None
            mr_size_col = self.write_headers.index('mr_size') if 'mr_size' in self.write_headers else None

            #the path column contains a relative file path rooted at self.path.  Make each cell a hyperlink to the file.
            #for row_num, path in enumerate(data['path'], start=1):
            #    folder = os.path.dirname(self.root+path)
            #    worksheet.write_url(row_num, 0, f"file:///{folder}", string=path)

            #freeze the first row and first column
            worksheet.freeze_panes(1, 1)

            #set the column width to fit the longest string for columns size, mtime, filecount, mr_size, mr_mtime
            for col in ['size', 'mtime', 'filecount', 'mr_size', 'mr_mtime']:
                max_len = data[col].astype(str).str.len().max()
                max_len = max_len if max_len > len(col) else len(col)
                worksheet.set_column(self.write_headers.index(col), self.write_headers.index(col), max_len)
            
            #set the column width for columns path and mr_path to 75
            worksheet.set_column(self.write_headers.index('path'), self.write_headers.index('path'), 75)
            worksheet.set_column(self.write_headers.index('mr_path'), self.write_headers.index('mr_path'), 75)

            #turn on auto filter
            worksheet.autofilter(0, 0, len(data), len(data.columns) - 1)

            # Apply the number format to all rows for `size` and `mr_size` columns if they exist.
            if size_col is not None:
                worksheet.set_column(size_col, size_col, None, num_format)
            if localsize_col is not None:
                worksheet.set_column(localsize_col, localsize_col, None, num_format)
            if mr_size_col is not None:
                worksheet.set_column(mr_size_col, mr_size_col, None, num_format)

    def save_as_csv(self):
        with open(self.output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # Write the headers
            writer.writerow(self.write_headers)
            
            # Write the data
            for entry in self.entries:
                row = [str(entry.get(header, '')) for header in self.write_headers]
                writer.writerow(row)


# test FileSystemWalker with Collector
if __name__ == '__main__':
    
    for path, output_file, exclude in [
                #('G:\\Shared drives\\Photographs', 'xls/du-photographs.xlsx'),
                #('G:\\.shortcut-targets-by-id\\0B-MQKkxg8dOAZTQxNjNmZmEtNzIxNi00MDlmLWEwNmMtMjQyNjg4ZWY0Njdi\\Worship Team Docs', 'xls/du-worship-docs.xlsx'),
                #('G:\\.shortcut-targets-by-id\\0B6XHzr6S7-pNN28weFpaaW1OUEk\\Choir', 'xls/du-choir-folder2.xlsx'),
                ('g:/shared drives/Board', 'xls/du-board.xlsx', []),
                #('G:\\Shared drives\\Worship', 'xls/du-worship2.xlsx', []),
                #('c:\\', 'xls/du-c2.xlsx', []), #['WinSxS\\', 'Windows\\', 'OneDrive\\']),    
                #('C:/Users/stuar/OneDrive/Documents/fb', 'xls/du-fb.xlsx', []), 
                #('G:\\Shared drives\\Photographs\\Northlake Pics', 'xls/du-northlake-pics.xlsx'),
                #('G:\\.shortcut-targets-by-id\\0B6sDSIKItI3Tc2YwdTlhM3ItblU\\Northlake Pics', 'xls/du-s-northlake-pics.xlsx'),
                #('c:\\tmp', 'xls/du-tmp.xlsx'),
                #('G:/shared drives/music/Migration In Process', 'xls/du-m-choir.xlsx'),
                ('G:/shared drives/music', 'xls/du-music2.xlsx', []),
                #('C:/Users/stuar/OneDrive', 'xls/du-onedrive.xlsx', [] ),
                ]:

        collector = Collector(output_file, path, exclude)
        walker = FileSystemWalker(path, collector)
        walker.walk()
        collector.save()
        print('Done*******************  ', output_file)

    