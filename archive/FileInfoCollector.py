
import platform
import time
import openpyxl
from abc import ABC, abstractmethod
import os
import pwd
from MDirEntry import MDirEntry    

from abc import ABC, abstractmethod

class FService(ABC):
    """File service interface
    Methods:
    list_files(path) - list the files in the specified path
    get_file_info(file) - get an MDirEntry for a given file path
    """

    def __init__(self, service_name):
        self.service_name = service_name

    @abstractmethod
    def list_entries(self, entry):
        '''return a list of MDirEntry objects for the entries in the entry.  entry may be'''
        pass

    @abstractmethod
    def get_file_info(self, path):
        '''return an MDirEntry object for the specified file path'''
        pass

class LocalFileService(FService):
    '''Implements FService for a local win32 file system
    '''
    def __init__(self):
        super().__init__("Local File Service")

    def list_entries(self, entry):
        '''path is either a file or directory path, or it is an mdirEntry object.
        Generate and return a list of MDirEntry objects for the entries in the specified path'''
        entries = os.scandir(entry.path)
        file_entries = [MDirEntry(e.path) for e in entries]
        return file_entries
    
    def get_file_info(self, path):
        return MDirEntry(path)
    
class GDFileService(FService):
    def __init__(self):
        super().__init__("Google Drive Service")

    def list_entries(self, path):
        # Implementation for Google Drive
        pass

    def get_file_info(self, path):
        # Implementation for Google Drive
        pass

class OutputCollector:
    def __init__(self, output_file, sheet_name):
        '''Initialize an excel file to log the data'''
        self.output_file = output_file
        self.sheet_name = sheet_name
        self.workbook = openpyxl.Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = sheet_name

    def Save(self):
        '''Save the data to the output file'''
        self.workbook.save(self.output_file)

    def Headers(self, **kwargs):
        '''Set the headers to ose in the specified kwargs.
        The headers are the keys in the kwargs
        The header line is formatted bold and centered 
        '''
        self.sheet.append(kwargs.keys())
        for cell in self.sheet[1]:
            cell.font = openpyxl.styles.Font(bold=True)
            cell.alignment = openpyxl.styles.Alignment(horizontal='center')
    
    def Log(self, **kwargs):
        '''Log the data in the specified kwargs'''
        self.sheet.append(kwargs.values())

class FileInfoCollector:
    '''FileInfoCollector 
    It sends to the output collector to be logged typically in excel, a CSV file or other DB.
    Columns of data to be logged:
     Path to file
     File name
     File size
     Modification date and time (aka mtime)
     Owner - name of the owner of the file
     ModifiedBy - name of the person who most recently modified the file
     Error - any error that occurred while trying to collect the file information    
    For directories:
      The file size is the size of all files below that directory in the hierarchy
      It also logs the following:
        RMPath - Path to the most recently modified file in the hierarchy
        RMName - Name of the most recently modified file in the hierarchy
        RMModifier - Name of the user who most recently modified the file
    details for each file including the path, name, size, modification date, and owner.
    For the folders below it, it reports the size as the total size of all files below that folder, and the modification time as the latest modification time of any file below that folder, along with the path, name and owner of that most recently modified file.
    It uses MDirEntry internally to represent directory entries. It also uses a direntry to track the most recently modified file in the hierarchy

    Attributes:
    path - the path to the directory to be traversed
    service - the file service to use to access the file system
    output_collector - the output collector to log the data
    file_count - the number of files processed
    current_file - the name of the file currently being processed
    progress_update_interval - the interval in seconds to update the progress
    most_recent_file - MDirEntry of the most recently modified file in the hierarchy

    Methods:
    FileInfoCollector(output_collector) - initialize a collector and where to put it.
    collect_folder(path) - traverses the directory and logs the file information
    save_to_excel(data, output_file) - saves the data to the output file
    '''
    
    def __init__(self, fileservice, output_collector):
        self.output_collector = output_collector
        self.service = fileservice
        self.file_count = 0
        self.current_file = ""
        self.progress_update_interval = 10
        self.most_recent_file = MDirEntry()

    def collect_folder(self, folder):
        '''Traverse the directory and log the file information'''
        self._collect_folder(path)

    def _collect_folder(self, folder):
        '''Recursively traverse the hierarchy under path
        returns an MDirEntry for the most recently modifile
        Logs results in the output collector
        '''
        def _collect_folder(self, path):
            '''Recursively traverse the hierarchy under path
            returns an MDirEntry for the most recently modified file
            Logs results in the output collector
            '''
            entries = self.service.list_entries(path)
            for entry in entries:
                if entry.is_directory():
                    tfsize, tfcount, mrecent = self._collect_folder(entry.path)
                    entry.size = tfsize
                else:
                    file_info = self.service.get_file_info(entry.path)
                    self.output_collector.Log(
                        Path=file_info.path,
                        FileName=file_info.name,
                        FileSize=file_info.size,
                        ModificationDateTime=file_info.mtime,
                        Owner=file_info.owner,
                        ModifiedBy=file_info.modified_by,
                        Error=file_info.error
                    )
                    if file_info.mtime > self.most_recent_file.mtime:
                        self.most_recent_file = file_info

