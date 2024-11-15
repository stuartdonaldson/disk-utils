import os
import sys
import time
import traceback
import pandas as pd
from datetime import datetime
from pathlib import Path
from MDirEntry import MDirEntry

__doc__ = '''
This app will recursively walk through a directory hierarchy, 
'''

# Import win32security only if running on Windows
if os.name == 'nt':
    import win32security

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate file info report")
    parser.add_argument("path", nargs='?', default="C:\\tmp", help="The directory to traverse")
    parser.add_argument("output_file", nargs='?', default="du-tmp.xlsx", help="The output Excel file")
    args = parser.parse_args()

    try:
        start_time = time.time()
        data = collect_info(args.path)
        save_to_excel(data, args.output_file)
        print(f"Report generated: {args.output_file}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
