import os
import pickle
import logging
import time
import json
import sys


from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from GDService import authenticate, retry_request

# DRY_RUN is a flag that can be set to True to prevent any changes from being made.
DRY_RUN = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger_handler = logging.FileHandler('gdcopy.log') # log to a file
logger.addHandler(logger_handler)

# Set up a post processing logger to log both to the standard logger and to a file information that needs to be reviewed.
post_logger = logging.getLogger('post_processing')
post_logger.setLevel(logging.INFO)
post_handler = logging.FileHandler('post_processing.log')
post_logger.addHandler(post_handler)

# post_logger starting including the date and time when starting.
post_logger.info(f"*****************************\nPost processing started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} \nDRY_RUN={DRY_RUN}\n*****************************")

# Function to remove a file from Google Drive, including files on Shared Drives
def remove_file(drive_service, file_id):
    try:
        drive_service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info(f"File with ID {file_id} has been removed successfully.")
        return None
    except Exception as error:
        logger.info(f"An error occurred while removing {file_id} {error}")
        return error

def get_file(service, file_id):

    try:
        file = service.files().get(
            fileId=file_id,
            supportsAllDrives=True,
            fields="id, name, mimeType, size, parents, modifiedTime, createdTime, description, starred, trashed, webViewLink, webContentLink, owners, permissions"
        ).execute()

        #print(f"File ID: {file['id']}")
        #print(f"File Name: {file['name']}")
        #print(f"MIME Type: {file['mimeType']}")
        #print(f"Size: {file.get('size', 'N/A')} bytes")
        #print(f"Parents: {file.get('parents', [])}")
        #print(f"Modified Time: {file['modifiedTime']}")
        #print(f"Created Time: {file['createdTime']}")
        #print(f"Description: {file.get('description', 'N/A')}")
        #print(f"Starred: {file['starred']}")
        #print(f"Trashed: {file['trashed']}")
        #print(f"Web View Link: {file.get('webViewLink', 'N/A')}")
        #print(f"Web Content Link: {file.get('webContentLink', 'N/A')}")
        #print(f"Owners: {file.get('owners', [])}")
        #print(f"Permissions: {file.get('permissions', [])}")
        return file
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None
    
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
            fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime, createdTime, description, starred, viewersCanCopyContent, writersCanShare, trashed, shortcutDetails)",
            pageToken=page_token
        ).execute()
        items.extend(results.get('files', []))
        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break

    return items
def lft(service, folder_id, drive_id=None):
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
            fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime, createdTime, description, starred, viewersCanCopyContent, writersCanShare, trashed)",
            pageToken=page_token
        ).execute()
        items.extend(results.get('files', []))
        page_token = results.get('nextPageToken', None)
        if page_token is None:
            break

    return items


def copy_file(service, file_id, parent_folder_id, file_metadata, drive_id=None):
    """Copy a file to the given folder and preserve metadata."""
    #file = retry_request(service.files().get, fileId=file_id, fields="name, mimeType, parents", supportsAllDrives=True)
    file = file_metadata
    copied_file = {
        'name': file['name'],
        'parents': [parent_folder_id],
        'description': file_metadata.get('description', '')
    }
    copied = retry_request(service.files().copy, fileId=file_id, body=copied_file, supportsAllDrives=True)
    return copied

def copy_file_item(service, file, parent_folder_id, file_metadata, drive_id=None):
    """Copy a file to the given folder and preserve metadata."""
    #file = retry_request(service.files().get, fileId=file_id, fields="name, mimeType, parents", supportsAllDrives=True)
    file_id = file['id']
    copied_file = {
        'name': file['name'],
        'parents': [parent_folder_id],
        'description': file_metadata.get('description', '')
    }
    copied = retry_request(service.files().copy, fileId=file_id, body=copied_file, supportsAllDrives=True)
    return copied

def copy_comments(drive_service, source_file_id, target_file_id):
    """Copy comments from the source file to the target file."""
    comments = retry_request(drive_service.comments().list, fileId=source_file_id, fields="comments(content, author, createdTime, modifiedTime, resolved, replies(author, content, createdTime, modifiedTime))")
    comment_count = 0
    if 'comments' in comments:
        for comment in comments['comments']:
            comment_count += 1
            # Include author information, resolved status, and modified time in the comment content
            copied_comment = {
                'content': f"Original author: {comment['author']['displayName']}\nResolved: {comment.get('resolved', False)}\nModified: {comment['modifiedTime']}\n{comment['content']}",
                'createdTime': comment['createdTime']
            }
            new_comment = retry_request(drive_service.comments().create, fileId=target_file_id, body=copied_comment, fields="id, content, createdTime")
            logger.info(f"Copied comment: {copied_comment['content']}")

            # Now copy the replies
            if 'replies' in comment:
                for reply in comment['replies']:
                    # Include author information and modified time in the reply content
                    copied_reply = {
                        'content': f"Original author: {reply['author']['displayName']}\nModified: {reply['modifiedTime']}\n{reply['content']}",
                        'createdTime': reply['createdTime']
                    }
                    retry_request(drive_service.replies().create, fileId=target_file_id, commentId=new_comment['id'], body=copied_reply, fields="id, content, createdTime")
                    logger.info(f"Copied reply: {copied_reply['content']}")
    else:
        logger.info(f"No comments found in file ID: {source_file_id}")
    return comment_count

tfile_count = 0
tfolder_count = 0
nfile_count = 0
nfolder_count = 0

def k_nmt(item):
    # if the mimeType is not a folder include modifiedTime in the key
    if item['mimeType'] != 'application/vnd.google-apps.folder':
        return item['name'] + ' ' + item['modifiedTime'] + item['mimeType']
    else:
        return item['name'] + ' ' + item['mimeType']
def k_nm(item):
    return item['name'] + ' ' + item['mimeType']
def rename_duplicates(files):
    """files - List of files.  The value of an entry has 'name' and 'modifiedTime' properties. 
    Check for duplicates using the function k_nm(file) to determine the uniqueness. 
    The name for duplicates is changed adding adding an incrementing number to the end of the name.
    """
    # sort files, using k_nm(file) to extract the key for comparison from the file object
    files.sort(key=lambda x: k_nm(x))
    # create a set to hold the keys of the files that have been seen
    seen = set()
    # walk list of files, checking for duplicates
    for file in files:
        key = k_nm(file)
        if key in seen:
            # duplicate found
            # create a new name by adding a number to the end of the name.
            # note that changing the name changes the key, so we need to check the new key for duplicates

            # split the name into the name and the extension
            name, ext = os.path.splitext(file['name']) 
            i = 1
            while k_nm(file) in seen:
                
                # create a new name by adding a number to the end of the name and adding the extension if it exists
                file['name'] = name + f" ({i})"
                if ext:
                    file['name'] = file['name'] + ext
                i += 1
            post_logger.info(f"Renamed: in folder {file['parents']} {key} to {k_nm(file)}")
            # renaming the file has changed the key, so update the key
            key = k_nm(file)
        seen.add(key)

def dup_check(files):
    seen = set()
    duplicates = set()
    for file in files:
        key = k_nm(file)
        if key in seen:
            post_logger.warning(f"Duplicate: parent={file['parents']} {key}")
            logger.warning(f"Duplicate: parent={file['parents']} {key}")
            duplicates.add(key)
        else:
            seen.add(key)
    return duplicates

def diff_folders(sourceitems, destitems):
    """Identify which items are different between the source and destination folders. Exclude items that are trashed"""
    source_set = {k_nmt(item): item['parents'] for item in sourceitems if not item['trashed']}
    dest_set = {k_nmt(item):item['parents'] for item in destitems if not item['trashed']}

    # log any items in source_set that are not in dest_set
    for key in source_set:
        if key not in dest_set:
            # file is only in the source
            post_logger.info(f"< {key} {source_set[key]}")

    # log any items in dest_set that are not in source_set
    for key in dest_set:
        if key not in source_set:
            # file is only in the destination
            post_logger.info(f"> {key} {dest_set[key]}")

    return

# Sometimes we get a group of files that have been copied but we do not trust that it was
# done correctly, and want to remove them so the next run of the script will not find the file already
# in place.  Unfortunately, the remove_file() function is getting a permission error, even though
# the associated drivemigration account has content manager permissions.  So the workaround
# is below, where we print out the webviewlink and trashed state of the files we want to remove and
# then click on that link and manually move the file to trash.

removeids = [ "1yA1en66XwzFTxgYYPtUwT9zEWjq07sCJlCUX0NNKM7U",
              "1IJmmUcxw3dF7hyjUjJxFjwP-nqjY9jH-ilw5eAdcORk"
            ]
def remove_files(drive_service,drive_id=None):
    """
    Remove the files from the destination folder.
    Print the name, mimetype, modifiedTime, and trashed state of each of the ids in removeids"""
    for id in removeids:
        try:
            file = get_file(drive_service, id)
            if file:
                logger.info(f"{file['webViewLink']}  {file['trashed']}")
                # see comment above for why we are not using remove_file()
                #x = remove_file(drive_service, id)
                #if x:
                #    logger.error(f"Error: {x}")
            else:
                logger.info(f"Remove: {id} not found")
        except HttpError as error:
            logger.error(f"Error: {error}")
            #post_logger.error(f"Error: {error}")

shortcut2target_folder = [] # list of source shortcut id and destination parent folder id.  Will create a shortcut in the destination folder after all processing is done
src2dest = {} # key is the source id.  value is src:file and dst:file which is the respective src and dst file object

def fix_shortcuts(drive_service):
    # for each of shortcuts, get the shortcutID from the details, update the targetid to the new targetid from the src2dest map and create a shortcut in the destination folder
    for shortcut in shortcut2target_folder:
        shortcut_id, dest_folder_id = shortcut
        shortcut_name = src2dest[shortcut_id]['name']
        oldtarget_id = src2dest[shortcut_id]['shortcutDetails']['targetId']

        if oldtarget_id in src2dest:
            new_target_id = src2dest[oldtarget_id]['dest_id'] # get the new target id from the src2dest map
            if new_target_id is None:
                logger.error(f"Target ID {oldtarget_id} not found in src2dest map.")
                post_logger.error(f"Target ID {oldtarget_id} not found in src2dest map.")
                continue
            new_shortcut = {
                'name': shortcut_name,
                'mimeType': 'application/vnd.google-apps.shortcut',
                'shortcutDetails': {
                    'targetId': new_target_id
                },
                'parents': [dest_folder_id]
            }
            if DRY_RUN:
                continue
            copied_shortcut = retry_request(drive_service.files().create, body=new_shortcut, supportsAllDrives=True, fields='id')
            post_logger.info(f"Copied shortcut: {shortcut_name} {oldtarget_id} to {new_target_id} {copied_shortcut}")
        else:
            logger.error(f"Fix Shortcut: {shortcut_name} {shortcut_id} target {oldtarget_id} not found in src2dest map.")
            post_logger.error(f"Fix Shortcut: {shortcut_name} {shortcut_id} target {oldtarget_id} not found in src2dest map.")

def copy_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id=None):
    """Recursively copy a folder and its contents."""
    global tfile_count,nfile_count,tfolder_count,nfolder_count

    # Get all items in the destination folder once
    existing_items = list_files(drive_service, dest_folder_id, drive_id)
    existing_files = {k_nmt(item): item for item in existing_items if item['mimeType'] != 'application/vnd.google-apps.folder' and item['trashed'] == False }
    existing_folders = {item['name']: item for item in existing_items if item['mimeType'] == 'application/vnd.google-apps.folder' and item['trashed'] == False }
    
    # Get all items in the source folder
    items = list_files(drive_service, src_folder_id, drive_id)
    #dup_check(items)
    rename_duplicates(items)

    diff_folders(items, existing_items) # log the differences between the source and destination folders

    for item in items:
    
        src2dest[item['id']] = item
        src2dest[item['id']]['dest_id'] = None

        if item['name'] == 'Copy of NUUC Congregational Vote 2020-04-19':
            print(f"Found It: {item}")
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            tfolder_count += 1
            srcname = item['name']
            if srcname in existing_folders:
                created_folder_id = existing_folders[srcname]['id']
                src2dest[item['id']]['dest_id'] = created_folder_id 

                logger.info(f"Folder {srcname} exists. use exiting ID: {created_folder_id}")
            else:
                # Create the new folder
                new_folder = {
                    'name': srcname,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [dest_folder_id]
                }
                if DRY_RUN:
                    continue
                created_folder = retry_request(drive_service.files().create, body=new_folder, supportsAllDrives=True, fields='id')
                created_folder_id = created_folder['id']
                logger.info(f"Created folder: {item['name']} (ID: {created_folder_id})")
                existing_folders[srcname] = created_folder  # Add the new folder to the existing folders map
                src2dest[item['id']]['dest_id'] = created_folder_id 
                nfolder_count += 1

            # Recursively copy the contents of the folder
            copy_folder(drive_service, docs_service, sheets_service, slides_service, item['id'], created_folder_id, drive_id)
        else:
            tfile_count += 1
            if item['mimeType'] == 'application/vnd.google-apps.shortcut':
                shortcut2target_folder.append( [item['id'], dest_folder_id])
                post_logger.info(f"Shortcut: {item}")
                src2dest[item['id']]['dest_id'] = None
                continue

            if k_nmt(item) in existing_files:
                logger.info(f"File exists {k_nmt(item)} src ID {item['id']} in folder {dest_folder_id}. Skipping.")
                src2dest[item['id']]['dest_id'] = existing_files[k_nmt(item)]['id']
                continue

            logger.info(f"Copying file: {item['name']} (ID: {item['id']})")
            post_logger.info(f"Copy: {item['name']} {item} from {src_folder_id} to {dest_folder_id}")

            if DRY_RUN:
                continue
            # continue unless item['name'] starts with '2020-08-01 Music Director Contract'
            if not item['name'].startswith('2020-08-01 Music Director Contract'):
                pass
            copied_file = {}
            copied_file = copy_file(drive_service, item['id'], dest_folder_id, item, drive_id)
            if copied_file:
                src2dest[item['id']]['dest_id'] = copied_file['id']
                nfile_count += 1
                logger.info(f"Copied file: {item['name']} (ID: {copied_file['id']})")
                post_logger.info(f"Copied: {item['name']} {copied_file}")

                # Copy the comments if this mime type supports comments.
                if item['mimeType'] in [
                        "application/vnd.google-apps.document",
                        "application/vnd.google-apps.spreadsheet",
                        "application/vnd.google-apps.presentation",
                        "application/vnd.google-apps.drawing"
                    ]:
                    copy_comments(drive_service, item['id'], copied_file['id'])
                    # updating the modified time after copying comments may not work if applied right away.
                    # probably should collect these ids for later processing.  At least this copy in 
                    # the post_logger data will be relatively easy to turn into a list of ids to process.
                    # discovered this while copying the board folder.  The modifiedTime was not updated on many
                    # files that had comments
                    post_logger.warning(f"Copied comments: modifiedTime may be wrong {copied_file['id']}")

                # Update modified time after copying comments if they exist
                update_file = {}
                if 'modifiedTime' in item:
                    update_file['modifiedTime'] = item['modifiedTime']
                if update_file:
                    update = retry_request(drive_service.files().update, fileId=copied_file['id'], body=update_file, fields='id, modifiedTime', supportsAllDrives=True)
                    post_logger.warning(f"Updated: {item['name']} {update_file} {update}")
                # Add the new file to the existing files map
                existing_files[k_nmt(item)] = copied_file
    logger.info(f"Folder {src_folder_id} copied to {dest_folder_id} - folders={nfolder_count}/{tfolder_count} files={nfile_count}/{tfile_count}.")


# for every itemm in src2dest, update the modifiedTime of the file specified by the dest_id
def fix_update_modified_time(drive_service):
    for src_id in src2dest:
        if src2dest[src_id]['dest_id']:
            file = src2dest[src_id]
            # only update modified time for files that are capable of having comments
            if file['mimeType'] in [
                    "application/vnd.google-apps.document",
                    "application/vnd.google-apps.spreadsheet",
                    "application/vnd.google-apps.presentation",
                    "application/vnd.google-apps.drawing"
                ]:
                update_file = {}
                if 'modifiedTime' in file:
                    update_file['modifiedTime'] = file['modifiedTime']
                if update_file:
                    update = retry_request(drive_service.files().update, fileId=file['dest_id'], body=update_file, fields='id, modifiedTime', supportsAllDrives=True)
                    post_logger.warning(f"Updated: {file['name']} {update_file} {update}")

# in messing with this, I suspected that copying comments was interfereing with updating the modifiedTime
# so in the final Board run, I did not copy comments inline, but am doing it in this fix function and 
# will update the modified time if needed.
#
# for every item in src2dest that is a mimetype that supports comments, copy the comments from the src file to the dest file
def fix_copy_comments(drive_service):
    for src_id in src2dest:
        file = src2dest[src_id]
        if file['mimeType'] in [
                "application/vnd.google-apps.document",
                "application/vnd.google-apps.spreadsheet",
                "application/vnd.google-apps.presentation",
                "application/vnd.google-apps.drawing"
            ]:
            if copy_comments(drive_service, src_id, file['dest_id']):
                # Update modified time after copying comments if they exist
                update_file = {}
                if 'modifiedTime' in file:
                    update_file['modifiedTime'] = file['modifiedTime']
                if update_file:
                    update = retry_request(drive_service.files().update, fileId=file['dest_id'], body=update_file, fields='id, modifiedTime', supportsAllDrives=True)
                    post_logger.info(f"Update modifiedTime: {file['name']} {update_file} {update}")


#################################################################################
src2dest = {} # map source id to destination id
shortcut2target_folder = [] # list of shortcuts and target parent folder id.  Will create a shortcut in the target folder after all processing is done

def load_state():
    global src2dest, shortcut2target_folder
    try:
        with open('gdcopy_state.json', 'r') as f:
            state = json.load(f)
            src2dest = state.get('src2dest', {})
            shortcut2target_folder = state.get('shortcuts_to_copy', [])
    except FileNotFoundError:
        src2dest = {}
        shortcut2target_folder = []

    # load an older state so we can merge in the changes from the current run.  So we start with the old state, and add in any of the current state values.
    with open('gdcopy_state_old.json', 'r') as f:
        state = json.load(f)
        old_src2dest = state.get('src2dest', {})
        old_shortcut2target_folder = state.get('shortcuts_to_copy', [])
        for key in src2dest:
            old_src2dest[key] = src2dest[key]
        src2dest = old_src2dest

        # to merge the shortcuts, we need to start with the old shortcuts, then any add it to the old shortcuts.  And any where the source id is already in the old shortcuts, we replace the old entry with the new entry.
        for shortcut in shortcut2target_folder:
            found = False
            for i, old_shortcut in enumerate(old_shortcut2target_folder):
                if shortcut[0] == old_shortcut[0]:
                    old_shortcut2target_folder[i] = shortcut
                    found = True
                    break
            if not found:
                old_shortcut2target_folder.append(shortcut)
        shortcut2target_folder = old_shortcut2target_folder


def save_state():
    state = {'src2dest': src2dest, 'shortcuts_to_copy': shortcut2target_folder}
    with open('gdcopy_state.json', 'w') as f:
        json.dump(state, f)

def copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id=None):
    """Copy the shared folder to the destination folder."""
    # load the state information from 'gdcopy_state.json' into src2dest and shortcuts_to_copy
    # if the file does not exist, create it with an empty dictionary
    load_state()

    #fix_copy_comments(drive_service)
    #fix_update_modified_time(drive_service)

    # Recursively copy the folder
    #copy_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id)

    # fix the shortcuts
    try:
        fix_shortcuts(drive_service)
        pass
    except Exception as error:
        logger.error(f"An error occurred while fixing shortcuts: {error}")
        post_logger.error(f"An error occurred while fixing shortcuts: {error}")
    
    # save the state information to 'gdcopy_state.json'
    save_state()


if __name__ == '__main__':
    drive_service, docs_service, sheets_service, slides_service = authenticate()

 #   list_files_in_folder(drive_service,  '0B6sDSIKItI3Tc2YwdTlhM3ItblU')
 #   sys.exit(0)

 #   remove_files(drive_service)
 #   sys.exit(0)

    #src_folder_id = '0B6XHzr6S7-pNYmpnZUtGYWo5MWc' #worship tech
    #src_folder_id = '10U4Fge5HedwwhUBffDbSRAnieYkqMwAK' #Tools
    #src_folder_id = '0B6XHzr6S7-pNeUd3Ml94YWJRR1k' # slide decks
    #src_folder_id = '0B1eJGEE-irYSRWQtOHVGV1dSSjQ' # roles, job descriptions, tech manuals
    #src_folder_id = '10EHK0vwbLpcC13C4vZwkDL82QKKrk15V' # WTD
    #src_folder_id = '0B6XHzr6S7-pNWXptcFRMajdod1U' # Recorded Services
    #src_folder_id = '15_bdrzpn-vkKpF0amQj9T4927JBP_8Wd' # moving remainder WTD
    #src_folder_id = '0B6sDSIKItI3Tc2YwdTlhM3ItblU' # Shared by Sandy N - Northlake Pics
    #
    #dest_folder_id = '106C-FLrlOCuejf7QU0FYxrT3MYQeCFWt' # worchp - Migration Test - see Stuart
    #dest_folder_id = '1wWO9BBjf93i2idvNk5mxe7sAdCrmnT4R' # Migration Test - Technology
    #dest_folder_id = '1ZPKFmrlzQXx6m-BuH8aCd16N_gOJ7N3q' # Migration Test - Technology Tools
    #dest_folder_id = '1myJqVJLJ6fCCHMAjqjbq9NfLyaF424Dv' # Migration Test - Technology Slide Decks
    #dest_folder_id = '1X7DDaWHurRoMIm_GLg6byB_bmRa5p7bo' # Migration Test - Technology Roles, Job Descriptions, Tech Manuals
    #dest_folder_id = '10EMSMU_pGVwUYh93JlUhAtEE6MVFGw6c' # Migration Test - Technology WTD
    #dest_folder_id = '1kZ92_oYv8geyKII7AirLef8Mz6m2AtBt' # Migration Test - Technology Recorded Services
    #dest_folder_id = '15erui30QPLSkZmZHEyrRsUoXoqwFVVqB' # Migration Test - Remaining WTD
    #drive_id = '0AFrbcK92qvQTUk9PVA'  # Worship Add your shared drive ID here if applicable
    
    #drive_id = '0ALdpykEykQl5Uk9PVA'  # Photographs
    #dest_folder_id = '1Kz-YuX8HYcD8WI63KQnkGM9IVldb2cO7' # Photographs - Northlake Pics

    
    #src_folder_id = '0B6XHzr6S7-pNN28weFpaaW1OUEk' # Choir
    #drive_id = '0AAPN5LAx_Q0ZUk9PVA'  # Music drive
    #dest_folder_id = '15UyDT8lUZptwsTvZ54Wjwnv26bvOEDJJ' # Music Migration
    
    src_folder_id = '0B1x393HDt_uqam1HTlhQcy12YW8' # Northlake Board shared folder
    drive_id = '0AKWZBbyOteK0Uk9PVA' # Board drive
    dest_folder_id = '1NyEXBW24Z9ZWijOjxwKfhKdNbk7xgTpJ' # Board Migration Work In Process

    dest_folder_id = '1p3mejJZS99_WD8iA8a9qUC05_STvbyd2' #Board / MIP See Stuart
    src_folder_id = '0B0N3H048FdBwdU13LUJWRFVPeWs' # Board Minutes
    copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id)

    src_folder_id = '1U1yx5r6YUZ1G_MSK7EeqDwQrzhrFCiDM' # Leadership Council
    copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id)

    src_folder_id = '0B0N3H048FdBwUXhfZElGQV82RzA' # Personnel
    copy_shared_folder(drive_service, docs_service, sheets_service, slides_service, src_folder_id, dest_folder_id, drive_id)


    logger.info("Copy operation completed.")
