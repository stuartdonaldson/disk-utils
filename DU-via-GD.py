import os
import time
import string
import GDCopy.GDService as GDService
import json

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

import os
import time

# Base class defining the shared interface for CDirEntry and GDriveEntry
# properties include path, name, size, mtime, type, cloud, localsize, owner, type, modified_by

class BaseEntry:
    COMMON_ATTRIBUTES_AND_DEFAULTS =   {'path': '', 'name': '', 'size': 0, 'mtime': 0, 'type': 'F', 'localsize': 0, 'owner': '', 'modified_by': ''}
    
    def __str__(self):
        return f"{self.path} {self.size} {self.strmtime()}"

    def __init__(self, path):
        if (isinstance(path, BaseEntry)):
            for key, value in self.COMMON_ATTRIBUTES_AND_DEFAULTS.items():
                setattr(self, key, getattr(path, key, value))
        elif (isinstance(path, dict)):
            for key, value in self.COMMON_ATTRIBUTES_AND_DEFAULTS.items():
                setattr(self, key, path.get(key, value))
        else:
            # initialize an empty entry
            for key, value in self.COMMON_ATTRIBUTES_AND_DEFAULTS.items():
                setattr(self, key, value)
            self.path = path
            self.name = os.path.basename(path)

    def is_dir(self):
        """Returns True if the entry is a directory."""
        return self.type == 'D'

    def is_cloud(self):
        return None
    
    def strmtime(self):
        """Returns a formatted modification time."""
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.mtime))

    def listfolder(self):
        return []
     
class AnonDirEntry(BaseEntry):
    def __init__(self):
        super().__init__('')
 
    
# Subclass for handling local filesystem entries
class CDirEntry(BaseEntry):
    def __init__(self, entry):
        if isinstance(entry, os.DirEntry):
            super().__init__(entry.path)
            self.size = entry.stat().st_size
            self.mtime = entry.stat().st_mtime
            self.type = 'D' if entry.is_dir() else 'F'
        elif isinstance(entry, str):
            super().__init__(entry)
            self.size = os.stat(entry).st_size
            self.mtime = os.stat(entry).st_mtime
            self.type = 'D' if os.path.isdir(entry) else 'F'
        else:
            raise ValueError("Invalid entry type for CDirEntry initialization.{entry}") 
        if self.is_cloud():
            self.localsize = 0
        else:
            self.localsize = self.size

    def is_cloud(self):
        attrs = get_file_attributes(self.path)
        # Check for specific cloud-related attribute
        return (attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS) == FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

    def _get_owner(self):
        # Platform-specific implementation for file ownership
        try:
            if os.name == 'nt':
                # Windows code to retrieve owner
                import win32security
                sd = win32security.GetFileSecurity(self.path, win32security.OWNER_SECURITY_INFORMATION)
                owner_sid = sd.GetSecurityDescriptorOwner()
                name, domain, type = win32security.LookupAccountSid(None, owner_sid)
                return f"{domain}\\{name}"
            else:
                import pwd
                return pwd.getpwuid(os.stat(self.path).st_uid).pw_name
        except Exception as e:
            return str(e)

    def listfolder(self):
        """List folder contents for local directory"""
        return [CDirEntry(entry) for entry in os.scandir(self.path)]

drive_service = None
gd_fileid_to_entry = {}

# Subclass for handling Google Drive entries
# properties include path, name, size, mtime, cloud, localsize, owner, type, modified_by

class GDEntry(BaseEntry):
    # entry is a dictionary with keys id, name, size, mtime, owner, type, modified_by
    # or a GDEntry instance
    # or a string which represents the URL or ID of the entry
    # parent is the parent folder which is derived from BaseEntry
    
    def __init__(self, entry, parent: BaseEntry=None):
        # Initialize the drive service if not already initialized
        global drive_service
        if not drive_service:
            drive_service = GDService.authenticate()[0]

        self.parent = parent

        # Initialize from another GDriveEntry instance
        if isinstance(entry, GDEntry):    
            super().__init__(entry) # copy the attributes from the entry
            self.id = entry.id
            self.fields = entry.fields
            raise ValueError("Invalid entry type for GDriveEntry initialization. GDEntry")
        elif isinstance(entry, dict):
            super().__init__(entry) # copy the attributes from the entry
            self._initialize_from_drivedata(entry)
        elif isinstance(entry, str):
            super().__init__(entry) # copy the attributes from the entry
            # Initialize from URL, drive ID, or folder ID
            drivedata = GDService.get_metadata(drive_service, entry)
            self._initialize_from_drivedata(drivedata)
            self.path = self.name
        else:
            raise ValueError("Invalid entry type for GDriveEntry initialization.")
        
        if self.parent:
            self.path = self.parent.path + '/' + self.name
        else:
            self.path = self.name

    def _initialize_from_drivedata(self, drivedata):
        """Initialize entry details from Google Drive API based on a URL or ID."""
        self.root = drivedata
        self.id = drivedata.get("id")
        gd_fileid_to_entry[self.id] = self  # map google File ID back to a GDEntry

        self.name = drivedata.get("name").replace('/', '_')
        # get the size as an integer
        self.size = int(drivedata.get('size', 0))

        modified_time= drivedata.get('modifiedTime')
        self.mtime = time.mktime(time.strptime(modified_time, "%Y-%m-%dT%H:%M:%S.%fZ"))

        # get the last modifying user and owner
        lmu = drivedata.get('lastModifyingUser', {})
        if lmu:
            self.modified_by = lmu.get('displayName', 'Unknown') + ' (' + lmu.get('emailAddress', 'Unknown') + ')'
        else:
            self.modified_by = ''
        owner = drivedata.get('owners', [{}])[0]
        if owner:
            self.owner = owner.get('displayName', 'Unknown') + ' (' + owner.get('emailAddress', 'Unknown') + ')'
        else:
            self.owner = ''

        self.owner = drivedata.get('owners', [{}])[0].get('displayName', 'Unknown')
        self.type = 'D' if drivedata.get('mimeType') == 'application/vnd.google-apps.folder' else 'F'

        self.link = drivedata.get('webViewLink')

        # get the permissions for the file
        if self.root.get('driveId'):
            self.load_permissions_from_service()
        else:
            self.load_permissions_from_file()        
        return
    
    # load the file().list() permissions into self.permissions
    # then calculate direct_permissions by comparing self.permissions with parent.permissions
    def load_permissions_from_file(self):
        perm = self.root.get('permissions', [])

        # if we have permissions, then we need to get the parent permissions
        # if we have a parent, then get the parent permissions
        # otherwise, assume the parent has no permissions
        if self.parent:
            pperm = self.parent.permissions
        else:
            pperm = []

        self.permissions = ["f:"]
        for p in perm:
            self.permissions.append(str(GDService.CPermission.from_dict(p)))

        self.direct_permissions = ["f:"]
        for p in self.permissions:
            if p not in pperm:
                self.direct_permissions.append(p)
        return

    def load_permissions_from_service(self):
        perms = ["s:"]
        dperms = ["s:"]
        for p in GDService.CPermission.from_service(drive_service, self.id):
            thisperm = str(p)
            perms.append(thisperm)
            # look at each of the permission details in the current permission, and if any of them are 
            # not in the parent permissions, then add the current permission to direct_permissions
            inherited = False
            for pd in p.permissionDetails:
                if not pd.inherited:
                    dperms.append(thisperm)
                    break
        self.permissions = perms
        self.direct_permissions = dperms
        return
            
    def listfolder(self):
        """List folder contents for Google Drive folder."""
        children = GDService.list_files(drive_service, self.id, additional_fields="lastModifyingUser, permissions(id, role, type, emailAddress, domain), webViewLink")  # Assume GoogleDriveService provides list_folder method
        fchildren = []
        for child in children:
            dentry = GDEntry(child, parent=self)
            fchildren.append(dentry)
        return fchildren
    
progress = TimedProgress()

class Permissions:
    def __init__(self, permissions):
        self.permissions = permissions
src2dest = {}
dest2src = {}

def get_original_path(file_id):
    # Ensure the state is loaded
    global dest2src, src2dest

    if not src2dest:
        with open('gdcopy_state.json', 'r') as f:
            state = json.load(f)
            src2dest = state.get('src2dest', {})

            # src2dest[id]['dest_id'] = dest_id, so invert this creating a dest2src dictionary
            dest2src = {}
            for src_id, file in src2dest.items():
                dest_id = file.get('dest_id')
                if dest_id:
                    dest2src[dest_id] = file

    # calculate the path for the original file
    # if the file_id is in dest2src, then the original path is the path of the src2dest entry, co 
    if file_id in dest2src:
        file_id = dest2src[file_id]['id']  # get the original file_id
        # walk the parents chain of src2dest[file_id] to calculate the path, only looking at the first element of parents.
        path = []
        while file_id and file_id in src2dest:
            path.append(src2dest[file_id]['name'])
            # get the parent of the current file_id if they are defined and there is a first element.
            if 'parents' in src2dest[file_id] and src2dest[file_id]['parents']:
                file_id = src2dest[file_id]['parents'][0]
            else:
                file_id = None
        path.reverse()
        return '/'.join(path)

    # If not found, return None
    return None


# FileSystemWalker walks the hierarchy of the file system under the path.
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
        self.collector = collector
        # if path starts with a drive letter and : then assume it is a local file system path and usecreate entry with CDirEntry, otherwise GDWalker
        # for a local file system path, create entry with CDirEntry, otherwise GDEntry
        if len(path) > 2 and path[1] == ':':
            self.root = CDirEntry(path)
        else:
            self.root = GDEntry(path)
    
    def walk(self):
     
        srecent, ssize, slocalsize, scount = self._walk(self.root)
        self.root.size = ssize
        self.root.localsize = slocalsize
        self.collector.add(self.root, mostrecent=srecent, filecount=scount)

    def _walk(self, folder):
        entry = None
        try:
            mostrecent = AnonDirEntry() # most recent entry in the folder
            totsize = 0
            totlocalsize = 0
            filecount = 0
            entry = None
            for entry in folder.listfolder():
                if entry.name == 'desktop.ini':
                    continue
                if entry.is_dir():
                    # get values from sub folder
                    srecent, ssize, slocalsize, scount = self._walk(entry)
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
            if entry:
                path = entry.path
            else:
                path = folder.path
            self.collector.add(entry, mostrecent=mostrecent, error=str(e), path=path)
        return mostrecent, totsize, totlocalsize, filecount
    

import csv
import win32security
import pandas as pd

class Collector:
    def __init__(self, output_file='du-default.csv', paths=[], exclude=[]):
        self.output_file = output_file
        self.exclude = exclude
        self.data_rows = []
        self.roots = paths
        self.write_headers = ['root', 'path', 'size', 'mtime', 'localsize', 'cloud',
                                'filecount',
                                'mr_path', 'mr_size', 'mr_mtime', 
                                'modified_by', 'direct_permissions',
                                'permissions', 
                                'owner', 'type', 'link', 'old_path','error']
        

    def add(self, entry, mostrecent=None, path=None, error=None, filecount=None):
        adding = {}
        if entry:
            adding["path"] = entry.path.encode('utf-8', errors='ignore').decode('utf-8')
            adding["name"] = entry.name.encode('utf-8', errors='ignore').decode('utf-8')
            adding["size"] = entry.size 
            adding["mtime"] = entry.strmtime()
            adding["cloud"] = entry.is_cloud()
            adding["localsize"] = entry.localsize  
            adding["owner"] = entry.owner
            adding["type"] = entry.type
            adding["modified_by"] = entry.modified_by
            adding["link"] = getattr(entry, 'link', '')
            adding["old_path"] = get_original_path(entry.id) if isinstance(entry, GDEntry) else ''

            if getattr(entry, 'permissions', None):
                # permissions is a list of CPermission instances.  Convert to a string
                adding["permissions"] = ", ".join([str(p) for p in entry.permissions])
            if getattr(entry, 'direct_permissions', None):
                adding["direct_permissions"] = ", ".join([str(p) for p in entry.direct_permissions])
                                                             
        if mostrecent:
            # make the recent path a relative path to entry.path.  
            # Assuming the left part of mostrecent.path is the same as entry.path, strip that part off.
            mr_path = mostrecent.path
            if entry and mr_path.startswith(entry.path):
                mr_path = mr_path[len(entry.path):]
            adding["mr_path"] = mr_path.encode('utf-8', errors='ignore').decode('utf-8')
            adding["mr_name"] = mostrecent.name.encode('utf-8', errors='ignore').decode('utf-8')
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

        if self.roots:
            multi = len(self.roots) > 1
            for idx in range(len(self.roots)):
                root = self.roots[idx]
                lp = len(root)
                if multi:
                    pfx = f"{idx}:"
                else:
                    pfx = ""
                if "path" in adding and adding["path"].startswith(root):
                    adding["path"] = pfx + adding["path"][lp:]
                    adding["root"] = root
                if "mr_path" in adding and adding["mr_path"].startswith(root):
                    adding["mr_path"] = pfx + adding["mr_path"][lp:]

        # return if any of the selements of self.exclude are in the string pathi
#        if any([ex in adding["path"] for ex in self.exclude]):
#            return
        # return if an item in self.exclude is contained in path and the filecount is non zero
        if any([ex in adding["path"] for ex in self.exclude]): # and not filecount:
            return
        # if we have > 1M entries, then only add the ones that have a filecount.
        if (len(self.data_rows) > 1000000) and not filecount:
            return
        if (len(self.data_rows) > 1048000):
            return
        if not adding.get('path'):
            pass
        progress.progress(f"processing {adding['path']}")
        
        self.data_rows.append(adding)
        
    def save(self):
        if self.output_file.endswith('.xlsx'):
            self.save_as_excel()
        else:
            self.save_as_csv()

    def save_as_excelx(self):
        data = pd.DataFrame(self.data_rows, columns=self.write_headers)        
        data.to_excel(self.output_file, index=False)

    def save_as_excel(self):
        import pandas as pd
        # Create a Pandas Excel writer using XlsxWriter as the engine.

        # create a Pandas Excel writer using XlsxWriter as the engine.  If there is an error creating
        # the output_file, then retry up to 5 times, appending (#) to the basename of the output file
        # incrementing each time.
        writer = None
        for i in range(5):
            base, ext = os.path.splitext(self.output_file)
            try:
                writer = pd.ExcelWriter(self.output_file, engine='xlsxwriter')
                break
            except Exception as e:
                print(f"Error creating {self.output_file}: {e}")
                self.output_file = f"{base}({i}){ext}"
                print(f"Trying {self.output_file}")

        if writer:
            # Convert the dataframe to an XlsxWriter Excel object.
            data = pd.DataFrame(self.data_rows, columns=self.write_headers)
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
            link_col = self.write_headers.index('path') if 'path' in self.write_headers else None

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
                worksheet.set_column(self.write_headers.index(col), self.write_headers.index(col), max_len+1)
            
            #set the column width for columns path and mr_path to 75
            worksheet.set_column(self.write_headers.index('path'), self.write_headers.index('path'), 75)
            worksheet.set_column(self.write_headers.index('mr_path'), self.write_headers.index('mr_path'), 10)
            worksheet.set_column(self.write_headers.index('root'), self.write_headers.index('root'), 5)

            #turn on auto filter
            worksheet.autofilter(0, 0, len(data), len(data.columns) - 1)

            # Apply the number format to all rows for `size` and `mr_size` columns if they exist.
            if size_col is not None:
                worksheet.set_column(size_col, size_col, None, num_format)
            if localsize_col is not None:
                worksheet.set_column(localsize_col, localsize_col, None, num_format)
            if mr_size_col is not None:
                worksheet.set_column(mr_size_col, mr_size_col, None, num_format)
            # Add a comment to the header labeled 'Permissions'
            header_row = 0
            p_col = self.write_headers.index('direct_permissions')
            worksheet.write_comment(header_row, p_col, 'Permissions not found in the parent.')

            p_col = self.write_headers.index('permissions')
            worksheet.write_comment(header_row, p_col, GDService.CPermission.legend(), {'width': 400, 'height': 100})
    
            writer.close()

        else:
            print(f"Error creating {self.output_file}")

    def save_as_csv(self):
        with open(self.output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # Write the headers
            writer.writerow(self.write_headers)
            
            # Write the data
            for entry in self.data_rows:
                row = [str(entry.get(header, '')) for header in self.write_headers]
                writer.writerow(row)


# test FileSystemWalker with Collector
if __name__ == '__main__':
    
    for path, output_file, exclude in [
                #('G:\\Shared drives\\Photographs', 'xls/du-photographs.xlsx'),
#                ('1HY8XzdaZ_MjG7DeUnJwSFFkRI0T5-IAt', 'xls/du-test-worship.xlsx', []),
#                ('1RmrJNxKNiinOtgjLGEm85riEv4gbww_S', 'xls/du-test.xlsx', []),
#                ('0B1x393HDt_uqam1HTlhQcy12YW8', 'xls/du-gd-board-shared.xlsx', []),
#                ('0AO1x9mFRA0upUk9PVA','xls/du-gd-administration.xlsx', []),
#                ('0AFrbcK92qvQTUk9PVA', 'xls/du-gd-worship.xlsx', []),
                #('0AKWZBbyOteK0Uk9PVA', 'xls/du-gd-board.xlsx', []),
                #('0AO1x9mFRA0upUk9PVA', 'xls/du-gd-administration.xlsx', []),
                #('0AAKmY0-DC2OqUk9PVA', 'xls/du-gd-governance.xlsx', []),
                #('0AF20wXRlCeg1Uk9PVA', 'xls/du-gd-finance.xlsx', []),
                #('1_uHpj8c6eQLLq-iO5NCNqYciobQ7dXHP', 'xls/du-gd.xlsx', []),
                #('c:/tmp', 'xls/du-tmp.xlsx', []),
                #('0B-MQKkxg8dOAZTQxNjNmZmEtNzIxNi00MDlmLWEwNmMtMjQyNjg4ZWY0Njdi', 'xls/du-worship-docs.xlsx', []),
                #('G:\\.shortcut-targets-by-id\\0B-MQKkxg8dOAZTQxNjNmZmEtNzIxNi00MDlmLWEwNmMtMjQyNjg4ZWY0Njdi\\Worship Team Docs', 'xls/du-worship-docs.xlsx'),
                #('G:\\.shortcut-targets-by-id\\0B6XHzr6S7-pNN28weFpaaW1OUEk\\Choir', 'xls/du-choir-folder2.xlsx'),
                #('g:/shared drives/Board', 'xls/du-board.xlsx', []),
                #('G:\\Shared drives\\Worship', 'xls/du-worship2.xlsx', []),
                #('0AOHETwyZCY8mUk9PVA', 'xls/du-gd-hr.xlsx', []),
                #('C:/Users/stuar/OneDrive/Documents/fb', 'xls/du-fb.xlsx', []), 
                #('G:\\Shared drives\\Photographs\\Northlake Pics', 'xls/du-northlake-pics.xlsx'),
                #('G:\\.shortcut-targets-by-id\\0B6sDSIKItI3Tc2YwdTlhM3ItblU\\Northlake Pics', 'xls/du-s-northlake-pics.xlsx'),
                #('c:\\tmp', 'xls/du-tmp.xlsx'),
                #('G:/shared drives/music/Migration In Process', 'xls/du-m-choir.xlsx'),
                #('G:/shared drives/music', 'xls/du-music2.xlsx', []),
                ("c:\\", 'xls/du-c.xlsx', ["WinSxS\\", "Windows\\", "OneDrive\\", ".lrdata\\", ".lrcat-data\\", ".lrcat\\", "$Recycle.Bin\\"]),
                ('C:/Users/stuar/OneDrive', 'xls/du-onedrive.xlsx', [] ),
                #(   [
                #    'G:\\My Drive\\Proj',
                #    'C:\\Users\\stuar\\OneDrive\\Proj'
                #    ],
                #    'xls/du-proj.xlsx', [".jpg",".git","DiskUtilization"]),
                ]:

        # if path is not a list, then make it a list
        if not isinstance(path, list):
            path = [path]
        collector = Collector(output_file, path, exclude)
        for p in path:                
            walker = FileSystemWalker(p, collector)
            walker.walk()
        collector.save()
        print('Done*******************  ', output_file)

    