import os
import pickle
import logging
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/presentations'
]

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def authenticate():
    """Authenticate the user and return the drive, docs, sheets, and slides services."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    drive_service = build('drive', 'v3', credentials=creds)
    docs_service = build('docs', 'v1', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)
    return drive_service, docs_service, sheets_service, slides_service

def retry_request(func, *args, **kwargs):
    """Retry a request in case of a transient error."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            if attempt:
                time.sleep(3 ** attempt)  # Exponential backoff
            return func(*args, **kwargs).execute()
        except HttpError as error:
            if error.resp.status in [403, 404, 500, 502, 503, 504]:
                # get the current time in printable format
                current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                logger.warning(f"*************************** Retrying due to {error.resp.status} {current_time}\n**** error: {error}")
            else:
                raise
    logger.error(f"Max retries exceeded for request: {func.__name__}")
    raise HttpError(f"Max retries exceeded for request: {func.__name__}")


def get_metadata(service, file_id, additiona_fields=None):
    """Get the metadata of a file."""

    fields = (
        "id, name, mimeType, parents, modifiedTime, createdTime, description, "
        "starred, viewersCanCopyContent, writersCanShare, shortcutDetails, driveId"
    )
    if additiona_fields:
        fields += f", {additiona_fields}"
    
    metadata = retry_request(service.files().get, 
                             fileId=file_id,
                             supportsAllDrives=True, 
                             fields=fields)
    return metadata


def list_files(service, folder_id, drive_id=None, additional_fields=None):
    """
    List all non-trashed files within a specified Google Drive folder, with support for shared drives and pagination.
    Allows for specifying additional fields to retrieve for each file.

    Args:
        service (googleapiclient.discovery.Resource): The Google Drive service object, authenticated via the Google API client library.
        folder_id (str): The ID of the folder to list contents from.
        drive_id (str, optional): The ID of the shared drive (if applicable). If provided, the function searches in this shared drive;
                                  otherwise, it defaults to the user's My Drive.
        additional_fields (str, optional): Comma-separated string of additional file metadata fields to retrieve.
                                           Possible fields include:
                                           - `id`: Unique identifier of the file.
                                           - `name`: Name of the file.
                                           - `mimeType`: MIME type of the file.
                                           - `parents`: Parent folders of the file.
                                           - `modifiedTime`: Timestamp when the file was last modified.
                                           - `createdTime`: Timestamp when the file was created.
                                           - `description`: Description of the file.
                                           - `starred`: Whether the file is starred.
                                           - `viewersCanCopyContent`: Whether viewers can copy the file's content.
                                           - `writersCanShare`: Whether writers can share the file.
                                           - `trashed`: Whether the file is in the trash.
                                           - `shortcutDetails`: Details if the file is a shortcut.
                                           - `size`: Size of the file in bytes.
                                           - `webViewLink`: URL that provides a view-only link to the file.
                                           - `webContentLink`: URL for direct download of the file content.
                                           - `thumbnailLink`: URL for a thumbnail of the file.
                                           - `iconLink`: URL for an icon representing the file.
                                           - `lastModifyingUser`: Details about the last user who modified the file.
                                           - `ownedByMe`: Whether the file is owned by the user making the request.
                                           - `permissions`: List of permissions for the file.
                                           - `folderColorRgb`: The color of the folder (if applicable).

    Returns:
        list of dict: A list of dictionaries where each dictionary contains metadata about a non-trashed file.

    Example:
        # Assuming `drive_service` is an authenticated Google Drive service instance
        folder_id = 'your-folder-id'
        files = list_files(drive_service, folder_id, additional_fields="size,webViewLink")
        for file in files:
            print(f"Name: {file['name']}, Size: {file.get('size', 'N/A')}, View Link: {file.get('webViewLink', 'N/A')}")
    """
    # Define the default fields to retrieve
    base_fields = (
        "id, name, mimeType, parents, size, modifiedTime, driveId,"
        "permissions(id, role, type, emailAddress, domain), "
        "owners, lastModifyingUser(displayName, emailAddress)"
    )
    
    # Append any additional fields specified by the user
    fields = f"nextPageToken, files({base_fields}"
    if additional_fields:
        fields += f", {additional_fields}"
    fields += ")"
    
    query = f"'{folder_id}' in parents and trashed = false"
    items = []
    page_token = None
    while True:
        if drive_id:
            corpora = 'drive'
        else:
            corpora = 'user'
        results = service.files().list(
            q=query,
            spaces='drive',
            corpora=corpora,
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields=fields,
            pageToken=page_token
        ).execute()
        
        items.extend(results.get('files', []))
        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break

    return items

# list_permissions
# https://chatgpt.com/c/67200022-8040-8002-a988-4daa590ce489

def get_permissions(service, file_id):
    """
    Retrieve the basic permissions for a specific file or folder.

    Args:
        service (googleapiclient.discovery.Resource): The authenticated Google Drive service instance.
        file_id (str): The unique ID of the file or folder for which to retrieve permissions.

    Returns:
        list of dict: A list of dictionaries where each dictionary contains basic permission information:
                      - id (str): The unique identifier of the permission.
                      - role (str): The access level granted by this permission (e.g., 'reader', 'writer', 'commenter').
                      - type (str): The type of entity the permission applies to (e.g., 'user', 'group', 'domain', 'anyone').
                      - emailAddress (str, optional): The email address associated with the permission, if applicable.
                      - domain (str, optional): The domain associated with the permission, if applicable.
                      - allowFileDiscovery (bool, optional): Whether the file can be discovered via search for 'anyone' type permissions.

    Requirements:
        - The Google Drive API should be enabled, and the `service` instance should be authenticated with sufficient
          permissions to view permissions for the specified file or folder.

    Example:
        permissions = get_permissions(drive_service, "your-file-id")
        for perm in permissions:
            print(f"Role: {perm['role']}, Type: {perm['type']}, Email: {perm.get('emailAddress', 'N/A')}")
    """
    try:
        permissions = service.permissions().list(
            fileId=file_id,
            supportsAllDrives=True,
            fields="permissions(id, role, type, emailAddress, domain, allowFileDiscovery)"
        ).execute().get('permissions', [])
        return permissions
    except Exception as e:
        print(f"An error occurred while retrieving permissions: {e}")
        return []
def get_permission_details(service, file_id):
    """
    Retrieve detailed permissions for a specific file or folder, including inheritance information.

    Args:
        service (googleapiclient.discovery.Resource): The authenticated Google Drive service instance.
        file_id (str): The unique ID of the file or folder for which to retrieve permissions and inheritance details.

    Returns:
        list of dict: A list of dictionaries, where each dictionary contains detailed permission information:
                      - id (str): The unique identifier of the permission.
                      - role (str): The access level granted by this permission (e.g., 'reader', 'writer', 'commenter').
                      - type (str): The type of entity the permission applies to (e.g., 'user', 'group', 'domain', 'anyone').
                      - emailAddress (str, optional): The email address associated with the permission, if applicable.
                      - domain (str, optional): The domain associated with the permission, if applicable.
                      - allowFileDiscovery (bool, optional): Whether the file can be discovered via search for 'anyone' type permissions.
                      - permissionDetails (list of dict): Contains inheritance details for each permission, with fields:
                          - inherited (bool): True if the permission is inherited from a parent folder.
                          - inheritedFrom (str, optional): The ID of the parent from which this permission is inherited.
                          - role (str): Role of the permission on this file (e.g., 'reader', 'writer').
                          - permissionType (str): Type of the entity (e.g., 'user', 'group', 'domain', 'anyone').

    Requirements:
        - The Google Drive API should be enabled, and the `service` instance should be authenticated with sufficient
          permissions to view detailed permissions for the specified file or folder.

    Example:
        detailed_permissions = get_permission_details(drive_service, "your-file-id")
        for perm in detailed_permissions:
            print(f"Role: {perm['role']}, Type: {perm['type']}, Inherited: {perm['permissionDetails'][0].get('inherited')}")
    """
    try:
        permissions = service.permissions().list(
            fileId=file_id,
            supportsAllDrives=True,
            fields="permissions(id, role, type, emailAddress, domain, allowFileDiscovery, permissionDetails)"
        ).execute().get('permissions', [])
        return permissions
    except Exception as e:
        print(f"An error occurred while retrieving permission details: {e}")
        return []
        # Example of the format of the return data for get_permission_details
        # {
        #     'id': '04343571417354947205',
        #     'type': 'user',
        #     'permissionDetails': [
        #         {
        #             'inherited': False,
        #             'inheritedFrom': 'root',
        #             'role': 'fileOrganizer',
        #             'permissionType': 'user'
        #         }
        #     ],
        #     'emailAddress': 'minister@northlakeuu.org',
        #     'role': 'fileOrganizer'
        # }
class CPermission:
    def __init__(self, id, type, role, emailAddress=None, domain=None, allowFileDiscovery=None, permissionDetails=None, data=None):
        self.id = id
        self.type = type
        self.role = role
        self.emailAddress = emailAddress
        self.domain = domain
        self.allowFileDiscovery = allowFileDiscovery
        self.permissionDetails = permissionDetails or []
        self.data = data
        # it turns out the role of the permissions, and role of permissionsdetails are different.
        if self.permissionDetails:
            for pd in self.permissionDetails:
                if pd.role != role:
                    pass #print (f"Role mismatch: {pd.role} vs {role}")

    @classmethod
    def from_dict(cls, data):
        # for permission details, only use the first one
        return cls(
            id=data.get('id'),
            type=data.get('type'),
            role=data.get('role'),
            emailAddress=data.get('emailAddress'),
            domain=data.get('domain'),
            allowFileDiscovery=data.get('allowFileDiscovery'),
            data=data,
            permissionDetails=[CPermissionDetail.from_dict(detail) for detail in data.get('permissionDetails', [])]
        )
    @classmethod
    def from_service(cls, service, file_id):
        permissions = get_permission_details(service, file_id)
        return [cls.from_dict(permission) for permission in permissions]

    def longform(self):
        details = "\n".join(str(detail) for detail in self.permissionDetails.longform())
        return (f"Permission ID: {self.id}\n"
                f"Type: {self.type}\n"
                f"Role: {self.role}\n"
                f"Email Address: {self.emailAddress}\n"
                f"Domain: {self.domain}\n"
                f"Allow File Discovery: {self.allowFileDiscovery}\n"
                f"Permission Details:\n{details}")
    def __str__(self):
        permissionDetailsString = ":".join(str(detail) for detail in self.permissionDetails) 
        return permission_string(self.__dict__) + permissionDetailsString
    
# function to return abbreviated string representing an individual detail of a permission

def permission_string(permission_dict):
    # Dictionary mapping for Permssion Types
    type_map = {
        'user': 'U',
        'group': 'G',
        'domain': 'D',
        'anyone': 'A'
    }
    # Dictionary mapping for Permission Roles
    permission_role_map = {
        'owner': 'O',
        'organizer': 'Z',
        'fileOrganizer': 'F',
        'writer': 'W',
        'commenter': 'C',
        'reader': 'R'
    }
    role_char = permission_role_map.get(permission_dict.get('role'),f"role='{permission_dict.get('role')}'")
    type_char = type_map.get(permission_dict.get('type'), f"type='{permission_dict.get('type')}'")
    if type_char == 'U' or type_char == 'G':
        target = "("+permission_dict.get('emailAddress','N/A').split('@')[0]+")"
    elif type_char == 'D':
        target = "@" + permission_dict.get('domain','N/A')
    else:
        target = ""


    return f"{role_char}{type_char}{target}"
        


# Properties in permissionDetails
#
# Property           | Possible Values
# ------------------ | -----------------------------------------------
# permissionType     | file, folder, teamDrive
# role               | owner, organizer, fileOrganizer, writer, commenter, reader
# inheritedFrom      | The ID of the parent from which the permission is inherited
# inherited          | true, false
# itemType           | file, folder, sharedDrive
# pendingOwner       | true, false

class CPermissionDetail:
    # class to process the permissionDetails field of a permission
    def __init__(self, inherited, inheritedFrom, role, permissionType, data=None):
        self.inherited = inherited
        self.inheritedFrom = inheritedFrom
        self.role = role
        self.permissionType = permissionType
        data = data

    @classmethod
    def from_dict(cls, data):
        return cls(
            inherited=data.get('inherited'),
            inheritedFrom=data.get('inheritedFrom'),
            role=data.get('role'),
            permissionType=data.get('permissionType'),
            data=data
        )

    def longform(self):
        return (f"  Inherited: {self.inherited}\n"
                f"  Inherited From: {self.inheritedFrom}\n"
                f"  Role: {self.role}\n"
                f"  Permission Type: {self.permissionType}")
    def __str__(self):
        # Return a condensed string representation of the permission detail, role, inherited and permission are all abbreviated to single character representations.  The email address is just the username, not the domain.
        inherited_char = '-' if self.inherited else 'D'
        # Dictionary mapping for Permission Types
        permission_type_map = {
            "member": "M",
            "file": "F",
            "folder": "D",
            "teamDrive": "T"
            }

        # Dictionary mapping for Permission Roles
        permission_role_map = {
            'owner': 'O',
            'organizer': 'Z',
            'fileOrganizer': 'F',
            'writer': 'W',
            'commenter': 'C',
            'reader': 'R'
        }

        role_char = permission_role_map.get(self.role,'-')
        permission_type_char = permission_type_map.get(self.permissionType,f"permissionType-'{self.permissionType}'")
        if len(permission_type_char) > 1:
            print(f"permission_type_char={permission_type_char}")
        return f"={inherited_char}{role_char}{permission_type_char}"


# test code for this module when the module is directly invoked
if __name__ == "__main__":
    # Authenticate the user
    drive_service, _, _, _ = authenticate()
    # Get the permissions for a specific file
    file_ids = [ 
                ("Shared Folder Worship Team Docs", '0B-MQKkxg8dOAZTQxNjNmZmEtNzIxNi00MDlmLWEwNmMtMjQyNjg4ZWY0Njdi',None),
                ("Shared Drive - Worship", '0AFrbcK92qvQTUk9PVA', '0AFrbcK92qvQTUk9PVA'),
                ]
    for name, file_id, drive_id in file_ids:
        print(f"Scanning {name}")
        list = list_files(drive_service, file_id, drive_id, additional_fields="permissions")
        for file in list:
            print(f"File: {file['name']}")
            print(f"CPermissions for {file['name']}")
            for pd in file.get('permissions', []):
                print(f"  from_dict:{CPermission.from_dict(pd)}")

            print(f"CPermissions from service for {file['name']}")
            for pd in CPermission.from_service(drive_service, file['id']):
                print(f"  from_service:{pd}")