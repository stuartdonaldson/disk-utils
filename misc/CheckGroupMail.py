import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Replace with your credentials file path
CREDENTIALS_FILE = "GDCopy/credentials.json"
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.group.readonly',
    'https://www.googleapis.com/auth/admin.reports.audit.readonly'
]

def get_service(api_name, api_version, scopes):
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=scopes)
    
    return build(api_name, api_version, credentials=credentials)

def list_groups():
    service = get_service('admin', 'directory_v1', SCOPES)
    logging.info("Fetching groups from domain northlakeuu.org")
    results = service.groups().list(domain='northlakeuu.org').execute()
    logging.info(f"Found {len(results.get('groups', []))} groups")
    return results.get('groups', [])

def check_pending_messages(group_email):
    service = get_service('admin', 'reports_v1', SCOPES)
    
    logging.info(f"Checking pending messages for group: {group_email}")
    results = service.activities().list(
        userKey='all',
        applicationName='groups',
        filters=f'group_id=={group_email}',
        eventName='group_pending_messages'
    ).execute()

    activities = results.get('items', [])

    if not activities:
        logging.info(f"No pending messages found for group: {group_email}")
    else:
        logging.info(f"Pending messages found for group: {group_email}")
        for activity in activities:
            logging.info(f"Message ID: {activity['id']}")

if __name__ == "__main__":
    groups = list_groups()
    for group in groups:
        check_pending_messages(group['email'])
