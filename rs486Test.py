import configparser
import tkinter as tk
from tkinter import ttk, messagebox
from pymodbus.client.sync import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import threading
import logging

logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.DEBUG)  # or logging.INFO for less verbose
INI_FILE = "mb2hal.ini"

def load_transactions(ini_file):
    config = configparser.ConfigParser()
    config.read(ini_file)
    # Find the first section with serial config
    for section in config.sections():
        if section.startswith("TRANSACTION_") and 'serial_port' in config[section]:
            serial_cfg = config[section]
            break
    else:
        serial_cfg = config['TRANSACTION_00']
    port = serial_cfg.get('serial_port', '/dev/ttyUSB0')
    baud = int(serial_cfg.get('serial_baud', 9600))
    bits = int(serial_cfg.get('serial_bits', 8))
    parity = serial_cfg.get('serial_parity', 'none').upper()[0]
    stop = int(serial_cfg.get('serial_stop', 1))
    parity_map = {'N': 'N', 'E': 'E', 'O': 'O'}
    parity = parity_map.get(parity, 'N')
    transactions = []
    for section in config.sections():
        if section.startswith("TRANSACTION_"):
            trans = dict(config[section])
            trans["section"] = section
            transactions.append(trans)
    return port, baud, bits, parity, stop, transactions

class RS485IOBoardFrame(ttk.LabelFrame):
    def __init__(self, master, client):
        super().__init__(master, text="Remote IO Board (Slave 2)")
        self.client = client
        self.inputs = [tk.StringVar(value="OFF") for _ in range(8)]
        self.outputs = [tk.IntVar(value=0) for _ in range(8)]

        # Outputs
        out_label = ttk.Label(self, text="Outputs (Relays):")
        out_label.grid(row=0, column=0, columnspan=2)
        for i in range(8):
            cb = ttk.Checkbutton(
                self, text=f"Relay {i}", variable=self.outputs[i],
                command=self.write_outputs)
            cb.grid(row=i+1, column=0, sticky="w")

        # Inputs
        in_label = ttk.Label(self, text="Inputs (Digital):")
        in_label.grid(row=0, column=2, columnspan=2)
        self.input_labels = []
        for i in range(8):
            lbl = ttk.Label(self, textvariable=self.inputs[i], width=6, relief=tk.SUNKEN)
            lbl.grid(row=i+1, column=2, sticky="w")
            desc = ttk.Label(self, text=f"Input {i}")
            desc.grid(row=i+1, column=3, sticky="w")
            self.input_labels.append(lbl)

        self.poll_inputs()

    def write_outputs(self):
        # Pack 8 checkboxes into a byte
        value = sum([self.outputs[i].get() << i for i in range(8)])
        def task():
            try:
                self.client.connect()
                self.client.write_register(18, value, unit=2)
                self.client.close()
            except Exception as e:
                messagebox.showerror("Write Error", str(e))
        threading.Thread(target=task).start()

    def poll_inputs(self):
        def task():
            try:
                self.client.connect()
                result = self.client.read_holding_registers(15, 1, unit=2)
                if hasattr(result, 'registers'):
                    value = result.registers[0]
                    # Unpack bits into indicators
                    for i in range(8):
                        state = "ON" if (value & (1 << i)) else "OFF"
                        self.inputs[i].set(state)
                self.client.close()
            except Exception as e:
                for i in range(8):
                    self.inputs[i].set("ERR")
            # Schedule next poll
            self.after(1000, self.poll_inputs)
        threading.Thread(target=task).start()

class RS485TestApp:
    def __init__(self, master, port, baud, bits, parity, stop, transactions):
        self.master = master
        master.title("RS485 & Modbus Test")
        self.transactions = transactions
        self.client = ModbusSerialClient(
            method='rtu', port=port, baudrate=baud, bytesize=bits,
            parity=parity, stopbits=stop, timeout=1
        )
        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self.master)
        frame.pack(padx=10, pady=10)
        self.entries = []
        row = 0
        for t in self.transactions:
            name = t.get('hal_tx_name', t['section'])
            tx_code = t.get('mb_tx_code', '')
            slave = int(t.get('mb_slave_id', 1))
            reg = int(t.get('first_element', 0))
            n = int(t.get('nelements', 1))
            # Only add basic UI for non-remote-IO transactions
            if not (slave == 2 and reg in (15, 18)):
                label = ttk.Label(frame, text=f"{name} (Slave {slave}, Reg {reg})")
                label.grid(row=row, column=0, sticky="w")
                status_label = ttk.Label(frame, text="Unknown", width=18)
                status_label.grid(row=row, column=1)
                if 'write_single_register' in tx_code:
                    btn = ttk.Button(frame, text="ON", command=lambda t=t, sl=slave, reg=reg, st=status_label: self.set_register(t, sl, reg, 1, st))
                    btn.grid(row=row, column=2)
                    btn2 = ttk.Button(frame, text="OFF", command=lambda t=t, sl=slave, reg=reg, st=status_label: self.set_register(t, sl, reg, 0, st))
                    btn2.grid(row=row, column=3)
                elif 'read_holding_registers' in tx_code:
                    btn = ttk.Button(frame, text="Read", command=lambda t=t, sl=slave, reg=reg, n=n, st=status_label: self.read_register(t, sl, reg, n, st))
                    btn.grid(row=row, column=2)
                self.entries.append((label, status_label))
                row += 1

        # Add a test for dongle health
        test_btn = ttk.Button(frame, text="Check Dongle", command=self.check_device)
        test_btn.grid(row=row, column=0, pady=10)
        self.device_status = ttk.Label(frame, text="Not checked", width=30)
        self.device_status.grid(row=row, column=1, columnspan=2)

        # Add the Remote IO frame
        io_frame = RS485IOBoardFrame(self.master, self.client)
        io_frame.pack(padx=10, pady=10, fill="x")

    def check_device(self):
        def task():
            try:
                connected = self.client.connect()
                if connected:
                    self.device_status.config(text="Dongle: OK", foreground="green")
                    self.client.close()
                else:
                    self.device_status.config(text="Dongle: Not found", foreground="red")
            except Exception as e:
                self.device_status.config(text=f"Error: {e}", foreground="red")
        threading.Thread(target=task).start()

    def set_register(self, t, slave, reg, value, status_label):
        def task():
            try:
                self.client.connect()
                result = self.client.write_register(reg, value, unit=slave)
                if hasattr(result, 'isError') and not result.isError():
                    status_label.config(text=f"Written: {value}", foreground="green")
                else:
                    status_label.config(text="Write Failed", foreground="red")
                self.client.close()
            except Exception as e:
                status_label.config(text=f"Error: {e}", foreground="red")
        threading.Thread(target=task).start()

    def read_register(self, t, slave, reg, n, status_label):
        def task():
            try:
                self.client.connect()
                result = self.client.read_holding_registers(reg, n, unit=slave)
                if hasattr(result, 'registers'):
                    status_label.config(text=f"Value: {result.registers[0]}", foreground="green")
                else:
                    status_label.config(text="Read Failed", foreground="red")
                self.client.close()
            except Exception as e:
                status_label.config(text=f"Error: {e}", foreground="red")
        threading.Thread(target=task).start()

def main():
    port, baud, bits, parity, stop, transactions = load_transactions(INI_FILE)
    root = tk.Tk()
    app = RS485TestApp(root, port, baud, bits, parity, stop, transactions)
    root.mainloop()

if __name__ == "__main__":
    main()