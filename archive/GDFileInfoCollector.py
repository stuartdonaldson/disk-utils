import unittest
from unittest.mock import MagicMock

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os
import pickle
from FileInfoCollector import FileInfoCollector

class GoogleDriveFileInfoCollector(FileInfoCollector):
    SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

    def __init__(self, path, output_collector=None):
        super().__init__(path, output_collector=output_collector)
        self.service = self.authenticate_google_drive()

    def authenticate_google_drive(self):
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('drive', 'v3', credentials=creds)
        return service

    def traverse_directory(self):
        # Implementation for traversing directories in Google Drive
        results = self.service.files().list(
            pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print('No files found.')
        else:
            print('Files:')
            for item in items:
                print(u'{0} ({1})'.format(item['name'], item['id']))

    def collect_file_info(self, file_id):
        # Implementation for collecting file info from Google Drive
        file = self.service.files().get(fileId=file_id, fields='id, name, size, owners, modifiedTime').execute()
        print(f"Name: {file['name']}, Size: {file.get('size', 'N/A')}, Owner: {file['owners'][0]['emailAddress']}, Modified Time: {file['modifiedTime']}")

# TestGDFileInfoCollector will take a URL and open GoogleDriveFileInfoCollector to walk through the hierarchy
# under that specified path.  It will output file information for each file encountered including:
# path, name, size, modification date, and owner.  For directories, it will output the size as the total size of files under it.
# the work is to be done by the FileInfoCollector.

class TestGDFileInfoCollector(unittest.TestCase):
    class TCollector:
        def __init__(self):
            self.data = {}
            self.file_count = 0
        def add(self, path, name, size, modification_date, owner, modified_by, error):
            self.data[path] = {"name": name, "size": size, "modification_date": modification_date, "owner": owner, "modified_by": modified_by, "error": error}
            self.file_count += 1
        def dump(self):
            for k in self.data.keys():
                print(f"Path: {k}, Name: {self.data[k]['name']}, Size: {self.data[k]['size']}, Modification Date: {self.data[k]['modification_date']}, Owner: {self.data[k]['owner']}, Modified By: {self.data[k]['modified_by']}, Error: {self.data[k]['error']}")
            print(f"Total files: {self.file_count}")
    
    def setUp(self):
        # Setup mock service in GDFileInfoCollector instance
        self.oc = TCollector()
        self.path = "https://drive.google.com/drive/folders/175fIyR2ctsa1Wyz3QdnQwmH86p8dcJ52?usp=drive_link"
        self.collector = GoogleDriveFileInfoCollector(self.path, output_collector=self.oc)
        self.collector.service = MagicMock()

if __name__ == '__main__':
    unittest.main()


import unittest
from unittest.mock import MagicMock

class FileSystemWalker:
    def walk(self, directory_path):
        # Simulate file system access (to be mocked in tests)
        file_names = self.get_file_names(directory_path)
        return file_names

    def get_file_names(self, directory_path):
        # Placeholder for actual file system access logic
        pass

class TestFileSystemWalker(unittest.TestCase):
    def setUp(self):
        self.walker = FileSystemWalker()
        # Mock the get_file_names method
        self.walker.get_file_names = MagicMock(return_value=['file1.txt', 'file2.txt', 'file3.txt'])

    def test_walk(self):
        expected_files = ['file1.txt', 'file2.txt', 'file3.txt']
        directory_path = '/mock/directory'
        result_files = self.walker.walk(directory_path)
        # Verify the walk method returns the expected list of file names
        self.assertEqual(result_files, expected_files)
        # Verify get_file_names was called with the correct directory path
        self.walker.get_file_names.assert_called_with(directory_path)

if __name__ == '__main__':
    unittest.main()