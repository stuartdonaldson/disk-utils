import os
import platform
from datetime import datetime
from GDCopy.GDService import authenticate, retry_request


class MDirEntry:
    '''
    Class to represent a directory entry.
    MDirEntry() - initializes an empty structure
    MDirEntry(mdirentry) - initializes the class with the info from another MDirEntry.
    MDirEntry(odirentry) - initializes the class based on an os.DirEntry.
    MDirEntry(gdfile) - initializes based on items returned by the Google Drive API list service.  
    MDirEntry(path, name, ftype, size, mtime, owner, mby) - initializes the class with the passed info.
        ftype = "file", "dir", "link"
        mtime = modification time
        mby = username of user that last modified the file (or owner if unavailable)
        owner = username of owner of file.
    MDirEntry._GDFileFields_ = list of fields required by the Google Drive API.
    self.type = "GD" when the file is on google drive
    self.id = unique identifier for the file, in the case of google drive, it is a tuple (drive_id, file_id)
    This should work on both a Linux and Windows environment.
    '''

    _GDFileFields_ = ['id', 'name', 'mimeType', 'modifiedTime', 'owners', 'lastModifyingUser', 'size']

    def __init__(self, *args):
        if len(args) == 1:
            if isinstance(args[0], MDirEntry):
                self._init_from_mdirentry(args[0])
            elif isinstance(args[0], os.DirEntry):
                self._init_from_odirentry(args[0])
            elif isinstance(args[0], dict):
                self._init_from_gdfile(args[0])
            else:
                raise ValueError("Invalid argument type. Expected MDirEntry, os.DirEntry, or dict.")
        elif len(args) == 7:
            self._init_from_params(*args)
        elif len(args) == 0:
            self._init_null()
        else:
            raise ValueError("Invalid number of arguments. Expected 0, 1, or 7 arguments.")

    def _init_from_mdirentry(self, mdirentry: 'MDirEntry'):
        self.path = mdirentry.path
        self.name = mdirentry.name
        self.ftype = mdirentry.ftype
        self.size = mdirentry.size
        self.mtime = mdirentry.mtime
        self.owner = mdirentry.owner
        self.mby = mdirentry.mby
        self.id = mdirentry.id
        self.type = mdirentry.type

    def _init_null(self):
        self.path = None
        self.name = None
        self.ftype = None
        self.size = 0
        self.mtime = datetime.fromtimestamp(0)
        self.owner = None
        self.mby = None
        self.id = None
        self.type = None

    def _init_from_odirentry(self, odirentry: os.DirEntry):
        self.path = odirentry.path
        self.name = odirentry.name
        self.ftype = 'dir' if odirentry.is_dir() else 'file' if odirentry.is_file() else 'link'
        self.size = odirentry.stat().st_size
        self.mtime = datetime.fromtimestamp(odirentry.stat().st_mtime)
        self.owner = self._get_owner(odirentry)
        self.mby = self._get_last_modified_by(odirentry)
        self.id = odirentry.path
        self.type = 'local'

    def _init_from_gdfile(self, gdfile: dict):
        drive_id = gdfile.get('driveId', '')
        file_id = gdfile.get('id', '')
        self.path = file_id
        self.name = gdfile.get('name', '')
        self.ftype = 'file' if gdfile.get('mimeType') != 'application/vnd.google-apps.folder' else 'dir'
        self.size = int(gdfile.get('size', 0)) if 'size' in gdfile else 0
        self.mtime = datetime.fromisoformat(gdfile.get('modifiedTime').replace('Z', '+00:00'))
        self.owner = gdfile['owners'][0]['displayName'] if 'owners' in gdfile and gdfile['owners'] else 'Unknown'
        self.mby = gdfile['lastModifyingUser']['displayName'] if 'lastModifyingUser' in gdfile else self.owner
        self.id = (drive_id, file_id)
        self._gdfile = gdfile
        self.type = 'GD'

    def _init_from_params(self, path: str, name: str, ftype: str, size: int, mtime: datetime, owner: str, mby: str):
        self.path = path
        self.name = name
        self.ftype = ftype
        self.size = size
        self.mtime = mtime
        self.owner = owner
        self.mby = mby
        self.id = path
        self.type = 'local'

    def _get_owner(self, odirentry: os.DirEntry) -> str:
        if platform.system() == 'Windows':
            return self._get_owner_windows(odirentry)
        else:
            return self._get_owner_unix(odirentry)

    def _get_owner_unix(self, odirentry: os.DirEntry) -> str:
        import pwd
        try:
            stat = odirentry.stat()
            uid = stat.st_uid
            return pwd.getpwuid(uid).pw_name
        except Exception:
            return 'Unknown'

    def _get_owner_windows(self, odirentry: os.DirEntry) -> str:
        import win32security
        try:
            sd = win32security.GetFileSecurity(odirentry.path, win32security.OWNER_SECURITY_INFORMATION)
            owner_sid = sd.GetSecurityDescriptorOwner()
            name, domain, _ = win32security.LookupAccountSid(None, owner_sid)
            return f"{domain}\\{name}"
        except Exception:
            return 'Unknown'

    def _get_last_modified_by(self, odirentry: os.DirEntry) -> str:
        # This is highly system dependent and may not be possible to get directly in a cross-platform way.
        return self._get_owner(odirentry)
    
    def __str__(self):
        return f"MDirEntry(path={self.path}, name={self.name}, ftype={self.ftype}, size={self.size}, mtime={self.mtime}, owner={self.owner}, mby={self.mby})"

# Example usage
# Create an instance using an os.DirEntry object
# odirentry = ...  # Get an os.DirEntry object from somewhere
# entry = MDirEntry(odirentry)

if __name__ == "__main__":
    # Create an instance using a dictionary
    gdfile = {
        'id': '12345',
        'name': 'example.txt',
        'mimeType': 'text/plain',
        'modifiedTime': '2022-01-01T12:00:00Z',
        'owners': [{'displayName': 'Alice'}],
        'lastModifyingUser': {'displayName': 'Bob'},
        'size': 1024
    }
    entry = MDirEntry(gdfile)

    # Create an instance using individual parameters
    entry = MDirEntry("path/to/file", "example.txt", "file", 1024, datetime(2022, 1, 1, 12, 0), "Alice", "Bob")
    print(entry)

    for d in os.scandir('.'):
        entry = MDirEntry(d)
        print(entry)