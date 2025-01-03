"""
Script to identify all Google Docs and Word documents in a specified Google Drive folder (including subfolders)
matching a given pattern, order them by modification date (oldest first), and concatenate them into a single PDF.
Each document is preceded by a banner page with metadata.

Default parameters:
- Folder ID: '1n8l7Zw_qHABL6xr47Er4rW_8I3n6wuh3'
- Pattern: '*minutes*'

Dependencies:
- Requires the GDCopy.GDService module for authentication and Google Drive interaction.
- Google Drive API credentials in 'credentials.json'.
- Installed required Python packages: `google-api-python-client`, `PyPDF2`, `reportlab`.
"""

import os
import logging
from PyPDF2 import PdfMerger
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
from GDCopy.GDService import authenticate, list_files, retry_request
from googleapiclient.http import MediaIoBaseDownload
import win32com.client

from PyPDF2 import PdfReader
import os

class TextMerger:
    def __init__(self):
        self.text_list = []

    def append(self, text_file_path):
        if os.path.isfile(text_file_path):
            with open(text_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            self.text_list.append(text)
        else:
            print(f"File {text_file_path} does not exist.")

    def write(self, output_file_path):
        with open(output_file_path, 'w', encoding='utf-8') as f:
            for text in self.text_list:
                f.write(text)
                f.write('\n\n')  # Add a new line between documents
        print(f"Text merged and saved to {output_file_path}")

    def close(self):
        pass



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def generate_banner_page(file_metadata, output_path, file_type = 'txt'):
    """Generate a banner page as a PDF with file metadata."""

    # When the pattern YY_MM or YY_MM_DD is in the filename, extract that as a date.
    date = None
    for pattern in ['%y_%m', '%y_%m_%d']:
        try:
            date = datetime.strptime(file_metadata['name'], pattern)
            break
        except ValueError:
            pass

    if date:
        formatted_date = date.strftime('%B %Y') if len(file_metadata['name']) == 5 else date.strftime('%B %d, %Y')
    else:
        formatted_date = "Unknown"

    
    text = f"""

    *****************************************************************************
    File Path: {file_metadata.get('path', 'Unknown')}
    File Name: {file_metadata['name']}
    Modification Date: {file_metadata['modifiedTime']}
    File Size: {file_metadata.get('size', 'Unknown')} bytes
    Date: {formatted_date}
    *****************************************************************************

    """
    if file_type == 'pdf':    
        c = canvas.Canvas(output_path, pagesize=letter)
        text_object = c.beginText(50, 750)
        for line in text.strip().split('\n'):
            text_object.textLine(line.strip())
        
        c.drawText(text_object)
        c.save()
    else:
        # generate a banner file that is a txt file
        with open(output_path, 'w') as f:
            f.write(text)

import os
from googleapiclient.errors import HttpError

def download_file_with_metadata(drive_service, file_metadata, output_file, file_type='txt', follow_shortcuts=False):
    """
    Download a file from Google Drive, converting it if necessary.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_metadata (dict): Metadata of the file to process (must include `id`, `name`, and optionally `mimeType`).
        output_file (str): Full path and name for the output file.
        file_type (str): The type of file to download ('pdf' or 'txt').
        follow_shortcuts (bool): Flag to determine whether to follow shortcuts.

    Returns:
        str: Path to the downloaded file.
    """
    try:
        # Extract necessary metadata
        file_id = file_metadata['id']
        mime_type = file_metadata.get('mimeType', 'application/octet-stream')  # Default if `mimeType` is missing

        # Ensure the parent directory of output_file exists
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Function to export Google Docs file
        def export_file(file_id, output_file, mime_type):
            request = drive_service.files().export_media(fileId=file_id, mimeType=mime_type)
            with open(output_file, 'wb') as out_file:
                out_file.write(request.execute())
            print(f"File downloaded to: {output_file}")

        # Function to convert and download file
        def convert_and_download(file_id, output_file, target_mime_type):
            copy_body = {"mimeType": "application/vnd.google-apps.document"}

            copied_file = drive_service.files().copy(
                fileId=file_id,
                supportsAllDrives=True,
                body=copy_body
            ).execute()
            docs_file_id = copied_file['id']
            print(f"File converted to Google Docs with ID: {docs_file_id}")

            # Export the Google Docs file
            export_file(docs_file_id, output_file, target_mime_type)

            # Optionally delete the temporary Google Docs file
            drive_service.files().delete(fileId=docs_file_id, supportsAllDrives=True).execute()
            print(f"Temporary Google Docs file deleted: {docs_file_id}")

        if mime_type == 'application/pdf':
            if file_type == 'pdf':
                # Directly download the PDF file
                export_file(file_id, output_file, 'application/pdf')
            else:
                # Convert the PDF to Google Docs and then to text
                convert_and_download(file_id, output_file, 'text/plain')
        elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
            # Convert the Word file to a Google Docs file and export
            target_mime_type = 'application/pdf' if file_type == 'pdf' else 'text/plain'
            convert_and_download(file_id, output_file, target_mime_type)
        elif mime_type.startswith('application/vnd.google-apps.shortcut'):
            if follow_shortcuts:
                # Resolve the shortcut to the target file
                request = drive_service.files().get(fileId=file_id, fields="shortcutDetails/targetId")
                shortcut_details = request.execute()
                target_id = shortcut_details.get('shortcutDetails', {}).get('targetId')
                if target_id:
                    # Download the target file
                    target_metadata = drive_service.files().get(fileId=target_id).execute()
                    return download_file_with_metadata(drive_service, target_metadata, output_file, file_type, follow_shortcuts)
            else:
                print(f"Shortcut detected but follow_shortcuts is set to False. Skipping shortcut: {file_id}")
                return None
        elif mime_type.startswith('application/vnd.google-apps.'):
            # Directly export Google Workspace files
            target_mime_type = 'application/pdf' if file_type == 'pdf' else 'text/plain'
            export_file(file_id, output_file, target_mime_type)
        else:
            # Unsupported file type
            print(f"Unsupported file type for conversion: {mime_type} {file_id} {file_metadata['name']}")
            return None

        return output_file

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# Helper function to convert Word files to PDF
def convert_word_to_pdf(word_path, pdf_path):
    try:
        # Initialize the Word application
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True

        # make word_path and pdf_path absolute paths
        word_path = os.path.abspath(word_path)
        pdf_path = os.path.abspath(pdf_path)

        # Open the Word document
        doc = word.Documents.Open(word_path)

        # Save the document as a PDF
        doc.SaveAs(pdf_path, FileFormat=17)  # 17 is the file format for PDF

        # Close the document and quit Word
        doc.Close()
        word.Quit()

        print(f"Converted Word file to PDF: {pdf_path}")
    except Exception as e:
        print(f"Error converting Word to PDF: {e}")

def process_folder(drive_service, folder_id, pattern, output_dir, file_type='txt'):
    all_files = []

    def collect_files(folder_id, path=""):
        files = list_files(drive_service, folder_id, additional_fields="size, modifiedTime")
        for f in files:
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                collect_files(f['id'], path + f['name'] + "/")
            else:
                f['path'] = path + f['name']
                all_files.append(f)
    collect_files(folder_id)

    # Filter files matching the pattern
    matching_files = [f for f in all_files if 'name' in f and pattern.lower() in f['name'].lower()]

    # Sort files by modification date (oldest first)
    matching_files.sort(key=lambda x: x['modifiedTime'])

    # Process each matching file
    processed_files = set()

    # Local function to get basename without extension
    def get_basename(path):
        return os.path.splitext(path)[0]

    file_number = 0
    while (file_number < len(matching_files)):
        file = matching_files[file_number]
        basename = get_basename(file['path'])
        file_number += 1
        if basename in processed_files:
            logger.info(f"Skipping already processed file: {basename}")
            continue

        try:
            # output log message with number of files, out of total number of files to process, the current file path, and mime type
            logger.info(f"Processing file {file_number} out of {len(matching_files)}: {file['path']} ({file['mimeType']})")

            # Download and append the document based on file_type
            file_extension = 'pdf' if file_type == 'pdf' else 'txt'
            file_path = os.path.join(output_dir, f"{file['name']}.{file_extension}")

            # If file_path does not exist, download the file
            if not os.path.exists(file_path):
                doc_path = download_file_with_metadata(drive_service, file, file_path, file_type=file_type)
            else:
                doc_path = file_path

            if doc_path:
                # Determine the file type and set the banner file extension accordingly
                banner_extension = 'pdf' if file_type == 'pdf' else 'txt'
                banner_path = os.path.join(output_dir, f"{file['id']}_banner.{banner_extension}")

                # Generate banner page
                generate_banner_page(file, banner_path, file_type=file_type)

                file_merger.append(banner_path)
                file_merger.append(doc_path)

                # Mark this file as processed
                processed_files.add(basename)
            else:
                logger.error(f"No processing of {file['name']}")
        except Exception as e:
            logger.error(f"Failed to process file {file['path']}: {e}")

    logger.info(f"Processed {len(processed_files)} files out of {len(matching_files)}")


def main(folder_id='1n8l7Zw_qHABL6xr47Er4rW_8I3n6wuh3', pattern='*minutes*'):
    # Authenticate Google Drive API services
    drive_service, _, _, _ = authenticate()

    # Prepare output directory
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    # Initialize PDF merger
    global file_merger
    file_merger = TextMerger() #PdfMerger()

    # Start processing from the root folder
    logger.info("Starting file search...")
    process_folder(drive_service, folder_id, pattern, output_dir)

    # Save the concatenated PDF
    final_path = os.path.join(output_dir, "combined_minutes.txt")
    file_merger.write(final_path)
    file_merger.close()

    logger.info(f"PDF generation completed. Output file: {final_path}")

if __name__ == "__main__":
    import sys
#    folder_id = sys.argv[1] if len(sys.argv) > 1 else '1n8l7Zw_qHABL6xr47Er4rW_8I3n6wuh3'
    folder_id = sys.argv[1] if len(sys.argv) > 1 else '1fG-b5RZZ1WryZPd4JsiC-lVFVqgtUIwb'
    pattern = sys.argv[2] if len(sys.argv) > 2 else 'minutes'
    main(folder_id, pattern)
