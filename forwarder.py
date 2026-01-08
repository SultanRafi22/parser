import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import socket
import serial
import serial.tools.list_ports
import threading
import time
import json
import os
from datetime import datetime

class DataForwarder:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Forwarder - Lab Equipment to Parser")
        
        # RESPONSIVE WINDOW SIZE
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.7)
        window_height = int(screen_height * 0.7)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(True, True)
        self.root.minsize(900, 650)
        self.root.configure(bg='#f0f0f0')
        
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # ===== FORWARDING CONFIGURATION =====
        self.forwarding_config = {
            'target_host': '127.0.0.1',
            'target_port': 8080,
            'timeout': 5,
            'auto_reconnect': True,
            'buffer_size': 65536
        }
        self.config_file = "forwarder_config.json"
        self.load_config()
        
        # ===== SOCKET SERVER CONFIGURATION =====
        self.socket_config = {
            'host': '0.0.0.0',
            'port': 9000,  # Port untuk terima dari alat
            'buffer_size': 65536
        }
        self.socket_server = None
        self.socket_running = False
        
        # ===== SERIAL PORT CONFIGURATION =====
        self.serial_connections = {}  # {port_name: serial_object}
        self.serial_threads = {}      # {port_name: thread_object}
        self.serial_running = {}      # {port_name: bool}
        self.serial_configs = {}      # {port_name: config_dict}
        
        # ===== STATISTICS =====
        self.stats = {
            'total_forwarded': 0,
            'total_failed': 0,
            'socket_forwarded': 0,
            'serial_forwarded': 0,
            'bytes_forwarded': 0,
            'last_forward_time': None,
            'session_start': datetime.now()
        }
        
        # Create UI
        self.create_widgets()
        
        # Window close event
        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)
        
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.forwarding_config.update(loaded.get('forwarding', {}))
                    self.socket_config.update(loaded.get('socket', {}))
                    self.serial_configs = loaded.get('serial_configs', {})
                print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                print(f"Failed to load config: {str(e)}")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'forwarding': self.forwarding_config,
                'socket': self.socket_config,
                'serial_configs': self.serial_configs,
                'last_saved': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to save config: {str(e)}")
            return False
    
    def create_widgets(self):
        """Create main UI"""
        # Title
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        title_frame.grid(row=0, column=0, sticky='ew')
        title_frame.grid_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🔄 Data Forwarder - Lab Equipment Relay System",
            font=("Arial", 16, "bold"),
            bg='#2c3e50',
            fg='white'
        )
        title_label.pack(pady=15)
        
        # Main Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, padx=10, pady=10, sticky='nsew')
        
        # Tab 1: Forwarding Config
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="⚙️ Configuration")
        self.create_config_tab()
        
        # Tab 2: Socket Receiver
        self.socket_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.socket_frame, text="🌐 Socket Receiver")
        self.create_socket_tab()
        
        # Tab 3: Serial Receiver
        self.serial_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.serial_frame, text="🔌 Serial Receiver")
        self.create_serial_tab()
        
        # Tab 4: Activity Log
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="📋 Activity Log")
        self.create_log_tab()
        
        # Tab 5: Statistics
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="📊 Statistics")
        self.create_stats_tab()
    
    # ========================================
    # TAB 1: CONFIGURATION
    # ========================================
    def create_config_tab(self):
        """Create forwarding configuration tab"""
        self.config_frame.grid_rowconfigure(0, weight=1)
        self.config_frame.grid_columnconfigure(0, weight=1)
        
        # Main container
        container = ttk.Frame(self.config_frame)
        container.grid(row=0, column=0, sticky='nsew', padx=20, pady=20)
        container.grid_columnconfigure(0, weight=1)
        
        # Target Parser Config
        parser_frame = ttk.LabelFrame(container, text="Target Parser Configuration", padding=20)
        parser_frame.grid(row=0, column=0, sticky='ew', pady=10)
        parser_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(parser_frame, text="Parser IP Address:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky='w', pady=10, padx=5
        )
        self.target_host_entry = ttk.Entry(parser_frame, font=("Arial", 11))
        self.target_host_entry.insert(0, self.forwarding_config['target_host'])
        self.target_host_entry.grid(row=0, column=1, pady=10, padx=5, sticky='ew')
        
        ttk.Label(parser_frame, text="Parser Port:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, sticky='w', pady=10, padx=5
        )
        self.target_port_entry = ttk.Entry(parser_frame, font=("Arial", 11))
        self.target_port_entry.insert(0, str(self.forwarding_config['target_port']))
        self.target_port_entry.grid(row=1, column=1, pady=10, padx=5, sticky='ew')
        
        ttk.Label(parser_frame, text="Connection Timeout (s):", font=("Arial", 10, "bold")).grid(
            row=2, column=0, sticky='w', pady=10, padx=5
        )
        self.timeout_entry = ttk.Entry(parser_frame, font=("Arial", 11))
        self.timeout_entry.insert(0, str(self.forwarding_config['timeout']))
        self.timeout_entry.grid(row=2, column=1, pady=10, padx=5, sticky='ew')
        
        # Auto-reconnect
        self.auto_reconnect_var = tk.BooleanVar(value=self.forwarding_config['auto_reconnect'])
        ttk.Checkbutton(
            parser_frame,
            text="Auto-reconnect on failure",
            variable=self.auto_reconnect_var
        ).grid(row=3, column=0, columnspan=2, pady=10, sticky='w', padx=5)
        
        # Buttons
        btn_frame = ttk.Frame(parser_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=15, sticky='ew')
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Button(
            btn_frame,
            text="💾 Save Configuration",
            command=self.save_forwarding_config,
            style="Accent.TButton"
        ).grid(row=0, column=0, padx=5, sticky='ew')
        
        ttk.Button(
            btn_frame,
            text="🧪 Test Connection",
            command=self.test_parser_connection
        ).grid(row=0, column=1, padx=5, sticky='ew')
        
        # Status
        self.config_status_label = tk.Label(
            parser_frame,
            text="Status: Not tested",
            font=("Arial", 10, "bold"),
            fg='#f39c12'
        )
        self.config_status_label.grid(row=5, column=0, columnspan=2, pady=10, sticky='ew')
        
        # Info Box
        info_frame = ttk.LabelFrame(container, text="ℹ️ Information", padding=15)
        info_frame.grid(row=1, column=0, sticky='ew', pady=10)
        
        info_text = """This application forwards raw data from lab equipment to the parser application.

📌 How it works:
   1. Receive raw data from lab equipment (Socket/Serial)
   2. Forward data directly to parser application via IP
   3. No local parsing or database storage
   
📌 Requirements:
   • Target parser application must be running
   • Target parser must have Socket Server active
   • Network connectivity between forwarder and parser
        """
        
        info_label = tk.Label(
            info_frame,
            text=info_text,
            font=("Consolas", 9),
            justify=tk.LEFT,
            bg='#ecf0f1',
            fg='#2c3e50',
            padx=10,
            pady=10
        )
        info_label.pack(fill=tk.BOTH, expand=True)
    
    def save_forwarding_config(self):
        """Save forwarding configuration"""
        try:
            self.forwarding_config['target_host'] = self.target_host_entry.get().strip()
            self.forwarding_config['target_port'] = int(self.target_port_entry.get().strip())
            self.forwarding_config['timeout'] = int(self.timeout_entry.get().strip())
            self.forwarding_config['auto_reconnect'] = self.auto_reconnect_var.get()
            
            if self.save_config():
                self.log_activity("💾 Configuration saved successfully")
                messagebox.showinfo("Success", "Configuration saved successfully!")
            else:
                messagebox.showerror("Error", "Failed to save configuration")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid port or timeout value: {str(e)}")
    
    def test_parser_connection(self):
        """Test connection to target parser"""
        target_host = self.target_host_entry.get().strip()
        target_port = int(self.target_port_entry.get().strip())
        
        self.log_activity(f"🧪 Testing connection to {target_host}:{target_port}...")
        self.config_status_label.configure(text="Status: Testing...", fg='#f39c12')
        
        def test_conn():
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(5)
                test_socket.connect((target_host, target_port))
                
                # Send test message
                test_message = "FORWARDER_TEST_CONNECTION\n"
                test_socket.send(test_message.encode('utf-8'))
                
                test_socket.close()
                
                self.root.after(0, lambda: self.config_status_label.configure(
                    text=f"Status: ✅ Connected to {target_host}:{target_port}",
                    fg='#27ae60'
                ))
                self.root.after(0, lambda: self.log_activity(
                    f"✅ Connection successful to {target_host}:{target_port}"
                ))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Success",
                    f"Connection test successful!\n\nParser is reachable at:\n{target_host}:{target_port}"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.config_status_label.configure(
                    text=f"Status: ❌ Connection failed",
                    fg='#e74c3c'
                ))
                self.root.after(0, lambda: self.log_activity(f"❌ Connection failed: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Connection Failed",
                    f"Cannot connect to parser:\n\n{str(e)}\n\nMake sure parser is running!"
                ))
        
        threading.Thread(target=test_conn, daemon=True).start()
    
    # ========================================
    # TAB 2: SOCKET RECEIVER
    # ========================================
    def create_socket_tab(self):
        """Create socket receiver tab"""
        self.socket_frame.grid_rowconfigure(0, weight=0)
        self.socket_frame.grid_rowconfigure(1, weight=1)
        self.socket_frame.grid_columnconfigure(0, weight=1)
        
        # Config Frame
        config_frame = ttk.LabelFrame(self.socket_frame, text="Socket Server Configuration", padding=15)
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky='ew')
        config_frame.grid_columnconfigure(1, weight=1)
        
        # Settings
        settings_frame = ttk.Frame(config_frame)
        settings_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)
        
        ttk.Label(settings_frame, text="Listen IP:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.socket_host_entry = ttk.Entry(settings_frame, width=20)
        self.socket_host_entry.insert(0, self.socket_config['host'])
        self.socket_host_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(settings_frame, text="Listen Port:").grid(row=0, column=2, sticky='w', padx=5, pady=5)
        self.socket_port_entry = ttk.Entry(settings_frame, width=10)
        self.socket_port_entry.insert(0, str(self.socket_config['port']))
        self.socket_port_entry.grid(row=0, column=3, padx=5, pady=5, sticky='ew')
        
        settings_frame.grid_columnconfigure(1, weight=1)
        settings_frame.grid_columnconfigure(3, weight=1)
        
        # Control Buttons
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=10)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        self.start_socket_btn = ttk.Button(
            btn_frame,
            text="🟢 Start Socket Server",
            command=self.start_socket_server,
            style="Accent.TButton"
        )
        self.start_socket_btn.grid(row=0, column=0, padx=5, sticky='ew')
        
        self.stop_socket_btn = ttk.Button(
            btn_frame,
            text="🔴 Stop Socket Server",
            command=self.stop_socket_server,
            state=tk.DISABLED
        )
        self.stop_socket_btn.grid(row=0, column=1, padx=5, sticky='ew')
        
        # Status
        self.socket_status_label = tk.Label(
            config_frame,
            text="Server Status: Stopped",
            font=("Arial", 10, "bold"),
            fg='#e74c3c'
        )
        self.socket_status_label.grid(row=2, column=0, columnspan=2, pady=10, sticky='ew')
        
        # Log Frame
        log_frame = ttk.LabelFrame(self.socket_frame, text="Socket Activity Log", padding=10)
        log_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        self.socket_log = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.socket_log.grid(row=0, column=0, sticky='nsew')
    
    def start_socket_server(self):
        """Start socket server"""
        if self.socket_running:
            messagebox.showwarning("Warning", "Socket server is already running!")
            return
        
        def run_server():
            try:
                self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                
                host = self.socket_host_entry.get()
                port = int(self.socket_port_entry.get())
                
                self.socket_server.bind((host, port))
                self.socket_server.listen(5)
                
                self.socket_running = True
                
                self.root.after(0, lambda: self.socket_status_label.configure(
                    text=f"Server Status: 🟢 Running on {host}:{port}",
                    fg='#27ae60'
                ))
                self.root.after(0, lambda: self.start_socket_btn.configure(state=tk.DISABLED))
                self.root.after(0, lambda: self.stop_socket_btn.configure(state=tk.NORMAL))
                self.root.after(0, lambda: self.log_socket(f"Socket server started on {host}:{port}"))
                
                while self.socket_running:
                    try:
                        client_socket, address = self.socket_server.accept()
                        self.root.after(0, lambda addr=address: self.log_socket(
                            f"Connection from {addr[0]}:{addr[1]}"
                        ))
                        
                        client_thread = threading.Thread(
                            target=self.handle_socket_client,
                            args=(client_socket, address),
                            daemon=True
                        )
                        client_thread.start()
                    except socket.error:
                        if self.socket_running:
                            break
            except Exception as e:
                self.socket_running = False
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to start server: {str(e)}"))
                self.root.after(0, lambda: self.socket_status_label.configure(
                    text="Server Status: Error",
                    fg='#e74c3c'
                ))
        
        threading.Thread(target=run_server, daemon=True).start()
    
    def stop_socket_server(self):
        """Stop socket server"""
        self.socket_running = False
        
        if self.socket_server:
            try:
                self.socket_server.close()
            except:
                pass
        
        self.socket_status_label.configure(text="Server Status: Stopped", fg='#e74c3c')
        self.start_socket_btn.configure(state=tk.NORMAL)
        self.stop_socket_btn.configure(state=tk.DISABLED)
        self.log_socket("Socket server stopped")
    
    def handle_socket_client(self, client_socket, address):
        """Handle socket client connection"""
        client_ip = address[0]
        
        try:
            with client_socket:
                data_buffer = ""
                last_data_time = time.time()
                
                while self.socket_running:
                    data = client_socket.recv(self.socket_config['buffer_size'])
                    if not data:
                        break
                    
                    received_data = data.decode('utf-8', errors='ignore')
                    data_buffer += received_data
                    last_data_time = time.time()
                    
                    # Check if complete message (simple end detection)
                    time_since_last = time.time() - last_data_time
                    
                    if time_since_last > 0.5 and len(data_buffer) > 50:
                        complete_data = data_buffer.strip()
                        data_buffer = ""
                        
                        self.root.after(0, lambda size=len(complete_data): self.log_socket(
                            f"📦 Received {size} bytes from {client_ip}"
                        ))
                        
                        # Forward to parser
                        self.forward_data(complete_data, 'socket', client_ip)
                        
                        # Send ACK
                        try:
                            client_socket.send("<ACK>\n".encode('utf-8'))
                        except:
                            pass
                        
                        last_data_time = time.time()
                    
                    time.sleep(0.1)
        except Exception as e:
            self.root.after(0, lambda: self.log_socket(f"Error handling {client_ip}: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.log_socket(f"Connection closed: {client_ip}"))
    
    def log_socket(self, message):
        """Log socket activity"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.socket_log.configure(state=tk.NORMAL)
        self.socket_log.insert(tk.END, log_entry)
        self.socket_log.see(tk.END)
        self.socket_log.configure(state=tk.DISABLED)
    
    # ========================================
    # TAB 3: SERIAL RECEIVER
    # ========================================
    def create_serial_tab(self):
        """Create serial receiver tab"""
        self.serial_frame.grid_rowconfigure(0, weight=0)
        self.serial_frame.grid_rowconfigure(1, weight=1)
        self.serial_frame.grid_columnconfigure(0, weight=1)
        
        # Control Panel
        control_frame = ttk.LabelFrame(self.serial_frame, text="Serial Port Control", padding=10)
        control_frame.grid(row=0, column=0, padx=10, pady=10, sticky='ew')
        
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            btn_frame,
            text="🔄 Refresh Ports",
            command=self.refresh_serial_ports,
            style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="➕ Add Port",
            command=self.add_serial_port,
            style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="✅ Connect All",
            command=self.connect_all_serial
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="❌ Disconnect All",
            command=self.disconnect_all_serial
        ).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.serial_status_label = tk.Label(
            control_frame,
            text="Connected Ports: 0 | Total: 0",
            font=("Arial", 10, "bold"),
            fg='#7f8c8d'
        )
        self.serial_status_label.pack(pady=10)
        
        # Ports List Frame
        list_frame = ttk.LabelFrame(self.serial_frame, text="Configured Serial Ports", padding=10)
        list_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Treeview
        columns = ('Port', 'Baudrate', 'Status')
        self.serial_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        
        self.serial_tree.heading('Port', text='Port Name')
        self.serial_tree.heading('Baudrate', text='Baudrate')
        self.serial_tree.heading('Status', text='Status')
        
        self.serial_tree.column('Port', width=150, minwidth=100)
        self.serial_tree.column('Baudrate', width=100, minwidth=80)
        self.serial_tree.column('Status', width=150, minwidth=100)
        
        v_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.serial_tree.yview)
        self.serial_tree.configure(yscrollcommand=v_scrollbar.set)
        
        self.serial_tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        
        # Action buttons
        action_frame = ttk.Frame(list_frame)
        action_frame.grid(row=1, column=0, columnspan=2, pady=10, sticky='ew')
        
        ttk.Button(
            action_frame,
            text="🔌 Connect Selected",
            command=self.connect_selected_serial
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="🔌 Disconnect Selected",
            command=self.disconnect_selected_serial
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="🗑️ Remove Selected",
            command=self.remove_selected_serial
        ).pack(side=tk.RIGHT, padx=5)
    
    def refresh_serial_ports(self):
        """Refresh available serial ports"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.log_activity(f"Found {len(ports)} available ports: {', '.join(ports) if ports else 'None'}")
        messagebox.showinfo("Serial Ports", f"Found {len(ports)} ports:\n\n" + "\n".join(ports) if ports else "No ports found")
    
    def add_serial_port(self):
        """Add new serial port"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Serial Port")
        dialog.geometry("450x350")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        x = (dialog.winfo_screenwidth() // 2) - 225
        y = (dialog.winfo_screenheight() // 2) - 175
        dialog.geometry(f"450x350+{x}+{y}")
        
        config_frame = ttk.LabelFrame(dialog, text="Port Configuration", padding=15)
        config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        config_frame.grid_columnconfigure(1, weight=1)
        
        # Port selection
        ttk.Label(config_frame, text="Select Port:").grid(row=0, column=0, sticky='w', pady=5, padx=5)
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        port_var = tk.StringVar()
        port_combo = ttk.Combobox(config_frame, textvariable=port_var, values=available_ports, width=25)
        port_combo.grid(row=0, column=1, pady=5, padx=5, sticky='ew')
        if available_ports:
            port_combo.current(0)
        
        # Baudrate
        ttk.Label(config_frame, text="Baudrate:").grid(row=1, column=0, sticky='w', pady=5, padx=5)
        baudrate_var = tk.StringVar(value='9600')
        ttk.Combobox(config_frame, textvariable=baudrate_var, 
                    values=['9600', '19200', '38400', '57600', '115200'], 
                    width=25, state='readonly').grid(row=1, column=1, pady=5, padx=5, sticky='ew')
        
        # Data bits
        ttk.Label(config_frame, text="Data Bits:").grid(row=2, column=0, sticky='w', pady=5, padx=5)
        datab_var = tk.StringVar(value='8')
        ttk.Combobox(config_frame, textvariable=datab_var,
        values=['5', '6', '7', '8'], width=25, state='readonly').grid(row=2, column=1, pady=5, padx=5, sticky='ew')
        
        ttk.Label(config_frame, text="Parity:").grid(row=3, column=0, sticky='w', pady=5, padx=5)
        parity_var = tk.StringVar(value='N')
        ttk.Combobox(config_frame, textvariable=parity_var, values=['N', 'E', 'O'], width=25, state='readonly').grid(row=3, column=1, pady=5, padx=5, sticky='ew')
            
        # Stop bits
        ttk.Label(config_frame, text="Stop Bits:").grid(row=4, column=0, sticky='w', pady=5, padx=5)
        stopb_var = tk.StringVar(value='1')
        ttk.Combobox(config_frame, textvariable=stopb_var, values=['1', '1.5', '2'], width=25, state='readonly').grid(row=4, column=1, pady=5, padx=5, sticky='ew')
            
        # Timeout
        ttk.Label(config_frame, text="Timeout (s):").grid(row=5, column=0, sticky='w', pady=5, padx=5)
        timeout_var = tk.StringVar(value='3')
        ttk.Entry(config_frame, textvariable=timeout_var, width=27).grid(row=5, column=1, pady=5, padx=5, sticky='ew')

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
            
        def save_and_close():
            port_name = port_var.get()
            if not port_name:
                messagebox.showwarning("Warning", "Please select a port")
                return
                
            if port_name in self.serial_configs:
                messagebox.showwarning("Warning", f"Port {port_name} already configured!")
                return
                
            try:
                self.serial_configs[port_name] = {
                    'port': port_name,
                    'baudrate': int(baudrate_var.get()),
                    'bytesize': int(datab_var.get()),
                    'parity': parity_var.get(),
                    'stopbits': float(stopb_var.get()),
                    'timeout': float(timeout_var.get())
                }
                    
                self.serial_running[port_name] = False
                self.update_serial_display()
                self.log_activity(f"Port {port_name} configured")
                self.save_config()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid configuration: {str(e)}")
            
        ttk.Button(btn_frame, text="💾 Save", command=save_and_close, 
                style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def update_serial_display(self):
        """Update serial ports display"""
        for item in self.serial_tree.get_children():
            self.serial_tree.delete(item)
        
        for port_name, config in self.serial_configs.items():
            status = "🟢 Connected" if self.serial_running.get(port_name, False) else "⚪ Disconnected"
            self.serial_tree.insert('', tk.END, values=(
                port_name,
                config['baudrate'],
                status
            ))
        
        total = len(self.serial_configs)
        connected = sum(1 for r in self.serial_running.values() if r)
        self.serial_status_label.configure(
            text=f"Connected Ports: {connected} | Total: {total}",
            fg='#27ae60' if connected > 0 else '#7f8c8d'
        )

    def connect_selected_serial(self):
        """Connect selected serial port"""
        selected = self.serial_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a port")
            return
        
        port_name = self.serial_tree.item(selected[0])['values'][0]
        self.connect_serial_port(port_name)

    def disconnect_selected_serial(self):
        """Disconnect selected serial port"""
        selected = self.serial_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a port")
            return
        
        port_name = self.serial_tree.item(selected[0])['values'][0]
        self.disconnect_serial_port(port_name)

    def remove_selected_serial(self):
        """Remove selected serial port"""
        selected = self.serial_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a port")
            return
        
        port_name = self.serial_tree.item(selected[0])['values'][0]
        
        if self.serial_running.get(port_name, False):
            messagebox.showwarning("Warning", f"Please disconnect {port_name} first")
            return
        
        if messagebox.askyesno("Confirm", f"Remove {port_name} from configuration?"):
            if port_name in self.serial_configs:
                del self.serial_configs[port_name]
            if port_name in self.serial_running:
                del self.serial_running[port_name]
            
            self.update_serial_display()
            self.log_activity(f"Port {port_name} removed")
            self.save_config()

    def connect_all_serial(self):
        """Connect all serial ports"""
        for port_name in self.serial_configs.keys():
            if not self.serial_running.get(port_name, False):
                self.connect_serial_port(port_name)
                time.sleep(0.2)

    def disconnect_all_serial(self):
        """Disconnect all serial ports"""
        for port_name in list(self.serial_running.keys()):
            if self.serial_running.get(port_name, False):
                self.disconnect_serial_port(port_name)

    def connect_serial_port(self, port_name):
        """Connect to serial port"""
        if port_name not in self.serial_configs:
            return
        
        config = self.serial_configs[port_name]
        
        def run_serial():
            try:
                ser = serial.Serial(
                    port=config['port'],
                    baudrate=config['baudrate'],
                    bytesize=config['bytesize'],
                    parity=config['parity'],
                    stopbits=config['stopbits'],
                    timeout=config['timeout']
                )
                
                self.serial_connections[port_name] = ser
                self.serial_running[port_name] = True
                
                self.root.after(0, lambda: self.log_activity(f"🔌 {port_name} connected at {config['baudrate']} baud"))
                self.root.after(0, self.update_serial_display)
                
                # Send initial ACK
                try:
                    time.sleep(0.5)
                    ser.write("<ACK>\n".encode('utf-8'))
                    ser.flush()
                except:
                    pass
                
                data_buffer = ""
                last_data_time = time.time()
                
                while self.serial_running.get(port_name, False):
                    try:
                        if ser.in_waiting > 0:
                            chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                            data_buffer += chunk
                            last_data_time = time.time()
                            time.sleep(0.05)
                            
                            # Simple completion check
                            time_since_last = time.time() - last_data_time
                            
                            if time_since_last > 0.5 and len(data_buffer) > 50:
                                received_data = data_buffer.strip()
                                data_buffer = ""
                                
                                self.root.after(0, lambda size=len(received_data): self.log_activity(
                                    f"📦 [{port_name}] Received {size} bytes"
                                ))
                                
                                # Forward to parser
                                self.forward_data(received_data, 'serial', port_name)
                                
                                # Send ACK
                                try:
                                    ser.write("<ACK>\n".encode('utf-8'))
                                    ser.flush()
                                except:
                                    pass
                                
                                last_data_time = time.time()
                        else:
                            time.sleep(0.1)
                    except serial.SerialException as e:
                        self.root.after(0, lambda: self.log_activity(f"❌ [{port_name}] Error: {str(e)}"))
                        break
            except Exception as e:
                self.serial_running[port_name] = False
                self.root.after(0, lambda: self.log_activity(f"❌ [{port_name}] Cannot open: {str(e)}"))
                self.root.after(0, self.update_serial_display)
        
        thread = threading.Thread(target=run_serial, daemon=True)
        self.serial_threads[port_name] = thread
        thread.start()

    def disconnect_serial_port(self, port_name):
        """Disconnect serial port"""
        if not self.serial_running.get(port_name, False):
            return
        
        self.serial_running[port_name] = False
        
        if port_name in self.serial_connections:
            try:
                self.serial_connections[port_name].close()
                del self.serial_connections[port_name]
            except:
                pass
        
        self.log_activity(f"🔌 [{port_name}] Disconnected")
        self.update_serial_display()

    # ========================================
    # TAB 4: ACTIVITY LOG
    # ========================================
    def create_log_tab(self):
        """Create activity log tab"""
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        
        log_container = ttk.LabelFrame(self.log_frame, text="System Activity Log", padding=10)
        log_container.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')
        log_container.grid_rowconfigure(0, weight=1)
        log_container.grid_columnconfigure(0, weight=1)
        
        self.activity_log = scrolledtext.ScrolledText(
            log_container,
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.activity_log.grid(row=0, column=0, sticky='nsew')
        
        # Buttons
        btn_frame = ttk.Frame(log_container)
        btn_frame.grid(row=1, column=0, pady=10, sticky='ew')
        
        ttk.Button(
            btn_frame,
            text="🗑️ Clear Log",
            command=self.clear_activity_log
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="💾 Export Log",
            command=self.export_activity_log
        ).pack(side=tk.LEFT, padx=5)

    def log_activity(self, message):
        """Log general activity"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.activity_log.configure(state=tk.NORMAL)
        self.activity_log.insert(tk.END, log_entry)
        self.activity_log.see(tk.END)
        self.activity_log.configure(state=tk.DISABLED)
        
        # Also print to console
        print(log_entry.strip())

    def clear_activity_log(self):
        """Clear activity log"""
        self.activity_log.configure(state=tk.NORMAL)
        self.activity_log.delete(1.0, tk.END)
        self.activity_log.configure(state=tk.DISABLED)
        self.log_activity("🗑️ Log cleared")

    def export_activity_log(self):
        """Export activity log"""
        try:
            filename = f"forwarder_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            content = self.activity_log.get(1.0, tk.END)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.log_activity(f"💾 Log exported to {filename}")
            messagebox.showinfo("Success", f"Log exported to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export log:\n{str(e)}")

    # ========================================
    # TAB 5: STATISTICS
    # ========================================
    def create_stats_tab(self):
        """Create statistics tab"""
        self.stats_frame.grid_rowconfigure(0, weight=1)
        self.stats_frame.grid_columnconfigure(0, weight=1)
        
        stats_container = ttk.LabelFrame(self.stats_frame, text="Forwarding Statistics", padding=20)
        stats_container.grid(row=0, column=0, padx=20, pady=20, sticky='nsew')
        
        # Stats display
        self.stats_text = tk.Text(
            stats_container,
            font=("Consolas", 12),
            bg='#ecf0f1',
            fg='#2c3e50',
            state=tk.DISABLED,
            wrap=tk.WORD,
            height=20
        )
        self.stats_text.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Buttons
        btn_frame = ttk.Frame(stats_container)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            btn_frame,
            text="🔄 Refresh Statistics",
            command=self.refresh_statistics,
            style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="🔄 Reset Statistics",
            command=self.reset_statistics
        ).pack(side=tk.LEFT, padx=5)
        
        # Auto-refresh
        self.refresh_statistics()

    def refresh_statistics(self):
        """Refresh statistics display"""
        uptime = datetime.now() - self.stats['session_start']
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        last_forward = self.stats['last_forward_time'].strftime('%Y-%m-%d %H:%M:%S') if self.stats['last_forward_time'] else 'Never'
        
        success_rate = 0
        total_attempts = self.stats['total_forwarded'] + self.stats['total_failed']
        if total_attempts > 0:
            success_rate = (self.stats['total_forwarded'] / total_attempts) * 100
        
        stats_text = f"""
╔══════════════════════════════════════════════════════════╗
║               FORWARDING STATISTICS                      ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  📊 Total Data Forwarded: {self.stats['total_forwarded']:,} packets
║  ❌ Total Failed: {self.stats['total_failed']:,} packets
║  📈 Success Rate: {success_rate:.2f}%
║                                                          ║
║  🌐 Socket Forwarded: {self.stats['socket_forwarded']:,} packets
║  🔌 Serial Forwarded: {self.stats['serial_forwarded']:,} packets
║                                                          ║
║  💾 Total Bytes: {self.stats['bytes_forwarded']:,} bytes
║  ⏱️  Last Forward: {last_forward}
║                                                          ║
║  🕐 Session Uptime: {hours}h {minutes}m
║  🚀 Session Start: {self.stats['session_start'].strftime('%Y-%m-%d %H:%M:%S')}
║                                                          ║
╚══════════════════════════════════════════════════════════╝
Target Parser: {self.forwarding_config['target_host']}:{self.forwarding_config['target_port']}
Socket Server: {self.socket_config['host']}:{self.socket_config['port']} ({'🟢 Active' if self.socket_running else '⚪ Inactive'})
Serial Ports: {sum(1 for r in self.serial_running.values() if r)} / {len(self.serial_configs)} connected
"""
        self.stats_text.configure(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(1.0, stats_text)
        self.stats_text.configure(state=tk.DISABLED)

    def reset_statistics(self):
        """Reset statistics"""
        if messagebox.askyesno("Confirm Reset", "Are you sure you want to reset all statistics?"):
            self.stats = {
                'total_forwarded': 0,
                'total_failed': 0,
                'socket_forwarded': 0,
                'serial_forwarded': 0,
                'bytes_forwarded': 0,
                'last_forward_time': None,
                'session_start': datetime.now()
            }
            self.refresh_statistics()
            self.log_activity("📊 Statistics reset")

    # ========================================
    # CORE FORWARDING FUNCTION
    # ========================================
    def forward_data(self, raw_data, source_type, source_identifier):
        """Forward raw data to parser"""
        target_host = self.forwarding_config['target_host']
        target_port = self.forwarding_config['target_port']
        
        def send_data():
            try:
                # Create connection
                forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                forward_socket.settimeout(self.forwarding_config['timeout'])
                forward_socket.connect((target_host, target_port))
                
                # Send raw data
                forward_socket.send(raw_data.encode('utf-8'))
                
                # Wait for ACK
                try:
                    ack = forward_socket.recv(1024).decode('utf-8', errors='ignore')
                    ack_status = "✅ ACK" if "<ACK>" in ack else "⚠️ No ACK"
                except:
                    ack_status = "⚠️ No ACK"
                
                forward_socket.close()
                
                # Update statistics
                self.stats['total_forwarded'] += 1
                self.stats['bytes_forwarded'] += len(raw_data)
                self.stats['last_forward_time'] = datetime.now()
                
                if source_type == 'socket':
                    self.stats['socket_forwarded'] += 1
                else:
                    self.stats['serial_forwarded'] += 1
                
                self.root.after(0, lambda: self.log_activity(
                    f"✅ Forwarded {len(raw_data)} bytes from [{source_identifier}] → {target_host}:{target_port} {ack_status}"
                ))
                
            except socket.timeout:
                self.stats['total_failed'] += 1
                self.root.after(0, lambda: self.log_activity(
                    f"❌ Timeout forwarding from [{source_identifier}]"
                ))
            except ConnectionRefusedError:
                self.stats['total_failed'] += 1
                self.root.after(0, lambda: self.log_activity(
                    f"❌ Connection refused by parser at {target_host}:{target_port}"
                ))
            except Exception as e:
                self.stats['total_failed'] += 1
                self.root.after(0, lambda: self.log_activity(
                    f"❌ Forward error from [{source_identifier}]: {str(e)}"
                ))
        
        threading.Thread(target=send_data, daemon=True).start()

    # ========================================
    # EXIT
    # ========================================
    def exit_application(self):
        """Exit application"""
        if self.socket_running or any(self.serial_running.values()):
            if messagebox.askyesno("Confirm Exit", 
                "Active connections detected!\n\n"
                "Do you want to disconnect and exit?"):
                
                # Disconnect all
                self.stop_socket_server()
                self.disconnect_all_serial()
                time.sleep(0.5)
        
        # Save config
        self.save_config()
        
        self.root.quit()
        self.root.destroy()

def main():
    root = tk.Tk()
    # Configure styles
    style = ttk.Style()
    style.theme_use('clam')

    style.configure('Accent.TButton',
                foreground='white',
                background='#3498db',
                font=('Arial', 10, 'bold'),
                padding=8)
    style.map('Accent.TButton',
            background=[('active', '#2980b9'), ('pressed', '#21618c')])

    style.configure('TLabelframe',
                background='#f0f0f0',
                borderwidth=2,
                relief='groove')
    style.configure('TLabelframe.Label',
                font=('Arial', 10, 'bold'),
                foreground='#2c3e50')

    style.configure('TNotebook',
                background='#f0f0f0',
                borderwidth=0)
    style.configure('TNotebook.Tab',
                padding=[15, 8],
                font=('Arial', 10, 'bold'))
    style.map('TNotebook.Tab',
            background=[('selected', '#3498db')],
            foreground=[('selected', 'white')])

    style.configure('Treeview',
                background='white',
                foreground='black',
                fieldbackground='white',
                font=('Arial', 9))
    style.configure('Treeview.Heading',
                font=('Arial', 10, 'bold'),
                background='#ecf0f1',
                foreground='#2c3e50')
    style.map('Treeview',
            background=[('selected', '#3498db')],
            foreground=[('selected', 'white')])

    app = DataForwarder(root)
    root.mainloop()

if __name__ == "__main__":
    main()