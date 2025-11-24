#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
m124_handler.py - Remove eslah files for specified workpiece type
Uses existing read_ESLH_values function from the project
"""

import os
import sys
import glob
from datetime import datetime

# Add the path to import your existing functions
sys.path.append('/home/cnc/linuxcnc/configs/xzacw/gcode')

# Import your existing function
try:
    from GuiLib import read_ESLH_values
    HAS_EXISTING_LIB = True
except ImportError:
    HAS_EXISTING_LIB = False
    print("M124: Warning: Could not import read_ESLH_values from GuiLib")

class M124Handler:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.standard_dimensions_dir = os.path.join(self.base_dir, "gcode", "StandardDimentions")
        
        # Radio button to directory name mapping (same as M118)
        self.workpiece_map = {
            0: "SX",
            1: "S1", 
            2: "S2",
            3: "F1",
            4: "F2",
            5: "F3"
        }
    
    def get_workpiece_type_from_value(self, workpiece_value):
        """Convert workpiece numeric value to type string"""
        try:
            value_int = int(workpiece_value)
            return self.workpiece_map.get(value_int, "S1")
        except (ValueError, TypeError):
            return "S1"
    
    def find_eslah_files_using_existing_function(self, workpiece_type):
        """Use the existing read_ESLH_values approach to find files"""
        try:
            # First try using the existing function's logic
            folder_path = os.path.join(self.standard_dimensions_dir, workpiece_type)
            
            if not os.path.exists(folder_path):
                return []
            
            eslah_files = []
            # Use the same pattern as read_ESLH_values
            for file_name in sorted(os.listdir(folder_path)):
                if (file_name.startswith(f"{workpiece_type}-ESLH-") and 
                    file_name.endswith(".txt")):
                    file_path = os.path.join(folder_path, file_name)
                    eslah_files.append(file_path)
            
            # Sort by the numeric part in the filename (newest first)
            def get_file_number(file_path):
                filename = os.path.basename(file_path)
                # Extract number from pattern like S1-ESLH-5.txt -> 5
                try:
                    # Remove the prefix and suffix to get the number
                    number_part = filename.replace(f"{workpiece_type}-ESLH-", "").replace(".txt", "")
                    return int(number_part)
                except ValueError:
                    return 0
            
            # Sort in descending order (highest number = newest)
            eslah_files.sort(key=get_file_number, reverse=True)
            
            return eslah_files
            
        except Exception as e:
            print(f"M124: Error using existing function logic: {e}")
            return []
    
    def find_eslah_files_fallback(self, workpiece_type):
        """Fallback method if the existing function approach fails"""
        folder_path = os.path.join(self.standard_dimensions_dir, workpiece_type)
        
        if not os.path.exists(folder_path):
            return []
        
        # Get ALL files in the directory
        all_files = glob.glob(os.path.join(folder_path, "*"))
        
        # Filter for ESLH files
        eslah_files = []
        for file_path in all_files:
            if os.path.isfile(file_path):
                filename = os.path.basename(file_path)
                # Match the exact pattern used by your system
                if (filename.startswith(f"{workpiece_type}-ESLH-") and 
                    filename.endswith(".txt")):
                    eslah_files.append(file_path)
        
        # Sort by numeric part (newest first)
        def get_file_number(file_path):
            filename = os.path.basename(file_path)
            try:
                number_part = filename.replace(f"{workpiece_type}-ESLH-", "").replace(".txt", "")
                return int(number_part)
            except ValueError:
                return 0
        
        eslah_files.sort(key=get_file_number, reverse=True)
        
        return eslah_files
    
    def list_eslah_files_for_workpiece(self, workpiece_type):
        """List only the eslah files for the specified workpiece type"""
        print(f"M124: ESLH files for {workpiece_type} (newest first):")
        
        # Try using the existing function approach first
        files = self.find_eslah_files_using_existing_function(workpiece_type)
        
        # Fallback if no files found
        if not files:
            files = self.find_eslah_files_fallback(workpiece_type)
        
        if files:
            for f in files:
                file_num = self.get_file_number(f)
                print(f"  - {os.path.basename(f)} (number: {file_num})")
        else:
            print(f"  No ESLH files found for {workpiece_type}")
        return files
    
    def remove_eslah_files(self, remove_count, workpiece_value):
        """Remove specified number of NEWEST eslah files for given workpiece type"""
        workpiece_type = self.get_workpiece_type_from_value(workpiece_value)
        workpiece_dir = os.path.join(self.standard_dimensions_dir, workpiece_type)
        
        print(f"M124: Removing {remove_count} NEWEST eslah files for {workpiece_type}")
        print(f"M124: Looking in directory: {workpiece_dir}")
        
        if not os.path.exists(workpiece_dir):
            msg = f"M124: Directory not found for {workpiece_type}: {workpiece_dir}"
            print(msg)
            return False, msg
        
        # List only the specified workpiece type files
        eslah_files = self.list_eslah_files_for_workpiece(workpiece_type)
        
        if not eslah_files:
            msg = f"M124: No eslah files found for {workpiece_type} in {workpiece_dir}"
            print(msg)
            return False, msg
        
        # Limit remove_count to available files
        actual_remove_count = min(int(remove_count), len(eslah_files))
        removed_files = []
        
        print(f"M124: Found {len(eslah_files)} eslah files for {workpiece_type}")
        print(f"M124: Will remove {actual_remove_count} NEWEST files")
        
        # Remove the NEWEST files (highest numbers)
        for i in range(actual_remove_count):
            file_to_remove = eslah_files[i]
            file_number = self.get_file_number(file_to_remove)
            
            print(f"M124: Removing file {i+1}/{actual_remove_count}: {os.path.basename(file_to_remove)}")
            print(f"M124: File number: {file_number}")
            
            try:
                # Create backup before removal
                backup_dir = os.path.join(self.standard_dimensions_dir, "backup", workpiece_type)
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = os.path.join(backup_dir, f"backup_{os.path.basename(file_to_remove)}_{timestamp}")
                
                import shutil
                shutil.copy2(file_to_remove, backup_file)
                print(f"M124: Backup created: {backup_file}")
                
                # Remove the file
                os.remove(file_to_remove)
                removed_files.append(os.path.basename(file_to_remove))
                print(f"M124: SUCCESS - Removed eslah file: {os.path.basename(file_to_remove)}")
                
            except Exception as e:
                print(f"M124: ERROR - Failed to remove file {file_to_remove}: {e}")
                continue
        
        if removed_files:
            # Sort removed files by their numbers in descending order for the message
            removed_files_sorted = sorted(removed_files, key=lambda x: self.get_file_number_from_name(x), reverse=True)
            msg = f"M124: Removed {len(removed_files)} NEWEST eslah files for {workpiece_type}: {', '.join(removed_files_sorted)}"
            print(msg)
            return True, msg
        else:
            msg = f"M124: No files were removed for {workpiece_type}"
            print(msg)
            return False, msg
    
    def get_file_number(self, file_path):
        """Extract file number from file path"""
        filename = os.path.basename(file_path)
        try:
            # Extract workpiece type from filename
            workpiece_type = None
            for wt in self.workpiece_map.values():
                if filename.startswith(f"{wt}-ESLH-"):
                    workpiece_type = wt
                    break
            
            if workpiece_type:
                number_part = filename.replace(f"{workpiece_type}-ESLH-", "").replace(".txt", "")
                return int(number_part)
            return 0
        except ValueError:
            return 0
    
    def get_file_number_from_name(self, filename):
        """Extract file number from filename string"""
        try:
            # Extract workpiece type from filename
            workpiece_type = None
            for wt in self.workpiece_map.values():
                if filename.startswith(f"{wt}-ESLH-"):
                    workpiece_type = wt
                    break
            
            if workpiece_type:
                number_part = filename.replace(f"{workpiece_type}-ESLH-", "").replace(".txt", "")
                return int(number_part)
            return 0
        except ValueError:
            return 0

def main():
    # Parse command line arguments (same format as M118)
    if len(sys.argv) != 3:
        print("Usage: python3 m124_handler.py <remove_count> <workpiece_value>")
        print(f"Received args: {sys.argv}")
        return 1
    
    try:
        # Parameters from M124 (already converted to integers in M124.sh)
        remove_count = int(sys.argv[1])  # P value: number of files to remove
        workpiece_value = int(sys.argv[2])  # Q value: workpiece type as number
    except (ValueError, IndexError) as e:
        print(f"M124: Error parsing parameters: {e}")
        print(f"M124: Usage: M124 P<remove_count> Q<workpiece_type>")
        return 1
    
    print(f"M124: Starting eslah file removal...")
    print(f"M124: Parameters - remove_count: {remove_count}, workpiece_value: {workpiece_value}")
    
    handler = M124Handler()
    
    # Remove the eslah files
    success, message = handler.remove_eslah_files(remove_count, workpiece_value)
    
    # Print the final message that will be shown in LinuxCNC
    print(f"(MSG, {message})")
    
    if success:
        print("M124: Operation completed successfully")
        return 0
    else:
        print("M124: Operation completed with warnings")
        return 0  # Exit with 0 even if no files found, as this might be normal

if __name__ == "__main__":
    sys.exit(main())