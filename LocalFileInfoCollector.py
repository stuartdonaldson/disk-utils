import os
import pwd
import time
from FileInfoCollector import FileInfoCollector

class LocalFileInfoCollector(FileInfoCollector):
    def __init__(self, path, output_collector):
        super().__init__(path, output_collector)


    def get_owner(self, file_path):
        return pwd.getpwuid(os.stat(file_path).st_uid).pw_name

    def get_file_path(self, root, file):
        # Get the full file path given the root directory and file name
        return os.path.join(root, file)

    def get_file_size(self, file_path):
        # Get the size of the file in bytes
        return os.path.getsize(file_path)

    def get_modification_date(self, file_path):
        # Get the modification date of the file
        return os.path.getmtime(file_path)


# Example usage
if __name__ == "__main__":
    output_collector = None  # Define or import your output collector
    collector = LocalFileInfoCollector("c:/", output_collector)
    collector.traverse_directory()