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
        self.eslah_button = builder.get_object('ESLAH')
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

        # ESLAH button initialization
        # Initial sync with HAL pin
        try:
            self.eslah_active = bool(self.halcomp["ESLAH"])
            self.update_eslah_appearance()
            print(f"Initial ESLAH state: {self.eslah_active}")
        except Exception as e:
            print(f"Error reading initial ESLAH state: {e}")
        if self.eslah_button:
            # HALIO_Button handles the HAL pin automatically
            # We just need to sync our internal state
            self.eslah_active = False
            self.sync_eslah_state()
        # Workpiece spinbutton initialization
        if self.workpiece_spin:
            # Map workpiece types to values: SX=0, S1=1, S2=2, F1=3, F2=4, F3=5
            self.workpiece_spin.set_value(1)  # Default to S1
            self.workpiece_spin.connect("value-changed", self.on_workpiece_spin_changed)

        # convenience: store component name
        try:
            self.comp_name = self.halcomp.name
        except Exception:
            self.comp_name = "gladevcp"

        # Connect widget signals
        if self.touchoff_display:
            self.touchoff_display.connect("value-changed", self.on_touchoff_changed)

        if self.test_button:
            self.test_button.connect("pressed", self.on_test_button_pressed)

        # Store current values to detect changes
        self.last_hal_total_machined = 0
        self.last_hal_touchoff = 0.0

        # periodic polls
        GLib.timeout_add(150, self._poll_hal_to_widget)
        GLib.timeout_add(100, self._poll_json_variables)

        # load variables once at startup
        GLib.idle_add(self.load_variables)

    def sync_eslah_state(self):
        """Sync our internal state with the HAL pin"""
        try:
            self.eslah_active = bool(self.halcomp["ESLAH"])
            self.update_eslah_appearance()
            print(f"ESLAH state synced: {self.eslah_active}")
        except Exception as e:
            print(f"Error syncing ESLAH state: {e}")

    # ---------------------------
    # ESLAH button handling
    # ---------------------------
    def on_eslah_pressed(self, widget):
        """Handle ESLAH button press - update our internal state"""
        # For HALIO_Button, the HAL pin is handled automatically
        # We just need to update our UI state
        try:
            # Read the current state from the HAL output pin
            self.eslah_active = bool(self.halcomp["ESLAH"])
            self.update_eslah_appearance()
            print(f"ESLAH button pressed - state: {self.eslah_active}")
        except Exception as e:
            print(f"Error reading ESLAH state: {e}")

    def update_eslah_appearance(self):
        """Update ESLAH button appearance based on state"""
        if self.eslah_button:
            if self.eslah_active:
                self.eslah_button.set_label("اعمال خواهد شد - کلیک برای لغو")
                self.eslah_button.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#00FF00"))
            else:
                self.eslah_button.set_label("اعمال نمیشود - کلیک برای فعال سازی")
                self.eslah_button.modify_bg(Gtk.StateType.NORMAL, None)


        # ---------------------------
    # ESLAH ToggleButton handling
    # ---------------------------
    def on_eslah_toggled(self, widget):
        """Handle ESLAH toggle button state change"""
        self.eslah_active = widget.get_active()
        
        if self.eslah_active:
            widget.set_label("اعمال خواهد شد - کلیک برای لغو")
            widget.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#00FF00"))
        else:
            widget.set_label("اعمال نمیشود - کلیک برای فعال سازی")
            widget.modify_bg(Gtk.StateType.NORMAL, None)
        
        print(f"ESLAH state: {self.eslah_active}")

    def reset_eslah_button(self):
        """Reset ESLAH button programmatically"""
        try:
            # For HALIO_Button with I/O pin, we can set it directly
            self.halcomp["ESLAH"] = False
            self.eslah_active = False
            self.update_eslah_appearance()
            print("ESLAH reset successfully")
        except Exception as e:
            print(f"Error resetting ESLAH: {e}")


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
            self.halcomp["touchoff_display-s"] = int(round(val))
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
        # touchoff: prefer feedback pin if present
        try:
            val = None
            try:
                val = float(self.halcomp["touchoff_display-f"])
            except Exception:
                try:
                    val = float(self.halcomp["touchoff_display"])
                except Exception:
                    val = None

            if val is not None and val != self.last_hal_touchoff:
                self.last_hal_touchoff = val
                if self.touchoff_display:
                    try:
                        self.touchoff_display.handler_block_by_func(self.on_touchoff_changed)
                    except Exception:
                        pass
                    try:
                        self.touchoff_display.set_value(float(val))
                    except Exception:
                        pass
                    try:
                        self.touchoff_display.handler_unblock_by_func(self.on_touchoff_changed)
                    except Exception:
                        pass
        except Exception:
            pass

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

        # Sync ESLAH state with HAL pin
        try:
            current_eslah_state = bool(self.halcomp["ESLAH"])
            if current_eslah_state != self.eslah_active:
                self.eslah_active = current_eslah_state
                self.update_eslah_appearance()
                print(f"ESLAH state changed to: {self.eslah_active}")
        except Exception as e:
            print(f"Error reading ESLAH pin: {e}")
        
        return True
        

    # ---------------------------
    # JSON pipe: M-codes write here, handler picks them up and updates widgets
    # ---------------------------
    def _poll_json_variables(self):
        if not os.path.exists(self.pipe_file):
            return True
        try:
            with open(self.pipe_file, "r") as f:
                data = json.load(f)
        except Exception:
            try:
                os.remove(self.pipe_file)
            except Exception:
                pass
            return True

        # touchoff via JSON
        if "touchoff" in data and self.touchoff_display:
            try:
                val = float(data["touchoff"])
                try:
                    self.touchoff_display.handler_block_by_func(self.on_touchoff_changed)
                except Exception:
                    pass
                self.touchoff_display.set_value(float(val))
                try:
                    self.touchoff_display.handler_unblock_by_func(self.on_touchoff_changed)
                except Exception:
                    pass
                try:
                    self.halcomp["touchoff_display-f"] = float(val)
                except Exception:
                    pass
                try:
                    self.halcomp["touchoff_display-s"] = int(round(val))
                except Exception:
                    pass
                self._write_variable_to_file("touchoff", val)
            except Exception:
                pass

        # total_machined via JSON - update widget only (M113 script handles HAL pin)
        if "total_machined" in data and self.total_machined:
            try:
                val = int(data["total_machined"])
                # Update widget only - M113 script will handle HAL pin via halcmd
                try:
                    self.total_machined.set_value(int(val))
                except Exception:
                    try:
                        self.total_machined.set_label(str(int(val)))
                    except Exception:
                        pass
                # Note: We don't update HAL pin here - M113 script does that
            except Exception:
                pass

        # ESLAH check via JSON
        if "eslah_check" in data:
            try:
                if data["eslah_check"]:
                    self.check_and_run_eslah_action()
            except Exception:
                pass

        # remove pipe only when safely processed
        try:
            os.remove(self.pipe_file)
        except Exception:
            pass

        return True

    # ---------------------------
    # ESLAH action check (if needed)
    # ---------------------------
    def check_and_run_eslah_action(self):
        """Check if ESLAH is active and run action"""
        if self.eslah_active:
            print("ESLAH is active - running action script...")
            
            # Get workpiece value from spinbutton
            workpiece_value = 1
            if self.workpiece_spin:
                workpiece_value = int(self.workpiece_spin.get_value())
            
            # Run your Python script
            script_path = os.path.join(self.base_dir, "eslah_action.py")
            if os.path.exists(script_path):
                try:
                    subprocess.run(["python3", script_path, "1", str(workpiece_value)], check=True)
                    print("ESLAH action completed successfully")
                    self.reset_eslah_button()
                except subprocess.CalledProcessError as e:
                    print(f"ESLAH script failed: {e}")
            else:
                print(f"ESLAH script not found: {script_path}")

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


def get_handlers(halcomp, builder, useropts):
    return [HandlerClass(halcomp, builder, useropts)]