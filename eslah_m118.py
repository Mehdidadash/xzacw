#!/usr/bin/env python3
"""
eslah_m118.py
# Run Python script with parameters
/home/cnc/anaconda3/bin/python /home/cnc/linuxcnc/configs/xzacw/eslah_m118.py "$P_VAL" "$Q_VAL"
"""
import sys
import os
import time
import glob

# Add the path to your project files so we can import them
sys.path.append('/home/cnc/linuxcnc/configs/xzacw/gcode')

# Import your existing functions
from GuiLib import create_eslah
from DrawLib import create_CNC_code

def get_latest_eslh_file(output_dir, file_type):
    """Get the most recently created ESLH file"""
    pattern = os.path.join(output_dir, f"{file_type}-ESLH-*.txt")
    eslh_files = glob.glob(pattern)
    if not eslh_files:
        return None
    # Return the most recently created file
    return max(eslh_files, key=os.path.getctime)

def reset_eslah_via_signal():
    """Reset eslah button via signal (most reliable method)"""
    try:
        import subprocess
        print("Resetting eslah button via signal...")
        # Reset the signal that controls the eslah button
        subprocess.run(['halcmd', 'sets', 'eslah-reset', '0'], 
                     check=True, timeout=2.0)
        # Small delay and verify
        import time
        time.sleep(0.1)
        subprocess.run(['halcmd', 'sets', 'eslah-reset', '0'], 
                     check=False, timeout=2.0)
        print("eslah signal reset completed")
    except Exception as e:
        print(f"Note during eslah reset: {e}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 eslah_action.py <file_type> <read_count>")
        return 1
    
    # Parameters from M118 (already converted to integers in M118.sh)
    file_type_num = int(sys.argv[1])  # P value: file type as number
    read_count = int(sys.argv[2])     # Q value: read count
    
    # Map numeric file type to string
    file_type_map = {
        0: "SX",
        1: "S1", 
        2: "S2",
        3: "F1",
        4: "F2",
        5: "F3"
    }
    
    file_type = file_type_map.get(file_type_num, "F2")  # Default to F2 if invalid
    
    print(f"eslah Action: file_type={file_type}, read_count={read_count}")
    
    # Fixed directory paths
    standard_folder = "/home/cnc/linuxcnc/configs/xzacw/gcode"
    main_folder = "/home/cnc/linuxcnc/configs/xzacw"
    eslh_output_dir = os.path.join(standard_folder, "StandardDimentions", file_type)
    
    try:
        # Step 1: Create ESLH file (only if Q > 0)
        if read_count > 0:
            print("Step 1: Creating ESLH file...")
            
            # Get existing ESLH files before creation
            existing_eslh_files = glob.glob(os.path.join(eslh_output_dir, f"{file_type}-ESLH-*.txt"))
            
            # Create ESLH file
            create_eslah(standard_folder, file_type, read_count)
            
            # Wait a moment for file system to update
            time.sleep(0.5)
            
            # Check if new ESLH file was created
            new_eslh_files = glob.glob(os.path.join(eslh_output_dir, f"{file_type}-ESLH-*.txt"))
            
            if len(new_eslh_files) <= len(existing_eslh_files):
                print("ERROR: No new ESLH file was created!")
                return 1
            
            # Get the newly created file
            latest_eslh_file = get_latest_eslh_file(eslh_output_dir, file_type)
            if latest_eslh_file and os.path.exists(latest_eslh_file):
                print(f"ESLH file created successfully: {latest_eslh_file}")
                
                # Verify file has content
                file_size = os.path.getsize(latest_eslh_file)
                if file_size == 0:
                    print("ERROR: ESLH file is empty!")
                    return 1
                    
                print(f"ESLH file size: {file_size} bytes")
            else:
                print("ERROR: Could not find the newly created ESLH file!")
                return 1
        else:
            print("Skipping ESLH creation (Q=0)")
        
        # Step 2: Create CNC code (always run if P is valid, even if Q=0)
        print("Step 2: Creating CNC code...")
        
        # Fixed parameters as you specified
        stepsize = 0.2
        maxfeed = 750
        savefilename = os.path.join(main_folder, f"{file_type.lower()}.ngc")
        IsReolix = False
        x_steps = 6
        
        # Create CNC code
        success = create_CNC_code(file_type, stepsize, maxfeed, savefilename, IsReolix, x_steps)
        
        if success:
            # Verify CNC file was created
            if os.path.exists(savefilename):
                cnc_file_size = os.path.getsize(savefilename)
                print(f"CNC code saved to: {savefilename} ({cnc_file_size} bytes)")
                print("eslah action completed successfully")
                reset_eslah_via_signal()
                return 0
            else:
                print("ERROR: CNC file was not created!")
                return 1
        else:
            print("Failed to create CNC code")
            return 1
            
    except Exception as e:
        print(f"Error in eslah action: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())