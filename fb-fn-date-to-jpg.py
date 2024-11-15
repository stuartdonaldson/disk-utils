import os
import sys
import piexif
from PIL import Image
from datetime import datetime
import re

"""
fb-n-date-to-jpg.py

This script parses filenames to extract the author's name and a timestamp,
and updates the EXIF metadata fields in JPEG files to reflect this information.

File Naming Convention:
- The filename should follow the format: authorname_YYYY_MM_DD__HH_MM[...].jpg
- The script ignores any characters that come after the minutes in the filename.

EXIF Metadata:
- The script updates the following EXIF fields:
  - DateTime
  - DateTimeOriginal
  - DateTimeDigitized
  - Artist (Creator)

Usage:
- To update a single file:
  python fb-n-date-to-jpg.py authorname_YYYY_MM_DD__HH_MM.jpg
  
- To update all files in a directory (including subdirectories):
  python fb-n-date-to-jpg.py /path/to/directory
"""

def usage():
    """Prints the usage instructions."""
    print("""
Usage: python fb-n-date-to-jpg.py [authorname_YYYY_MM_DD__HH_MM.jpg ...] | [Folders...]

Description:
This script updates the EXIF metadata of JPEG files based on the filename.
It expects the filename to include an author's name followed by a date and time 
in the format YYYY_MM_DD__HH_MM. Any characters after the minutes in the filename 
are ignored.

Parameters:
- A list of files and/or directories. If a directory is provided, all JPEG files
  within that directory and its subdirectories will be processed.

Example:
- Single file:
  python fb-n-date-to-jpg.py john_doe_2024_09_01__12_30.jpg

- Directory:
  python fb-n-date-to-jpg.py /path/to/images
""")

def parse_filename(filename):
    """
    Parses the filename to extract the author's name and timestamp.
    Assumes the filename format: authorname_part1_part2_..._YYYY_MM_DD__HH_MM[...].jpg,
    where the date part starts with the first occurrence of a four-digit year (YYYY).
    Two underscores separate the date and time, leaving an empty string in the split parts.
    """
    base_name = os.path.basename(filename)
    name_part, _ = os.path.splitext(base_name)
    
    try:
        # Split the filename on underscores
        parts = name_part.split('_')
        
        # Find the first part that starts with 4 digits (assumed to be the year)
        for i, part in enumerate(parts):
            if re.match(r'^\d{4}$', part):
                # Extract year, month, day directly
                year = int(parts[i])
                month = int(parts[i+1])
                day = int(parts[i+2])
                
                # Skip the empty string from the double underscore
                hour = int(parts[i+4])
                minute = int(parts[i+5])
                
                author_name = '_'.join(parts[:i])
                
                # Construct the datetime object
                date_time = datetime(year, month, day, hour, minute)
                break
        else:
            # If no date part is found, raise an exception
            raise ValueError("No valid date found in filename")
        
    except (ValueError, IndexError) as e:
        print(f"Filename format error: {filename}")
        return None, None
    
    return author_name, date_time

def update_exif_data(image_path, author_name, date_time):
    """Updates the EXIF data of the image with the provided author's name and timestamp."""
    try:
        # Check if the file exists
        if not os.path.exists(image_path):
            print(f"File not found: {image_path}")
            return

        # Load the image
        image = Image.open(image_path)
        
        # Ensure it's a JPEG
        if image.format != 'JPEG':
            print(f"Unsupported image format for EXIF update: {image.format}")
            return

        # Attempt to load existing EXIF data, or start with an empty dict if loading fails
        try:
            exif_dict = piexif.load(image.info.get('exif', b''))
        except Exception as e:
            print(f"Warning: Could not load EXIF data for {image_path}. Error: {e}")
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}}

        # Format the date-time string
        date_str = date_time.strftime('%Y:%m:%d %H:%M:%S')

        # Update EXIF fields
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str.encode('utf-8')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str.encode('utf-8')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str.encode('utf-8')
        
        # Update the author name in the "Artist" field
        exif_dict["0th"][piexif.ImageIFD.Artist] = author_name.encode('utf-8')

        # Convert back to bytes
        exif_bytes = piexif.dump(exif_dict)

        # Save the image with updated EXIF data
        image.save(image_path, exif=exif_bytes)
        print(f"Updated EXIF for {image_path}: Author={author_name}, DateTime={date_str}")
    except Exception as e:
        print(f"Failed to update EXIF data for {image_path}: {e}")

def process_directory(directory):
    """Recursively processes all JPEG files in the directory and its subdirectories."""
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            author_name, date_time = parse_filename(file_path)
            if author_name and date_time:
                update_exif_data(file_path, author_name, date_time)

def main():
    """Main function that processes the provided files and directories."""
    if len(sys.argv) < 2:
        usage()
        return

    for item in sys.argv[1:]:
        if os.path.isfile(item):
            author_name, date_time = parse_filename(item)
            if author_name and date_time:
                update_exif_data(item, author_name, date_time)
        elif os.path.isdir(item):
            process_directory(item)
        else:
            print(f"Invalid path: {item}")
            usage()

if __name__ == "__main__":
    main()
