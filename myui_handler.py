#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
myui_handler.py — GladeVCP handler (complete version)
"""

import os
import subprocess
import csv
import json
from gi.repository import Gtk, GLib, Gdk
import hal_glib
import hal
import linuxcnc
class HandlerClass:
    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp
        self.builder = builder
        self.useropts = useropts

        # --- widgets (same names as your UI) ---
        self.led_gripper_out = builder.get_object('gripper_out')
        self.led_jack_in = builder.get_object('jack_in')
        self.total_machined = builder.get_object('total_machined')
        self.touchoff_display = builder.get_object('touchoff_display')
        self.test_button = builder.get_object('test_button')
        self.eslah_button = builder.get_object('eslah')
        self.workpiece_spin = builder.get_object('workpiece_type_value')

        # radio buttons
        self.radio_buttons = {
            "SX": builder.get_object("SX"),
            "S1": builder.get_object("S1"),
            "S2": builder.get_object("S2"),
            "F1": builder.get_object("F1"),
            "F2": builder.get_object("F2"),
            "F3": builder.get_object("F3"),
        }
        for name, button in self.radio_buttons.items():
            if button:
                button.connect("toggled", self.on_radio_toggled, name)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.csv_path = os.path.join(self.base_dir, "wear.csv")
        self.ngc_path = os.path.join(self.base_dir, "file.ngc")
        self.vars_file = os.path.join(self.base_dir, "variables.txt")
        self.pipe_file = os.path.join(self.base_dir, "variables_pipe.json")

        # default radio
        default = self.radio_buttons.get("S1")
        if default:
            default.set_active(True)

        # Ensure touchoff feedback / strobe pins exist as OUT
        try:
            self.halcomp.newpin("touchoff_display-f", hal.HAL_FLOAT, hal.HAL_OUT)
        except Exception:
            pass
        try:
            self.halcomp.newpin("touchoff_display-s", hal.HAL_S32, hal.HAL_OUT)
        except Exception:
            pass

        # eslah button - HALIO_Button with I/O pin
        self.eslah_button = builder.get_object('eslah')
        self.eslah_toggle_state = False
        
        if self.eslah_button:
            # COMPLETELY DISABLE HALIO_BUTTON'S DEFAULT BEHAVIOR
            # Method 1: Disconnect all signal handlers
            try:
                # Get all signal handlers and disconnect them
                self.eslah_button.handler_block_by_func(None)  # Block all
            except:
                pass
            
            # Method 2: Use button-press-event and return True to stop propagation
            self.eslah_button.connect("button-press-event", self.on_eslah_button_press)
            self.eslah_button.connect("button-release-event", self.on_eslah_button_release)
            
            # Initial sync
            self.sync_eslah_state()

        # convenience: store component name
        try:
            self.comp_name = self.halcomp.name
        except Exception:
            self.comp_name = "gladevcp"
        
        # Workpiece spinbutton initialization
        self.workpiece_spin = builder.get_object('workpiece_type_value')
        if self.workpiece_spin:
            # Connect the value-changed signal
            self.workpiece_spin.connect("value-changed", self.on_workpiece_spin_changed)
            # Set initial value
            self.workpiece_spin.set_value(1)  # Default to S1

        # Connect widget signals
        if self.touchoff_display:
            self.touchoff_display.connect("value-changed", self.on_touchoff_changed)

        if self.test_button:
            self.test_button.connect("pressed", self.on_test_button_pressed)

        # Store current values to detect changes
        self.last_hal_total_machined = 0
        self.last_hal_touchoff = 0.0


        ########wear compensation###########
         # Initialize wear compensation system FIRST
        self.init_wear_compensation()
        
        # THEN connect wear compensation spinbutton signals
        wear_spinbuttons = [
            "SX_Wear_Compensation", "S1_Wear_Compensation", "S2_Wear_Compensation",
            "F1_Wear_Compensation", "F2_Wear_Compensation", "F3_Wear_Compensation"
        ]
        
        for spinbutton_id in wear_spinbuttons:
            spinbutton = self.builder.get_object(spinbutton_id)
            if spinbutton:
                spinbutton.connect("value-changed", self.on_wear_compensation_changed)
        # periodic polls
        GLib.timeout_add(150, self._poll_hal_to_widget)
        GLib.timeout_add(100, self._poll_json_variables)

        # load variables once at startup
        GLib.idle_add(self.load_variables)

    

    def on_reload_clicked(widget=None, data=None):
        c = linuxcnc.command()
        print("Reloading file from GladeVCP…")
        c.program_reload()

    # ---------------------------
    # eslah button handling
    # ---------------------------
    def on_eslah_button_press(self, widget, event):
        """Handle button press and completely prevent default behavior"""
        print("eslah button press - blocking default")
        # Return True to stop the signal from propagating to HALIO_Button's internal handlers
        return True

    def on_eslah_button_release(self, widget, event):
        """Handle button release and implement our toggle logic"""
        try:
            # Toggle our internal state
            self.eslah_toggle_state = not self.eslah_toggle_state
            
            # Set the HAL I/O pin to our toggle state
            self.halcomp["eslah"] = self.eslah_toggle_state
            
            # Update appearance
            self.update_eslah_appearance()
            
            print(f"eslah released - toggle state: {self.eslah_toggle_state}")
            
            # If turning ON, trigger action
            if self.eslah_toggle_state:
                self.trigger_eslah_action()
            
            # Return True to stop the signal from propagating to HALIO_Button's internal handlers
            return True
                
        except Exception as e:
            print(f"Error in eslah release: {e}")
            return True


    def update_eslah_appearance(self):
        """Update eslah button appearance"""
        if self.eslah_button:
            if self.eslah_toggle_state:
                self.eslah_button.set_label("اعمال خواهد شد - کلیک برای لغو")
                self.eslah_button.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#00FF00"))
            else:
                self.eslah_button.set_label("اعمال نمیشود - کلیک برای فعال سازی") 
                self.eslah_button.modify_bg(Gtk.StateType.NORMAL, None)

    def sync_eslah_state(self):
        """Sync with HAL pin state"""
        try:
            current_state = bool(self.halcomp["eslah"])
            self.eslah_toggle_state = current_state
            self.update_eslah_appearance()
            print(f"eslah state synced: {self.eslah_toggle_state}")
        except Exception as e:
            print(f"Error syncing eslah state: {e}")

    def reset_eslah_button(self):
        """Reset eslah programmatically"""
        self.eslah_toggle_state = False
        self.halcomp["eslah"] = False
        self.update_eslah_appearance()
        print("eslah reset programmatically")

    def trigger_eslah_action(self):
        """Optional: Trigger action when eslah is turned ON"""
        # Your existing trigger code here
        print("eslah activated - action would trigger here")


    # ---------------------------
    # Workpiece spinbutton handling
    # ---------------------------
    def on_workpiece_spin_changed(self, widget):
        """Handle manual changes to workpiece spinbutton"""
        value = int(widget.get_value())
        workpiece_map = {0: "SX", 1: "S1", 2: "S2", 3: "F1", 4: "F2", 5: "F3"}
        workpiece_type = workpiece_map.get(value, "S1")
        
        print(f"Workpiece spin changed to: {value} ({workpiece_type})")
        
        # Update the radio button to match
        radio_button = self.radio_buttons.get(workpiece_type)
        if radio_button and not radio_button.get_active():
            radio_button.set_active(True)

    # ---------------------------
    # Test button
    # ---------------------------
    def on_test_button_pressed(self, widget):
        script_path = os.path.join(self.base_dir, "write_hello.py")
        if os.path.exists(script_path):
            subprocess.run(["python3", script_path], check=True)

    # ---------------------------
    # Radio buttons -> update file.ngc
    # ---------------------------
    def on_radio_toggled(self, button, workpiece_type):
        if not button.get_active():
            return
        
        print(f"Workpiece type changed to: {workpiece_type}")
        
        # Update workpiece spinbutton to match
        if self.workpiece_spin:
            workpiece_map = {"SX": 0, "S1": 1, "S2": 2, "F1": 3, "F2": 4, "F3": 5}
            spin_value = workpiece_map.get(workpiece_type, 1)
            
            # Block handler to avoid recursion
            try:
                self.workpiece_spin.handler_block_by_func(self.on_workpiece_spin_changed)
                self.workpiece_spin.set_value(spin_value)
                self.workpiece_spin.handler_unblock_by_func(self.on_workpiece_spin_changed)
            except Exception as e:
                print(f"Error updating workpiece spin: {e}")
        
        # Rest of radio button functionality
        wear_value = self.get_wear_value(workpiece_type)
        if wear_value is None:
            return
        self.update_ngc_file(workpiece_type, wear_value)

    def get_wear_value(self, workpiece_type):
        try:
            with open(self.csv_path, newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip().upper() == workpiece_type.upper():
                        return float(row[1])
        except Exception as e:
            print(f"[myui_handler] ERROR reading wear.csv: {e}")
        return None

    def update_ngc_file(self, workpiece_type, wear_value):
        if not os.path.exists(self.ngc_path):
            return
        try:
            with open(self.ngc_path, "r") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                if line.strip().startswith("#75="):
                    line = f"#75={wear_value:.5f} (wheel wear per part SX 0.0004 S1 0.0008 S2 0.00075 F1 0.0006 F2 0.0005 F3 0.0004)\n"
                if line.strip().startswith("o<"):
                    line = f"o<{workpiece_type.lower()}> call [#4] [#78] [#79] [#6] [#80]\n"
                if line.strip().startswith("#76="):
                    new_val = 26 if workpiece_type.upper() == "SX" else 30
                    line = f"#76={new_val} (total length of the part)\n"
                new_lines.append(line)
            with open(self.ngc_path, "w") as f:
                f.writelines(new_lines)
        except Exception as e:
            print(f"[myui_handler] ERROR updating file.ngc: {e}")

    # ---------------------------
    # User changed touchoff widget
    # ---------------------------
    def on_touchoff_changed(self, widget):
        try:
            val = float(widget.get_value())
        except Exception:
            return

        # Update HAL feedback and strobe pins if they exist
        try:
            self.halcomp["touchoff_display-f"] = float(val)
        except Exception:
            pass
        try:
            self.halcomp["touchoff_display-s"] = int(round(val, 0))  # Explicit rounding to 0 decimal places
        except Exception:
            pass

        # Persist change to variables.txt
        try:
            self._write_variable_to_file("touchoff", val)
        except Exception:
            pass

    # ---------------------------
    # Poll HAL -> widget (external HAL setp updates)
    # ---------------------------
    def _poll_hal_to_widget(self):


        # total_machined: read halcomp pin and update widget
        try:
            val2 = None
            try:
                val2 = int(self.halcomp["total_machined"])
            except Exception:
                val2 = None

            if val2 is not None and val2 != self.last_hal_total_machined:
                # Only update variables.txt if the change is significant (not startup zero)
                # and if we've already loaded our initial values
                if hasattr(self, 'variables_loaded') and self.variables_loaded and val2 != 0:
                    self._write_variable_to_file("total_machined", val2)
                
                self.last_hal_total_machined = val2
                if self.total_machined:
                    try:
                        # try set_value, fall back to set_label
                        try:
                            self.total_machined.set_value(int(val2))
                        except Exception:
                            try:
                                self.total_machined.set_label(str(int(val2)))
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

            # eslah state sync
        # eslah state sync for external changes
        try:
            current_hal_state = bool(self.halcomp["eslah"])
            if current_hal_state != self.eslah_toggle_state:
                print(f"eslah state changed externally: {self.eslah_toggle_state} -> {current_hal_state}")
                self.eslah_toggle_state = current_hal_state
                self.update_eslah_appearance()
        except Exception as e:
            print(f"Error polling eslah state: {e}")
        
        return True
        
    
    # ---------------------------
    # JSON pipe: M-codes write here, handler picks them up and updates widgets
    # ---------------------------
    def _poll_json_variables(self):
        """Poll for JSON variable updates with enhanced debugging"""
        pipe_file = self.pipe_file
        
        #print(f"POLL_JSON: Checking pipe file at: {pipe_file}")
        #print(f"POLL_JSON: File exists: {os.path.exists(pipe_file)}")
        
        if not os.path.exists(pipe_file):
            # Check if there are any other pipe files
            pipe_dir = os.path.dirname(pipe_file)
            all_files = os.listdir(pipe_dir)
            json_files = [f for f in all_files if f.startswith('variables_pipe')]
            if json_files:
                print(f"POLL_JSON: Found other pipe files: {json_files}")
            return True
            
        try:
            # Get file info for debugging
            file_size = os.path.getsize(pipe_file)
            file_mtime = os.path.getmtime(pipe_file)
            print(f"POLL_JSON: File size: {file_size}, mtime: {file_mtime}")
            
            # Read the file content first
            with open(pipe_file, "r") as f:
                content = f.read().strip()
                print(f"POLL_JSON: Raw content: '{content}'")
                
            if not content:
                print("POLL_JSON: Empty content, removing file")
                os.remove(pipe_file)
                return True
                
            # Parse JSON
            data = json.loads(content)
            print(f"POLL_JSON: Parsed data: {data}")
            
            # Process touchoff update
            if "touchoff" in data:
                val = float(data["touchoff"])
                print(f"POLL_JSON: Current last_hal_touchoff: {self.last_hal_touchoff}")
                print(f"POLL_JSON: New value from pipe: {val}")
                
                # Always update regardless of difference for now (for testing)
                print(f"POLL_JSON: Updating touchoff to {val}")
                
                # Update widget
                if self.touchoff_display:
                    try:
                        self.touchoff_display.handler_block_by_func(self.on_touchoff_changed)
                        self.touchoff_display.set_value(float(val))
                        self.touchoff_display.handler_unblock_by_func(self.on_touchoff_changed)
                        print(f"POLL_JSON: Widget updated to {val}")
                    except Exception as e:
                        print(f"POLL_JSON: Widget update error: {e}")
                
                # Update HAL pins
                try:
                    self.halcomp["touchoff_display-f"] = float(val)
                    print(f"POLL_JSON: HAL float pin updated to {val}")
                except Exception as e:
                    print(f"POLL_JSON: HAL float pin error: {e}")
                    
                try:
                    self.halcomp["touchoff_display-s"] = int(round(val))
                    print(f"POLL_JSON: HAL int pin updated to {int(round(val))}")
                except Exception as e:
                    print(f"POLL_JSON: HAL int pin error: {e}")
                
                # Update variables.txt
                self._write_variable_to_file("touchoff", val)
                self.last_hal_touchoff = val
                print(f"POLL_JSON: variables.txt updated to {val}")
            
            # Remove the pipe file after processing
            print("POLL_JSON: Removing pipe file after processing")
            os.remove(pipe_file)
            print("POLL_JSON: SUCCESS - File removed")
                
        except json.JSONDecodeError as e:
            print(f"POLL_JSON: JSON decode error: {e}")
            print(f"POLL_JSON: Content was: '{content}'")
            try:
                os.remove(pipe_file)
            except:
                pass
        except Exception as e:
            print(f"POLL_JSON: Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            
        return True

    # ---------------------------
    # eslah action check (if needed)
    # ---------------------------
    def check_and_run_eslah_action(self):
        """Check if eslah is active and run action"""
        if self.eslah_toggle_state:  # Changed from self.eslah_active
            print("eslah is active - running action script...")
            
            # Get workpiece value from spinbutton
            workpiece_value = 1
            if self.workpiece_spin:
                workpiece_value = int(self.workpiece_spin.get_value())
            
            # Run your Python script
            script_path = os.path.join(self.base_dir, "eslah_action.py")
            if os.path.exists(script_path):
                try:
                    subprocess.run(["python3", script_path, "1", str(workpiece_value)], check=True)
                    print("eslah action completed successfully")
                    self.reset_eslah_button()
                except subprocess.CalledProcessError as e:
                    print(f"eslah script failed: {e}")
            else:
                print(f"eslah script not found: {script_path}")

    # ---------------------------
    # Load variables.txt at startup (populate widgets)
    # ---------------------------
    def load_variables(self):
        print("[myui_handler] load_variables() called")
        print(f"[myui_handler] vars_file = {self.vars_file}")

        touchoff = 0.0
        total_machined = 0
        if os.path.exists(self.vars_file):
            with open(self.vars_file, "r") as f:
                for line in f:
                    if line.startswith("touchoff="):
                        try:
                            touchoff = float(line.strip().split("=", 1)[1])
                        except Exception:
                            pass
                    elif line.startswith("total_machined="):
                        try:
                            total_machined = int(float(line.strip().split("=", 1)[1]))
                        except Exception:
                            pass

        print(f"[myui_handler] parsed: touchoff = {touchoff}, total_machined = {total_machined}")

        # For touchoff: set widget and feedback/strobe pins
        try:
            if self.touchoff_display:
                self.touchoff_display.set_value(float(touchoff))
        except Exception:
            pass
        try:
            self.halcomp["touchoff_display-f"] = float(touchoff)
        except Exception:
            pass
        try:
            self.halcomp["touchoff_display-s"] = int(round(touchoff))
        except Exception:
            pass

        # For total_machined: just update widget (M115 will handle HAL pin)
        try:
            if self.total_machined:
                try:
                    self.total_machined.set_value(int(total_machined))
                except Exception:
                    try:
                        self.total_machined.set_label(str(int(total_machined)))
                    except Exception:
                        pass
        except Exception:
            pass

        # Initialize last values
        self.last_hal_total_machined = total_machined
        self.last_hal_touchoff = touchoff
        
        # Set flag that variables are loaded (to prevent startup zero overwrite)
        self.variables_loaded = True

        return False

    # ---------------------------
    # helper: persist single variable to variables.txt
    # ---------------------------
    def _write_variable_to_file(self, key, value):
        try:
            lines = []
            if os.path.exists(self.vars_file):
                with open(self.vars_file, "r") as f:
                    lines = f.readlines()
            found = False
            with open(self.vars_file, "w") as f:
                for line in lines:
                    if line.startswith(f"{key}="):
                        f.write(f"{key}={value}\n")
                        found = True
                    else:
                        f.write(line)
                if not found:
                    f.write(f"{key}={value}\n")
            print(f"[myui_handler] Updated {key}={value} in variables.txt")
        except Exception as e:
            print(f"[myui_handler] ERROR writing var {key}: {e}")

    def init_wear_compensation(self):
        """Initialize wear compensation spinbuttons from wear.csv"""
        try:
            print("init_wear_compensation called")
            if not os.path.exists(self.csv_path):
                print(f"Wear CSV file not found: {self.csv_path}")
                return
            
            # Map of tool names to spinbutton widgets
            wear_widgets = {
                "SX": self.builder.get_object("SX_Wear_Compensation"),
                "S1": self.builder.get_object("S1_Wear_Compensation"), 
                "S2": self.builder.get_object("S2_Wear_Compensation"),
                "F1": self.builder.get_object("F1_Wear_Compensation"),
                "F2": self.builder.get_object("F2_Wear_Compensation"),
                "F3": self.builder.get_object("F3_Wear_Compensation")
            }
            
            # Read wear.csv
            with open(self.csv_path, 'r', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        tool_name = row[0].strip().upper()
                        try:
                            wear_value = float(row[1])
                            # Update corresponding spinbutton widget
                            spinbutton = wear_widgets.get(tool_name)
                            if spinbutton:
                                # Simply set the value - no signal blocking needed since handler isn't connected yet
                                spinbutton.set_value(wear_value)
                                print(f"Loaded {tool_name} wear: {wear_value}")
                        except ValueError as e:
                            print(f"Error parsing wear value for {tool_name}: {e}")
                            continue
                            
        except Exception as e:
            print(f"Error initializing wear compensation: {e}")

    def on_wear_compensation_changed(self, widget):
        """Handle wear compensation spinbutton changes - update wear.csv and HAL pins"""
        try:
            # Map of widget names to tool names
            tool_map = {
                "SX_Wear_Compensation": "SX",
                "S1_Wear_Compensation": "S1",
                "S2_Wear_Compensation": "S2", 
                "F1_Wear_Compensation": "F1",
                "F2_Wear_Compensation": "F2",
                "F3_Wear_Compensation": "F3"
            }
            
            # Get tool name from widget
            tool_name = None
            widget_name = None
            for widget_id, name in tool_map.items():
                widget_obj = self.builder.get_object(widget_id)
                if widget_obj and widget_obj == widget:
                    tool_name = name
                    widget_name = widget_id
                    break
            
            if not tool_name:
                return
                
            wear_value = widget.get_value()
            print(f"Wear compensation changed: {tool_name} = {wear_value}")
            
            # Update HAL pins (this should happen automatically, but let's be sure)
            self.halcomp[f"{widget_name}-f"] = wear_value
            self.halcomp[f"{widget_name}-s"] = int(wear_value * 10000)
            
            # Update wear.csv
            self.update_wear_csv(tool_name, wear_value)
            
        except Exception as e:
            print(f"Error handling wear compensation change: {e}")

    def update_wear_csv(self, tool_name, wear_value):
        """Update wear.csv with new wear compensation value"""
        try:
            # Read existing data
            data = {}
            if os.path.exists(self.csv_path):
                with open(self.csv_path, 'r', newline='') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 2:
                            data[row[0].strip().upper()] = row[1]
            
            # Update the specific tool
            data[tool_name.upper()] = f"{wear_value:.5f}"
            
            # Write back to file
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                for tool, value in data.items():
                    writer.writerow([tool, value])
                    
            print(f"Updated wear.csv: {tool_name} = {wear_value}")
            
        except Exception as e:
            print(f"Error updating wear.csv: {e}")
    def debug_wear_values(self):
        """Debug method to check current wear values"""
        wear_widgets = {
            "SX": self.builder.get_object("SX_Wear_Compensation"),
            "S1": self.builder.get_object("S1_Wear_Compensation"), 
            "S2": self.builder.get_object("S2_Wear_Compensation"),
            "F1": self.builder.get_object("F1_Wear_Compensation"),
            "F2": self.builder.get_object("F2_Wear_Compensation"),
            "F3": self.builder.get_object("F3_Wear_Compensation")
        }
        
        for tool, widget in wear_widgets.items():
            if widget:
                value = widget.get_value()
                print(f"{tool} widget value: {value}")
                
        # Check HAL pins
        for tool in wear_widgets.keys():
            try:
                pin_base = f"{tool}_Wear_Compensation"
                float_val = self.halcomp[f"{pin_base}-f"]
                int_val = self.halcomp[f"{pin_base}-s"]
                print(f"{tool} HAL pins: -f={float_val}, -s={int_val}")
            except:
                print(f"{tool} HAL pins: not accessible")

def get_handlers(halcomp, builder, useropts):
    return [HandlerClass(halcomp, builder, useropts)]