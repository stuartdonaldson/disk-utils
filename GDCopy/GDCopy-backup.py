import os
import pickle
import logging

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/presentations'
]
#CREDENTIALS = 'c:/tmp/LogGDriveData/logdrivedata-keys.json'
CREDENTIALS = 'g:/my drive/diskutilization/gdcopy/credentials.json'

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
                CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    drive_service = build('drive', 'v3', credentials=creds)
    docs_service = build('docs', 'v1', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)
    return drive_service, docs_service, sheets_service, slides_service

def list_files(service, folder_id, drive_id=None):
    """List all files in the given folder, handling pagination."""
    query = f"'{folder_id}' in parents"
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
            fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime, createdTime, description, starred, viewersCanCopyContent, writersCanShare)",
            pageToken=page_token
        ).execute()
        items.extend(results.get('files', []))
        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break

    return items


def copy_file(service, file_id, parent_folder_id, drive_id=None):
    """Copy a file to the given folder."""
    try:
        file = service.files().get(
            fileId=file_id,
            fields="name, mimeType, parents",
            supportsAllDrives=True
        ).execute()
        copied_file = {'name': file['name'], 'parents': [parent_folder_id]}
        copied = service.files().copy(
            fileId=file_id,
            body=copied_file,
            supportsAllDrives=True
        ).execute()
        return copied
    except HttpError as error:
        logger.error(f"An error occurred while copying file ID {file_id}: {error}")
        return None

def copy_comments(drive_service, source_file_id, target_file_id):
    """Copy comments from the source file to the target file."""
    try:
        comments = drive_service.comments().list(
            fileId=source_file_id,
            fields="comments(content, author, createdTime, modifiedTime, resolved, replies(author, content, createdTime, modifiedTime))"
        ).execute()
        if 'comments' in comments:
            for comment in comments['comments']:
                # Include author information, resolved status, and modified time in the comment content
                copied_comment = {
                    'content': f"Original author: {comment['author']['displayName']}\nResolved: {comment.get('resolved', False)}\nModified: {comment['modifiedTime']}\n{comment['content']}",
                    'createdTime': comment['createdTime']
                }
                new_comment = drive_service.comments().create(
                    fileId=target_file_id,
                    body=copied_comment,
                    fields="id, content, createdTime"
                ).execute()
                logger.info(f"Copied comment: {copied_comment['content']}")

                # Now copy the replies
                if 'replies' in comment:
                    for reply in comment['replies']:
                        # Include author information and modified time in the reply content
                        copied_reply = {
                            'content': f"Original author: {reply['author']['displayName']}\nModified: {reply['modifiedTime']}\n{reply['content']}",
                            'createdTime': reply['createdTime']
                        }
                        drive_service.replies().create(
                            fileId=target_file_id,
                            commentId=new_comment['id'],
                            body=copied_reply,
                            fields="id, content, createdTime"
                        ).execute()
                        logger.info(f"Copied reply: {copied_reply['content']}")
        else:
            logger.info(f"No comments found in file ID: {source_file_id}")
    except HttpError as error:
        logger.error(f"An error occurred while copying comments from {source_file_id} to {target_file_id}: {error}")
        return None

def copy_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id=None):
    """Recursively copy a folder and its contents."""
    items = list_files(drive_service, src_folder_id, drive_id)
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            # Create the new folder
            new_folder = {
                'name': item['name'],
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [dest_folder_id]
            }
            try:
                created_folder = drive_service.files().create(
                    body=new_folder,
                    supportsAllDrives=True,
                    fields='id'
                ).execute()
                logger.info(f"Created folder: {item['name']} (ID: {created_folder['id']})")
                # Recursively copy the contents of the folder
                copy_folder(drive_service, docs_service, sheets_service, slides_service, item['id'], created_folder['id'], drive_id)
            except HttpError as error:
                logger.error(f"An error occurred while creating folder {item['name']}: {error}")
        else:
            copied_file = copy_file(drive_service, item['id'], dest_folder_id, drive_id)
            if copied_file:
                logger.info(f"Copied file: {item['name']} (ID: {copied_file['id']})")
                copy_comments(drive_service, item['id'], copied_file['id'])
                # Update modified time after copying comments if they exist
                update_file = {}
                if 'modifiedTime' in item:
                    update_file['modifiedTime'] = item['modifiedTime']
#                if 'createdTime' in item:
#                    update_file['createdTime'] = item['createdTime']
                if update_file:
                    drive_service.files().update(
                        fileId=copied_file['id'],
                        body=update_file,
                        fields='id, modifiedTime',
                        supportsAllDrives=True
                    ).execute()

def copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id=None):
    """Copy the shared folder to the destination folder."""
    copy_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id)

if __name__ == '__main__':
    drive_service, docs_service, sheets_service, slides_service = authenticate()
    drive_id = '0AFrbcK92qvQTUk9PVA'  # Worship Add your shared drive ID here if applicable
    src_folder_id = '0B6XHzr6S7-pNUmVmRHRWRGpFdEE' # Worship team docs - OOS
    src_folder_id = '1cm8JITvhCcjkjH3WyPcOn8ubu7pOfnzH' # oos 2019
    src_folder_id = '0B6XHzr6S7-pNYmpnZUtGYWo5MWc' #worship tech
    #dest_folder_id = '106C-FLrlOCuejf7QU0FYxrT3MYQeCFWt' # worchp - Migration Test - see Stuart
    dest_folder_id = '1CCSF3G4KOUKgv8WIJzy9MAlmH7R4myQL' # Migration Test - OoS
    dest_folder_id = '18vZW0oR2d7CyBMQJwxvCBxjZsgRDnUBh' # Migration Test - Technology
    for item in list_files(drive_service, src_folder_id):
        logger.info(f"SRC Folder: {item['name']} ({item['mimeType']})")
        # fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime, createdTime, description, starred, viewersCanCopyContent, writersCanShare)"
        if 'modifiedTime' in item:
            logger.info(f"-Modified Time: {item['modifiedTime']}")
        if 'createdTime' in item:
            logger.info(f"-Created Time: {item['createdTime']}")
        if 'description' in item:
            logger.info(f"-Description: {item['description']}")
        if 'starred' in item:
            logger.info(f"-Starred: {item['starred']}")

    for item in list_files(drive_service, dest_folder_id, drive_id=drive_id):  
        logger.info(f"DEST Folder: {item['name']} ({item['mimeType']})")

    copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id=drive_id)
    logger.info("Copy operation completed.")

