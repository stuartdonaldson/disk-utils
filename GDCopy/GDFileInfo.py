import os
import time
import string
import GDService as GDService

additionalFields = "lastModifyingUser, owners, webContentLink, webViewLink, permissions(id, role, type, emailAddress, domain)"
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
            drivedata = GDService.get_metadata(drive_service, entry, additiona_fields=additionalFields)
            self._initialize_from_drivedata(drivedata)
            self.path = self.name
        else:
            raise ValueError("Invalid entry type for GDriveEntry initialization.")
        
        if self.parent:
            self.path = self.parent.path + '/' + self.name
        else:
            self.path = self.name
    def calc_path(self):
        # walk up the parents to build the path
        node = self
        path = ''
        while node:
            if path:
                path = node.name + '/' + path
            else:
                path = node.name

            parents = node.root.get('parents', [])
            if parents:
                node = GDEntry(parents[0])
            else:
                node = None
        return path
    
    def dump(self):
        # print out the calc_path, size, strmtime, localsize, owner, modified_by, Permissions, Direct Permissions, each on a line by itself, with a label identifying what is printed
        print(f"\n*******************************")
        print(f"ID:            {self.id}")
        print(f"Path:          {self.calc_path()}")
        print(f"mimeType:      {self.root.get('mimeType')}")
        print(f"Size:          {self.size}")
        print(f"Modified Time: {self.strmtime()}")
        print(f"Local Size:    {self.localsize}")
        print(f"Owner:         {self.owner}")
        print(f"Modified By:   {self.modified_by}")
        print(f"Permissions:   {self.permissions}")
        print(f"Direct Perm:   {self.direct_permissions}")
        print(f"Trashed:       {self.root.get('trashed', 'Not Found')}")
        print(f"webViewLink:   {self.root.get('webViewLink','Not found')}")
        print(f"webContentLink:{self.root.get('webContentLink','Not found')}")
        driveId = self.root.get('driveId')  
        if driveId:
            print(f"Drive ID:      {driveId}")  
            drive = drive_service.drives().get(driveId=driveId).execute()
            print("Drive Name:    {drive.get('name')}")

        return

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

        if self.root.get('driveId'):
            self.load_permissions_from_service()
        else:
            self.load_permissions_from_file()        
        return
    
    # load the file().list() permissions into self.permissions
    # then calculate direct_permissions by comparing self.permissions with parent.permissions
    def load_permissions_from_file(self):
        perm = self.root.get('permissions', [])

        # if we have a parent, then get the parent permissions so we can calculate direct_permissions
        # otherwise, assume the parent has no permissions
        if self.parent:
            pperm = self.parent.permissions
        else:
            pperm = []

        self.permissions = []
        for p in perm:
            self.permissions.append(str(GDService.CPermission.from_dict(p)))

        self.direct_permissions = []
        for p in self.permissions:
            if p not in pperm:
                self.direct_permissions.append(p)
        return

    def load_permissions_from_service(self):
        perms = []
        dperms = []
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
        children = GDService.list_files(drive_service, self.id, additional_fields=additionaFields)  # Assume GoogleDriveService provides list_folder method
        fchildren = []
        for child in children:
            dentry = GDEntry(child, parent=self)
            fchildren.append(dentry)
        return fchildren
    
progress = TimedProgress()

# given a string, create a function that creates the right entry and then prints out the entry information.  Each property is labeled
def print_entry_info(entry):
    
    if entry.is_cloud():
        print(f"{entry.path} {entry.size} {entry.strmtime()} {entry.localsize} {entry.owner} {entry.modified_by} {entry.permissions} {entry.direct_permissions}")
    else:
        print(f"{entry.path} {entry.size} {entry.strmtime()} {entry.localsize} {entry.owner} {entry.modified_by}")



# add code to test the class and print out information about the file
if __name__ == "__main__":
    # Test the CDirEntry class

    # Test the GDEntry class
    #entry = GDEntry("1u3w8jp0W34RXem8WjgHnSF96pmZcMhVY")
#    print("\n############################\n")
#    GDEntry("1GPAenFRNbNirYCWjZZP3-c0V2KEEQqkhkDXKmBEDkXg").dump()
#    print("\n############################\n")
#    GDEntry("1FCo1nYxRLqlOP4TVCyzLmPbup8tcOOC98FQA4_9Zmvo").dump()
#    GDEntry("1M6eMY_UoZ8ThntVI9-C54yPosMAklOGORF-tXST8m8Q").dump() # test file moved from mydrive to worship migration in progress
    GDEntry("1VoOhQEhz0lrrysvXRTGFO5jAnvwTCkk1y7sEKZXcu_8").dump() # martin's timesheet
    GDEntry("1K5FtuMDBf1jmppab6T2SHLHdeBykpsxu").dump() # online worship folder from margaret
    
