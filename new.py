import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import psycopg2
from datetime import datetime
import threading
import os
import socket
import json
import requests
import serial
import serial.tools.list_ports
import time

class HL7ParserGUI:
# 1. ===SETTING INISIALISASI===
    def __init__(self, root):
        self.root = root
        self.root.title("Data Parser - LIMS Simulation")
        
        # RESPONSIVE WINDOW SIZE
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(True, True)
        self.root.minsize(800, 600)
        self.root.configure(bg='#f0f0f0')
        
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Database configuration
        self.db_config = {
            'host': '',
            'database': '',
            'user': '',
            'password': '',
        }
        
        # Socket server configuration
        self.socket_config = {
            'host': '0.0.0.0',
            'port': 8080,
            'buffer_size': 65536
        }
        self.socket_server = None
        self.socket_running = False

        # ✅ MULTI SERIAL PORT SUPPORT
        self.serial_connections = {}  # {port_name: serial_object}
        self.serial_threads = {}      # {port_name: thread_object}
        self.serial_running = {}      # {port_name: bool}
        self.serial_configs = {}      # {port_name: config_dict}
        
        # API configuration
        self.api_config = {
            'endpoint': '',
            'method': 'POST',
            'api_key': '',
            'timeout': 30,
            'enabled': False
        }

        self.device_labels = {"socket": {}, "serial": {}}
        self.device_labels_file = "device_labels.json"
        self.load_device_labels()

          # ===== ✅ NEW: AUTO-STARTUP CONFIGURATION =====
        self.config_file = "app_config.json"  # Main configuration file
        self.auto_startup_enabled = False
        self.last_connected_serials = []  # Track which ports were connected
        self.socket_was_running = False   # Track if socket was running
                
        # ✅ LOAD SAVED CONFIGURATION ON STARTUP
        config_loaded = self.load_app_configuration()
        
        self.adjust_ui_for_resolution()
        # Create menu bar
        self.create_menu()
        
        # Create main interface
        self.create_widgets()

        # ✅ Log to UI AFTER widgets are created
        if config_loaded:
            self.log_multi_serial("Configuration loaded from previous session")
            if self.db_config['host']:
                self.log_multi_serial(f"Database: {self.db_config['host']}/{self.db_config['database']}")
            if self.serial_configs:
                self.log_multi_serial(f"Serial Ports: {len(self.serial_configs)} configured")
            if self.socket_config['port'] != 8080:
                self.log_multi_serial(f"Socket Port: {self.socket_config['port']}")

        # Configure window close event
        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)
        self.root.bind('<Configure>', self.on_window_resize)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.exit_fullscreen)
        self.is_fullscreen = False

        # Delay auto-reconnect to ensure UI is fully loaded
        self.root.after(1000, self.auto_reconnect_devices)

    def load_device_labels(self):
        """Load saved device labels from JSON file"""
        if os.path.exists(self.device_labels_file):
            try:
                with open(self.device_labels_file, "r") as f:
                    self.device_labels = json.load(f)
            except Exception as e:
                self.device_labels = {"socket": {}, "serial": {}}
                self.update_status(f"Failed to load device labels: {str(e)}")

    def save_device_labels(self):
        """Save current device labels to JSON file"""
        try:
            with open(self.device_labels_file, "w") as f:
                json.dump(self.device_labels, f, indent=4)
            self.update_status("Device labels saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save device labels: {str(e)}")

    def load_app_configuration(self):
        """Load saved application configuration from JSON file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # ✅ Load Database Config
                if 'database' in config:
                    self.db_config = config['database']
                    print("✅ Database configuration loaded")  # ← GUNAKAN print()
                
                # ✅ Load Socket Config
                if 'socket' in config:
                    self.socket_config = config['socket']
                    self.socket_was_running = config.get('socket_was_running', False)
                    print("✅ Socket configuration loaded")  # ← GUNAKAN print()
                
                # ✅ Load Serial Configs
                if 'serial_configs' in config:
                    self.serial_configs = config['serial_configs']
                    print(f"✅ Loaded {len(self.serial_configs)} serial port configurations")  # ← GUNAKAN print()
                
                # ✅ Load Last Connected Serials
                if 'last_connected_serials' in config:
                    self.last_connected_serials = config['last_connected_serials']
                    print(f"ℹ️  Last session: {len(self.last_connected_serials)} serial ports were connected")  # ← GUNAKAN print()
                
                # ✅ Load API Config
                if 'api' in config:
                    self.api_config = config['api']
                    print("✅ API configuration loaded")  # ← GUNAKAN print()
                
                # ✅ Load Auto-Startup Setting
                if 'auto_startup_enabled' in config:
                    self.auto_startup_enabled = config['auto_startup_enabled']
                
                print("Configuration loaded from last session")  # ← GUNAKAN print()
                return True
                
            except Exception as e:
                print(f"Failed to load configuration: {str(e)}")  # ← GUNAKAN print()
                return False
        else:
            print("No saved configuration found - using defaults")  # ← GUNAKAN print()
            return False

    def save_app_configuration(self):
        """Save current application configuration to JSON file"""
        try:
            # Collect current connected serial ports
            connected_serials = [
                port_name for port_name, is_running in self.serial_running.items() 
                if is_running
            ]
            
            config = {
                'database': self.db_config,
                'socket': self.socket_config,
                'socket_was_running': self.socket_running,
                'serial_configs': self.serial_configs,
                'last_connected_serials': connected_serials,
                'api': self.api_config,
                'auto_startup_enabled': self.auto_startup_enabled,
                'last_saved': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            self.log_multi_serial(f"Configuration saved ({len(connected_serials)} ports connected)")
            return True
            
        except Exception as e:
            self.log_multi_serial(f"Failed to save configuration: {str(e)}")
            return False

    def auto_reconnect_devices(self):
        """Auto-reconnect devices that were connected in last session"""
        if not self.auto_startup_enabled:
            self.log_multi_serial("Auto-startup is disabled")
            return
        
        self.log_multi_serial("Starting auto-reconnect sequence...")
        
        reconnect_count = 0
        
        # ✅ NEW: Auto-test database connection if configured
        if self.db_config['host'] and self.db_config['database']:
            self.log_multi_serial("Testing database connection...")
            try:
                # Test in background thread
                def test_db():
                    try:
                        conn = psycopg2.connect(**self.db_config)
                        conn.close()
                        self.root.after(0, lambda: self.conn_status.configure(
                            text="✓ Connection successful (auto-tested)", 
                            fg='#27ae60'
                        ))
                        self.root.after(0, lambda: self.log_multi_serial("Database connection verified"))
                    except Exception as e:
                        self.root.after(0, lambda: self.conn_status.configure(
                            text=f"✗ Connection failed: {str(e)}", 
                            fg='#e74c3c'
                        ))
                        self.root.after(0, lambda: self.log_multi_serial(f"Database connection failed: {str(e)}"))
                
                threading.Thread(target=test_db, daemon=True).start()
                
            except Exception as e:
                self.log_multi_serial(f"Database test error: {str(e)}")
        
        # ✅ Auto-reconnect Serial Ports
        if self.last_connected_serials:
            self.log_multi_serial(f"🔌 Attempting to reconnect {len(self.last_connected_serials)} serial ports...")
            
            for port_name in self.last_connected_serials:
                if port_name in self.serial_configs:
                    try:
                        self.log_multi_serial(f"   Reconnecting {port_name}...")
                        self.connect_single_port(port_name)
                        reconnect_count += 1
                        time.sleep(0.5)
                    except Exception as e:
                        self.log_multi_serial(f"Failed to reconnect {port_name}: {str(e)}")
                else:
                    self.log_multi_serial(f"Configuration for {port_name} not found")
        
        # ✅ Auto-start Socket Server
        if self.socket_was_running:
            try:
                self.log_multi_serial("Auto-starting socket server...")
                self.start_socket_server()
                reconnect_count += 1
            except Exception as e:
                self.log_multi_serial(f"Failed to start socket server: {str(e)}")
        
        # Summary
        if reconnect_count > 0:
            self.update_status(f"Auto-reconnected {reconnect_count} device(s)")
            messagebox.showinfo("Auto-Startup Complete", 
                f"Configuration restored:\n\n"
                f"Database: {'Connected' if self.db_config['host'] else 'Not configured'}\n"
                f"Socket: {'Running' if self.socket_running else 'Stopped'}\n"
                f"Serial Ports: {reconnect_count} reconnected\n\n"
                "System ready!")
        else:
            self.update_status("Configuration loaded - no devices to reconnect")

# 2. ===SETTING GUI APLIKASI===
    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode"""
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        return 'break'

    def exit_fullscreen(self, event=None):
        """Exit fullscreen mode"""
        self.is_fullscreen = False
        self.root.attributes('-fullscreen', False)
        return 'break'

    def on_window_resize(self, event):
            """Handle window resize events"""
            # Only process resize events for the root window
            if event.widget == self.root:
                # Adjust layouts if needed
                pass
        
    def create_menu(self):
        # """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open File", command=self.load_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.exit_application, accelerator="Alt+F4")
        
        connection_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Connection", menu=connection_menu)
        connection_menu.add_command(label="Socket Settings", command=self.show_socket_settings)
        connection_menu.add_separator()
        connection_menu.add_command(label="Start Socket Server", command=self.start_socket_server)
        connection_menu.add_command(label="Stop Socket Server", command=self.stop_socket_server)
        connection_menu.add_separator()
        connection_menu.add_command(label="API Settings", command=self.show_api_settings)
        
        database_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Database", menu=database_menu)
        database_menu.add_command(label="Test Connection", command=self.test_connection)
        database_menu.add_command(label="Database Settings", command=lambda: self.notebook.select(2))

        # ===== ✅ NEW: SETTINGS MENU =====
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        # Auto-startup checkbox
        self.auto_startup_var = tk.BooleanVar(value=self.auto_startup_enabled)
        settings_menu.add_checkbutton(
            label="Enable Auto-Startup",
            variable=self.auto_startup_var,
            command=self.toggle_auto_startup
        )
        
        settings_menu.add_separator()
        settings_menu.add_command(label="Save Configuration Now", command=self.manual_save_config)
        settings_menu.add_command(label="Reset Configuration", command=self.reset_configuration)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
        self.root.bind_all("<Control-o>", lambda e: self.load_file())

    def toggle_auto_startup(self):
        """Toggle auto-startup feature"""
        self.auto_startup_enabled = self.auto_startup_var.get()
        
        if self.auto_startup_enabled:
            # Save immediately when enabled
            self.save_app_configuration()
            self.log_multi_serial("Auto-startup ENABLED - Configuration will be saved automatically")
            messagebox.showinfo("Auto-Startup Enabled", 
                "Auto-startup is now enabled!\n\n"
                "Your configuration will be saved automatically and "
                "devices will reconnect when you restart the application.")
        else:
            self.log_multi_serial("Auto-startup DISABLED")
            messagebox.showinfo("Auto-Startup Disabled", 
                "Auto-startup is now disabled.\n\n"
                "Configuration will not be saved automatically.")

    def manual_save_config(self):
        """Manually save configuration"""
        if self.save_app_configuration():
            messagebox.showinfo("Success", 
                "Configuration saved successfully!\n\n"
                f"Database: {'Configured' if self.db_config['host'] else 'Not set'}\n"
                f"Socket: {self.socket_config['host']}:{self.socket_config['port']}\n"
                f"Serial Ports: {len(self.serial_configs)} configured\n"
                f"Connected Ports: {sum(1 for r in self.serial_running.values() if r)}")
        else:
            messagebox.showerror("Error", "Failed to save configuration")

    def reset_configuration(self):
        """Reset all configuration to defaults"""
        if messagebox.askyesno("Confirm Reset", 
            "Are you sure you want to reset all configuration to defaults?\n\n"
            "This will:\n"
            "• Clear database settings\n"
            "• Reset socket settings\n"
            "• Remove all serial port configurations\n"
            "• Clear API settings\n\n"
            "This action cannot be undone!"):
            
            try:
                # Delete config file
                if os.path.exists(self.config_file):
                    os.remove(self.config_file)
                
                # Reset to defaults
                self.db_config = {'host': '', 'database': '', 'user': '', 'password': ''}
                self.socket_config = {'host': '0.0.0.0', 'port': 8080, 'buffer_size': 65536}
                self.serial_configs = {}
                self.serial_running = {}
                self.api_config = {'endpoint': '', 'method': 'POST', 'api_key': '', 'timeout': 30, 'enabled': False}
                self.last_connected_serials = []
                self.socket_was_running = False
                
                # Update UI
                self.update_ports_display()
                
                self.log_multi_serial("Configuration reset to defaults")
                messagebox.showinfo("Reset Complete", 
                    "Configuration has been reset to defaults.\n\n"
                    "Please restart the application for full effect.")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reset configuration: {str(e)}")
        
    def create_widgets(self):
        title_label = tk.Label(
            self.root, 
            text="Data Parser & Database Input System",
            font=("Arial", 16, "bold"),
            bg='#f0f0f0',
            fg='#2c3e50'
        )
        title_label.grid(row=0, column=0, pady=10, sticky='ew')
        
        self.notebook = ttk.Notebook(self.root)

        exit_button = tk.Button(
            self.root,
            text="Exit Application",
            bg="#e74c3c", fg="white",
            font=("Arial", 9, "bold"),
            relief="raised",
            command=self.exit_application
        )
        exit_button.place(relx=1.0, x=-10, y=10, anchor="ne")

        self.notebook.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        
        self.input_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.input_frame, text="File Input")
        self.create_input_tab()
        
        self.socket_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.socket_frame, text="Socket Connection")
        self.create_socket_tab()
        
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="Database Config")
        self.create_config_tab()
        
        self.results_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.results_frame, text="Results")
        self.create_results_tab()
        
        self.api_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.api_frame, text="API Integration")
        self.create_api_tab()

        self.serial_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.serial_frame, text="Serial Ports")
        self.create_multi_serial_tab()

        self.device_label_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.device_label_frame, text="Device Labels")
        self.create_device_labels_tab()

    def adjust_ui_for_resolution(self):
        """Adjust UI elements based on screen resolution"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Determine scale factor
        if screen_width <= 1366:  # Small screens
            font_scale = 0.9
            padding_scale = 0.8
        elif screen_width <= 1920:  # Normal screens (HD/Full HD)
            font_scale = 1.0
            padding_scale = 1.0
        else:  # Large screens (4K+)
            font_scale = 1.2
            padding_scale = 1.2
        
        # Update styles dengan scale
        style = ttk.Style()
        
        base_font_size = int(10 * font_scale)
        title_font_size = int(16 * font_scale)
        padding = int(6 * padding_scale)
        
        style.configure('Accent.TButton', 
                    font=('Arial', base_font_size, 'bold'),
                    padding=padding)
        
        style.configure('TLabelframe.Label', 
                    font=('Arial', base_font_size, 'bold'))
        
        # Update window minimum size based on screen
        min_width = int(1000 * padding_scale)
        min_height = int(700 * padding_scale)
        self.root.minsize(min_width, min_height)

# 3. ===SETTING TAB MENU TAMPILAN GUI===
    def create_input_tab(self):
        # Configure grid weights for responsive layout
        self.input_frame.grid_rowconfigure(0, weight=0)  # File operations
        self.input_frame.grid_rowconfigure(1, weight=1)  # File content (expandable)
        self.input_frame.grid_rowconfigure(2, weight=0)  # Process buttons
        self.input_frame.grid_rowconfigure(3, weight=0)  # Status
        self.input_frame.grid_rowconfigure(4, weight=0)  # Exit
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        # File operations frame
        file_frame = ttk.LabelFrame(self.input_frame, text="File Operations", padding=10)
        file_frame.grid(row=0, column=0, padx=10, pady=5, sticky='ew')
        
        # Configure internal grid
        file_frame.grid_columnconfigure(0, weight=1)
        
        # File selection frame
        select_frame = ttk.Frame(file_frame)
        select_frame.grid(row=0, column=0, sticky='ew', pady=5)
        select_frame.grid_columnconfigure(1, weight=1)  # File label expands
        
        ttk.Label(select_frame, text="Selected File:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky='w')
        
        self.file_path_label = tk.Label(
            select_frame,
            text="No file selected",
            bg='#f8f9fa',
            fg='#6c757d',
            font=("Arial", 9),
            relief=tk.SUNKEN,
            anchor=tk.W,
            padx=10,
            pady=5
        )
        self.file_path_label.grid(row=0, column=1, sticky='ew', padx=(10, 0))
        
        # Buttons frame with responsive layout
        button_frame = ttk.Frame(file_frame)
        button_frame.grid(row=1, column=0, sticky='ew', pady=5)
        
        # ✅ Use grid for buttons with proper spacing
        ttk.Button(
            button_frame,
            text="Browse File", 
            command=self.load_file,
            style="Accent.TButton"
        ).grid(row=0, column=0, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            button_frame, 
            text="Reload File", 
            command=self.reload_file,
            state=tk.DISABLED
        ).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        self.reload_button = button_frame.grid_slaves(row=0, column=1)[0]
        
        ttk.Button(
            button_frame, 
            text="Clear", 
            command=self.clear_data
        ).grid(row=0, column=2, padx=5, pady=2, sticky='ew')
        
        # ✅ Make buttons expand equally
        for i in range(3):
            button_frame.grid_columnconfigure(i, weight=1)
        
        # HL7 Content Display frame (Read-only) - EXPANDABLE
        display_frame = ttk.LabelFrame(self.input_frame, text="File Content (Read-Only)", padding=10)
        display_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        
        # ✅ Configure display frame to expand
        display_frame.grid_rowconfigure(0, weight=1)
        display_frame.grid_columnconfigure(0, weight=1)
        
        self.hl7_text = scrolledtext.ScrolledText(
            display_frame,
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg='#f8f9fa'
        )
        self.hl7_text.grid(row=0, column=0, sticky='nsew')
        
        # Processing buttons frame
        process_frame = ttk.Frame(self.input_frame)
        process_frame.grid(row=2, column=0, padx=10, pady=5, sticky='ew')
        
        # ✅ Configure button columns
        for i in range(3):
            process_frame.grid_columnconfigure(i, weight=1)
        
        ttk.Button(
            process_frame,
            text="Parse Data",
            command=self.parse_data,
            style="Accent.TButton",
            state=tk.DISABLED
        ).grid(row=0, column=0, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            process_frame,
            text="Save to Database",
            command=self.save_to_database,
            state=tk.DISABLED
        ).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            process_frame,
            text="Clear File Content",
            command=self.clear_file_content
        ).grid(row=0, column=2, padx=5, pady=2, sticky='ew')
        
        # Store references to buttons
        self.parse_button = process_frame.grid_slaves(row=0, column=0)[0]
        self.save_button = process_frame.grid_slaves(row=0, column=1)[0]
        
        # Status frame
        self.status_label = tk.Label(
            self.input_frame,
            text="Please select file to begin",
            bg='#f0f0f0',
            fg='#7f8c8d',
            font=("Arial", 9)
        )
        self.status_label.grid(row=3, column=0, pady=5, sticky='ew')
        
        # Store current file path
        self.current_file_path = None

    def create_socket_tab(self):
        """Create socket connection tab with responsive layout"""
        self.socket_frame.grid_rowconfigure(0, weight=0)  # Config
        self.socket_frame.grid_rowconfigure(1, weight=1)  # Log (expandable)
        self.socket_frame.grid_rowconfigure(2, weight=1)  # Data (expandable)
        self.socket_frame.grid_rowconfigure(3, weight=0)  # Buttons
        self.socket_frame.grid_columnconfigure(0, weight=1)
            
        # Socket Configuration frame
        config_frame = ttk.LabelFrame(self.socket_frame, text="Socket Server Configuration", padding=10)
        config_frame.grid(row=0, column=0, padx=10, pady=5, sticky='ew')
            
        # ✅ Configure internal grid
        config_frame.grid_columnconfigure(1, weight=1)
            
            # Host and Port settings
        settings_frame = ttk.Frame(config_frame)
        settings_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)
            
            # ✅ Responsive grid for settings
        ttk.Label(settings_frame, text="Host:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.socket_host_entry = ttk.Entry(settings_frame, width=20)
        self.socket_host_entry.insert(0, self.socket_config['host'])
        self.socket_host_entry.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
            
        ttk.Label(settings_frame, text="Port:").grid(row=0, column=2, sticky='w', padx=5, pady=2)
        self.socket_port_entry = ttk.Entry(settings_frame, width=10)
        self.socket_port_entry.insert(0, str(self.socket_config['port']))
        self.socket_port_entry.grid(row=0, column=3, padx=5, pady=2, sticky='ew')
            
        ttk.Label(settings_frame, text="Buffer Size:").grid(row=0, column=4, sticky='w', padx=5, pady=2)
        self.socket_buffer_entry = ttk.Entry(settings_frame, width=10)
        self.socket_buffer_entry.insert(0, str(self.socket_config['buffer_size']))
        self.socket_buffer_entry.grid(row=0, column=5, padx=5, pady=2, sticky='ew')
            
            # Make entry columns expandable
        settings_frame.grid_columnconfigure(1, weight=1)
        settings_frame.grid_columnconfigure(3, weight=1)
        settings_frame.grid_columnconfigure(5, weight=1)
            
            # Control buttons
        control_frame = ttk.Frame(config_frame)
        control_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
            
            # Configure button columns
        for i in range(3):
            control_frame.grid_columnconfigure(i, weight=1)
            
        self.start_socket_btn = ttk.Button(
            control_frame,
            text="🟢 Start Socket Server",
            command=self.start_socket_server,
            style="Accent.TButton"
        )
        self.start_socket_btn.grid(row=0, column=0, padx=5, pady=2, sticky='ew')
            
        self.stop_socket_btn = ttk.Button(
            control_frame,
            text="🔴 Stop Socket Server",
            command=self.stop_socket_server,
            state=tk.DISABLED
        )
        self.stop_socket_btn.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
            
        ttk.Button(
            control_frame,
            text="Update Settings",
            command=self.update_socket_config
        ).grid(row=0, column=2, padx=5, pady=2, sticky='ew')
            
            # Server status
        self.socket_status_label = tk.Label(
            config_frame,
            text="Server Status: Stopped",
            fg='#e74c3c',
            font=("Arial", 10, "bold")
        )
        self.socket_status_label.grid(row=2, column=0, columnspan=2, pady=5, sticky='ew')
            
            # Connection log frame - EXPANDABLE
        log_frame = ttk.LabelFrame(self.socket_frame, text="Connection Log", padding=10)
        log_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
            
            # Configure log frame to expand
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
            
        self.socket_log = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.socket_log.grid(row=0, column=0, sticky='nsew')
            
            # Received data frame - EXPANDABLE
        data_frame = ttk.LabelFrame(self.socket_frame, text="Last Received Data", padding=10)
        data_frame.grid(row=2, column=0, padx=10, pady=5, sticky='nsew')
            
            # Configure data frame to expand
        data_frame.grid_rowconfigure(0, weight=1)
        data_frame.grid_columnconfigure(0, weight=1)
            
        self.received_data_text = scrolledtext.ScrolledText(
            data_frame,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg='#f8f9fa'
        )
        self.received_data_text.grid(row=0, column=0, sticky='nsew')
            
            # Process buttons for socket data
        socket_process_frame = ttk.Frame(self.socket_frame)
        socket_process_frame.grid(row=3, column=0, padx=10, pady=5, sticky='ew')
            
        # Configure button columns
        for i in range(4):
            socket_process_frame.grid_columnconfigure(i, weight=1)
            
        self.parse_socket_btn = ttk.Button(
            socket_process_frame,
            text="Parse Socket Data",
            command=self.parse_socket_data,
            state=tk.DISABLED,
            style="Accent.TButton"
        )
        self.parse_socket_btn.grid(row=0, column=0, padx=5, pady=2, sticky='ew')
            
        self.save_socket_btn = ttk.Button(
            socket_process_frame,
            text="Save to Database",
            command=self.save_socket_to_database,
            state=tk.DISABLED
        )
        self.save_socket_btn.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
            
        ttk.Button(
            socket_process_frame,
            text="Clear Received Data",
            command=self.clear_received_data
        ).grid(row=0, column=2, padx=5, pady=2, sticky='ew')
            
        ttk.Button(
            socket_process_frame,
            text="Clear Log",
            command=self.clear_socket_log
        ).grid(row=0, column=3, padx=5, pady=2, sticky='ew')
        
    def create_config_tab(self):
        # Configure grid weights
        self.config_frame.grid_rowconfigure(0, weight=1)
        self.config_frame.grid_columnconfigure(0, weight=1)
        
        config_frame = ttk.LabelFrame(self.config_frame, text="PostgreSQL Database Configuration", padding=20)
        config_frame.grid(row=0, column=0, padx=20, pady=20, sticky='nsew')
        
        # Configure internal grid
        config_frame.grid_columnconfigure(1, weight=1)
        
        # Database config entries with responsive layout
        ttk.Label(config_frame, text="Host:").grid(row=0, column=0, sticky='w', pady=5, padx=5)
        self.host_entry = ttk.Entry(config_frame)
        self.host_entry.insert(0, self.db_config['host'])
        self.host_entry.grid(row=0, column=1, pady=5, padx=5, sticky='ew')
        
        ttk.Label(config_frame, text="Database:").grid(row=1, column=0, sticky='w', pady=5, padx=5)
        self.db_entry = ttk.Entry(config_frame)
        self.db_entry.insert(0, self.db_config['database'])
        self.db_entry.grid(row=1, column=1, pady=5, padx=5, sticky='ew')
        
        ttk.Label(config_frame, text="Username:").grid(row=2, column=0, sticky='w', pady=5, padx=5)
        self.user_entry = ttk.Entry(config_frame)
        self.user_entry.insert(0, self.db_config['user'])
        self.user_entry.grid(row=2, column=1, pady=5, padx=5, sticky='ew')
        
        ttk.Label(config_frame, text="Password:").grid(row=3, column=0, sticky='w', pady=5, padx=5)
        self.pass_entry = ttk.Entry(config_frame, show="*")
        self.pass_entry.insert(0, self.db_config['password'])
        self.pass_entry.grid(row=3, column=1, pady=5, padx=5, sticky='ew')
        
        # Buttons
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20, sticky='ew')
        
        # ✅ Configure button columns
        for i in range(2):
            button_frame.grid_columnconfigure(i, weight=1)
        
        ttk.Button(
            button_frame,
            text="Test Connection",
            command=self.test_connection
        ).grid(row=0, column=0, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            button_frame,
            text="Update Config",
            command=self.update_config
        ).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # Connection status
        self.conn_status = tk.Label(
            config_frame,
            text="Connection not tested",
            fg='#f39c12',
            font=("Arial", 10)
        )
        self.conn_status.grid(row=5, column=0, columnspan=2, pady=10, sticky='ew')

    def create_results_tab(self):
        # Configure grid weights
        self.results_frame.grid_rowconfigure(0, weight=0)  # Patient info
        self.results_frame.grid_rowconfigure(1, weight=1)  # Results table (expandable)
        self.results_frame.grid_columnconfigure(0, weight=1)
        
        # Patient info frame
        patient_frame = ttk.LabelFrame(self.results_frame, text="Patient Information", padding=10)
        patient_frame.grid(row=0, column=0, padx=10, pady=5, sticky='ew')
        
        # Configure patient frame
        patient_frame.grid_rowconfigure(0, weight=1)
        patient_frame.grid_columnconfigure(0, weight=1)
        
        self.patient_info = tk.Text(patient_frame, height=4, font=("Arial", 10), wrap=tk.WORD)
        self.patient_info.grid(row=0, column=0, sticky='ew')
        
        # Results frame - EXPANDABLE
        results_frame = ttk.LabelFrame(self.results_frame, text="Laboratory Results", padding=10)
        results_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        
        # Configure results frame to expand
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        
        # Treeview for results
        columns = ('Test Name', 'Value', 'Units', 'Reference Range', 'Flag')
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show='headings')
        
        # Define column headings and widths
        for col in columns:
            self.results_tree.heading(col, text=col)
            if col == 'Test Name':
                self.results_tree.column(col, width=200, minwidth=150)
            elif col == 'Reference Range':
                self.results_tree.column(col, width=150, minwidth=100)
            else:
                self.results_tree.column(col, width=100, minwidth=80)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Grid layout for treeview and scrollbars
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
    def create_api_tab(self):
        """Create API integration tab"""
        # Configure grid weights
        self.api_frame.grid_rowconfigure(0, weight=0)  # Config
        self.api_frame.grid_rowconfigure(1, weight=1)  # JSON preview (expandable)
        self.api_frame.grid_rowconfigure(2, weight=0)  # Send buttons
        self.api_frame.grid_rowconfigure(3, weight=1)  # Response log (expandable)
        self.api_frame.grid_columnconfigure(0, weight=1)
        
        # API Configuration frame
        config_frame = ttk.LabelFrame(self.api_frame, text="API Configuration", padding=10)
        config_frame.grid(row=0, column=0, padx=10, pady=5, sticky='ew')
        
        # Configure internal grid
        config_frame.grid_columnconfigure(1, weight=1)
        
        # API Endpoint
        ttk.Label(config_frame, text="API Endpoint:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.api_endpoint_entry = ttk.Entry(config_frame)
        self.api_endpoint_entry.insert(0, self.api_config['endpoint'])
        self.api_endpoint_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky='ew')
        
        # HTTP Method
        ttk.Label(config_frame, text="HTTP Method:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.api_method_var = tk.StringVar(value=self.api_config['method'])
        method_combo = ttk.Combobox(config_frame, textvariable=self.api_method_var, 
                                    values=['POST', 'PUT', 'PATCH'], state='readonly', width=15)
        method_combo.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        # API Key
        ttk.Label(config_frame, text="API Key:").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.api_key_entry = ttk.Entry(config_frame, show="*")
        self.api_key_entry.insert(0, self.api_config['api_key'])
        self.api_key_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky='ew')
        
        # Timeout
        ttk.Label(config_frame, text="Timeout (seconds):").grid(row=3, column=0, sticky='w', padx=5, pady=5)
        self.api_timeout_entry = ttk.Entry(config_frame, width=15)
        self.api_timeout_entry.insert(0, str(self.api_config['timeout']))
        self.api_timeout_entry.grid(row=3, column=1, padx=5, pady=5, sticky='w')
        
        # Enable API
        self.api_enabled_var = tk.BooleanVar(value=self.api_config['enabled'])
        ttk.Checkbutton(
            config_frame,
            text="Enable API Integration",
            variable=self.api_enabled_var
        ).grid(row=4, column=0, columnspan=2, padx=5, pady=10, sticky='w')
        
        # Control buttons
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=5, sticky='ew')
        
        # Configure button columns
        for i in range(2):
            button_frame.grid_columnconfigure(i, weight=1)
        
        ttk.Button(
            button_frame,
            text="Save API Config",
            command=self.save_api_config
        ).grid(row=0, column=0, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            button_frame,
            text="Test API Connection",
            command=self.test_api_connection
        ).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # API Status
        self.api_status_label = tk.Label(
            config_frame,
            text="API Status: Not configured",
            fg='#f39c12',
            font=("Arial", 10, "bold")
        )
        self.api_status_label.grid(row=6, column=0, columnspan=3, pady=5, sticky='ew')
        
        # JSON Payload Preview frame - EXPANDABLE
        preview_frame = ttk.LabelFrame(self.api_frame, text="JSON Payload Preview", padding=10)
        preview_frame.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        
        # ✅ Configure preview frame to expand
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        
        self.json_preview = scrolledtext.ScrolledText(
            preview_frame,
            font=("Consolas", 9),
            wrap=tk.WORD
        )
        self.json_preview.grid(row=0, column=0, sticky='nsew')
        
        # Send to API buttons
        send_frame = ttk.Frame(self.api_frame)
        send_frame.grid(row=2, column=0, padx=10, pady=5, sticky='ew')
        
        # Configure button columns
        for i in range(3):
            send_frame.grid_columnconfigure(i, weight=1)
        
        ttk.Button(
            send_frame,
            text="Generate JSON Payload",
            command=self.generate_json_payload,
            style="Accent.TButton"
        ).grid(row=0, column=0, padx=5, pady=2, sticky='ew')
        
        self.send_api_btn = ttk.Button(
            send_frame,
            text="Send to API",
            command=self.send_to_api,
            state=tk.DISABLED,
            style="Accent.TButton"
        )
        self.send_api_btn.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        ttk.Button(
            send_frame,
            text="Copy JSON",
            command=self.copy_json_to_clipboard
        ).grid(row=0, column=2, padx=5, pady=2, sticky='ew')
        
        # API Response Log frame - EXPANDABLE
        log_frame = ttk.LabelFrame(self.api_frame, text="API Response Log", padding=10)
        log_frame.grid(row=3, column=0, padx=10, pady=5, sticky='nsew')

        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        self.api_response_log = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.api_response_log.grid(row=0, column=0, sticky='nsew')

    def create_multi_serial_tab(self):
        """Create multi serial port connection tab with RESIZABLE sections"""
        # Configure grid weights
        self.serial_frame.grid_rowconfigure(0, weight=0)  # Controls (fixed)
        self.serial_frame.grid_rowconfigure(1, weight=1)  # PanedWindow (expandable)
        self.serial_frame.grid_columnconfigure(0, weight=1)
        
        # === TOP CONTROL PANEL ===
        control_panel = ttk.LabelFrame(self.serial_frame, text="Serial Port Control Panel", padding=10)
        control_panel.grid(row=0, column=0, padx=10, pady=5, sticky='ew')
        
        # Control buttons frame
        btn_frame = ttk.Frame(control_panel)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            btn_frame,
            text="Refresh Available Ports",
            command=self.refresh_all_ports,
            style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Add Port Connection",
            command=self.add_port_connection,
            style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Connect All",
            command=self.connect_all_ports
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Disconnect All",
            command=self.disconnect_all_ports
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Clear All Data",
            command=self.clear_all_serial_data
        ).pack(side=tk.RIGHT, padx=5)
        
        # Status label
        self.multi_serial_status = tk.Label(
            control_panel,
            text="Connected Ports: 0 | Total Configured: 0",
            font=("Arial", 10, "bold"),
            fg='#7f8c8d'
        )
        self.multi_serial_status.pack(pady=5)
        
        # ===== PANED WINDOW FOR RESIZABLE SECTIONS =====
        # Create main PanedWindow (vertical orientation)
        main_paned = ttk.PanedWindow(self.serial_frame, orient=tk.VERTICAL)
        main_paned.grid(row=1, column=0, padx=10, pady=5, sticky='nsew')
        
        # === PANE 1: PORT LIST ===
        port_list_frame = ttk.LabelFrame(main_paned, text="Port Connections", padding=10)
        main_paned.add(port_list_frame, weight=2)  # Initial weight
        
        port_list_frame.grid_rowconfigure(0, weight=1)
        port_list_frame.grid_columnconfigure(0, weight=1)
        
        # Create Treeview for port list
        columns = ('Port', 'Baudrate', 'Status', 'Last Activity')
        self.ports_tree = ttk.Treeview(port_list_frame, columns=columns, show='headings')
        
        # Define column headings
        self.ports_tree.heading('Port', text='Port Name')
        self.ports_tree.heading('Baudrate', text='Baudrate')
        self.ports_tree.heading('Status', text='Status')
        self.ports_tree.heading('Last Activity', text='Last Activity')
        
        # Define column widths
        self.ports_tree.column('Port', width=120, minwidth=100)
        self.ports_tree.column('Baudrate', width=100, minwidth=80)
        self.ports_tree.column('Status', width=120, minwidth=100)
        self.ports_tree.column('Last Activity', width=200, minwidth=150)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(port_list_frame, orient=tk.VERTICAL, command=self.ports_tree.yview)
        self.ports_tree.configure(yscrollcommand=v_scrollbar.set)
        
        self.ports_tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        
        # Port action buttons
        port_btn_frame = ttk.Frame(port_list_frame)
        port_btn_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky='ew')
        
        ttk.Button(
            port_btn_frame,
            text="Configure Selected",
            command=self.configure_selected_port
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            port_btn_frame,
            text="Connect Selected",
            command=self.connect_selected_port
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            port_btn_frame,
            text="Disconnect Selected",
            command=self.disconnect_selected_port
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            port_btn_frame,
            text="Remove Selected",
            command=self.remove_selected_port
        ).pack(side=tk.RIGHT, padx=5)
        
        # === PANE 2: RECEIVED DATA ===
        data_frame = ttk.LabelFrame(main_paned, text="Last Received Data (Serial)", padding=10)
        main_paned.add(data_frame, weight=2)  # Initial weight
        
        data_frame.grid_rowconfigure(0, weight=1)
        data_frame.grid_columnconfigure(0, weight=1)
        
        self.serial_received_data_text = scrolledtext.ScrolledText(
            data_frame,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg='#f8f9fa',
            wrap=tk.WORD
        )
        self.serial_received_data_text.grid(row=0, column=0, sticky='nsew')
        
        # === PANE 3: UNIFIED LOG ===
        log_frame = ttk.LabelFrame(main_paned, text="Serial Communication Log (All Ports)", padding=10)
        main_paned.add(log_frame, weight=3)  # Initial weight (largest)
        
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        self.multi_serial_log = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.multi_serial_log.grid(row=0, column=0, sticky='nsew')
        
        # Log control buttons
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, pady=5, sticky='ew')
        
        ttk.Button(
            log_btn_frame,
            text="Clear Received Data",
            command=self.clear_serial_received_data
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            log_btn_frame,
            text="Clear Log",
            command=self.clear_multi_serial_log
        ).pack(side=tk.LEFT, padx=5)

    def create_device_labels_tab(self):
        """Create Device Labels management tab"""
        self.device_label_frame.grid_rowconfigure(0, weight=1)
        self.device_label_frame.grid_columnconfigure(0, weight=1)

        notebook = ttk.Notebook(self.device_label_frame)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # === SOCKET DEVICES TAB ===
        socket_tab = ttk.Frame(notebook)
        notebook.add(socket_tab, text="Socket Devices")
        self.create_socket_label_tab(socket_tab)

        # === SERIAL DEVICES TAB ===
        serial_tab = ttk.Frame(notebook)
        notebook.add(serial_tab, text="Serial Devices")
        self.create_serial_label_tab(serial_tab)
        
# 4. ===SETTING MENU INPUT FILE===
    def load_file(self):
        """Load HL7 file from disk"""
        filename = filedialog.askopenfilename(
            title="Select File",
            filetypes=[
                ("HL7 files", "*.hl7"),
                ("Text files", "*.txt"), 
                ("All files", "*.*")
            ]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as file:
                    content = file.read()
                    
                # Update display
                self.hl7_text.configure(state=tk.NORMAL)
                self.hl7_text.delete(1.0, tk.END)
                self.hl7_text.insert(1.0, content)
                self.hl7_text.configure(state=tk.DISABLED)
                
                # Update file path display
                self.current_file_path = filename
                file_name = filename.split('/')[-1] if '/' in filename else filename.split('\\')[-1]
                self.file_path_label.configure(text=f"{file_name}", fg='#28a745')
                
                # Enable buttons
                self.reload_button.configure(state=tk.NORMAL)
                self.parse_button.configure(state=tk.NORMAL)
                
                self.update_status(f"File loaded successfully: {file_name}")
                # baru
                # --- AUTOMATIC: langsung parse (parse_data akan memicu save otomatis) ---
                try:
                    self.parse_data()
                except Exception as e:
                    # Kalau parse gagal, tetap tampilkan error pada status/log
                    self.update_status(f"Auto-parse error: {str(e)}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")
                self.update_status("Failed to load file")
                
    def reload_file(self):
        """Reload the current file"""
        if self.current_file_path and os.path.exists(self.current_file_path):
            try:
                with open(self.current_file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    
                # Update display
                self.hl7_text.configure(state=tk.NORMAL)
                self.hl7_text.delete(1.0, tk.END)
                self.hl7_text.insert(1.0, content)
                self.hl7_text.configure(state=tk.DISABLED)
                
                file_name = self.current_file_path.split('/')[-1] if '/' in self.current_file_path else self.current_file_path.split('\\')[-1]
                self.update_status(f"File reloaded successfully: {file_name}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reload file: {str(e)}")
                self.update_status("Failed to reload file")
        else:
            messagebox.showwarning("Warning", "No valid file to reload")
                
    def clear_data(self):
        """Clear all input and results"""
        # Clear file content display
        self.hl7_text.configure(state=tk.NORMAL)
        self.hl7_text.delete(1.0, tk.END)
        self.hl7_text.configure(state=tk.DISABLED)
        
        # Clear results using the dedicated function
        self.clear_results_tab()
            
        # Reset file path
        self.current_file_path = None
        self.file_path_label.configure(text="No file selected", fg='#6c757d')
        
        # Disable buttons
        self.reload_button.configure(state=tk.DISABLED)
        # self.parse_button.configure(state=tk.DISABLED)
        # self.save_button.configure(state=tk.DISABLED)
        
        # Clear stored data
        if hasattr(self, 'patient'):
            delattr(self, 'patient')
        if hasattr(self, 'results'):
            delattr(self, 'results')
        
        self.update_status("Data cleared - Please select an HL7 file")

    def is_valid_patient_id(self, value):  # BARU
        """
        Validate if a value is a valid Patient ID
        Returns: bool
        Rules:
        - Not empty
        - Not just special characters
        - Not purely numeric with length <= 3 (likely sequence number)
        - Not common placeholder values
        """
        if not value or not value.strip():
            return False
        
        value = value.strip()
        
        # Skip if it's empty or just special characters
        if value in ['^', '-', '_', '', '0']:
            return False
        
        # Skip if it's purely numeric with length <= 3 (likely sequence number)
        if value.isdigit() and len(value) <= 3:
            return False
        
        # Skip common placeholder values
        invalid_values = ['UNKNOWN', 'N/A', 'NA', 'NULL', 'NONE', 'TEST', 'NOERS']
        if value.upper() in invalid_values:
            return False
        
        return True
    
    def clear_file_content(self):
        """Clear file content and results"""
        # Clear file content display
        self.hl7_text.configure(state=tk.NORMAL)
        self.hl7_text.delete(1.0, tk.END)
        self.hl7_text.configure(state=tk.DISABLED)
        
        # Clear results in Results tab
        self.clear_results_tab()
        
        # Reset file path
        self.current_file_path = None
        self.file_path_label.configure(text="No file selected", fg='#6c757d')
        
        # Disable buttons
        self.reload_button.configure(state=tk.DISABLED)
        self.parse_button.configure(state=tk.DISABLED)
        self.save_button.configure(state=tk.DISABLED)
        
        # Clear stored data
        if hasattr(self, 'patient'):
            delattr(self, 'patient')
        if hasattr(self, 'results'):
            delattr(self, 'results')
    
# 5. ===SETTING LOGIKA PARSE===
    def parse_hl7(self, hl7_text):
        """
        Parse HL7 data and extract patient ID, sample time, and results
        
        Supports multiple HL7 formats:
        - URIT Standard HL7 (without markers)
        - BS-200 (Mindray)
        - BC-5300 Standard HL7
        - Other standard HL7 devices
        """
        hl7_text = hl7_text.strip()
        lines = []

        # Split into lines
        if '\n' not in hl7_text and '\r' not in hl7_text:
            import re
            segment_pattern = r'(MSH|PID|PV1|ORC|OBR|OBX|NTE|ZDR|ZPR)'
            if re.search(segment_pattern, hl7_text):
                parts = re.split(r'(?=' + segment_pattern + r')', hl7_text)
                lines = [part.strip() for part in parts if part.strip()]
            else:
                lines = [hl7_text]
        else:
            hl7_text = hl7_text.replace('\r\n', '\n').replace('\r', '\n')
            lines = hl7_text.strip().split('\n')

        patient = {}
        results = []
        obr_patient_id = None
        obr_sample_time = None
        pid_patient_name = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            segments = line.split('|')
            if not segments:
                continue

            segment_type = segments[0]

            # ===== MSH Segment (Message Header) =====
            if segment_type == 'MSH':
                try:
                    # Field 7: Message DateTime (YYYYMMDDHHMMSS)
                    if len(segments) > 6 and segments[6]:
                        msg_datetime = segments[6].strip()
                        if len(msg_datetime) >= 14:
                            year = msg_datetime[:4]
                            month = msg_datetime[4:6]
                            day = msg_datetime[6:8]
                            hour = msg_datetime[8:10]
                            minute = msg_datetime[10:12]
                            second = msg_datetime[12:14]
                            obr_sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                            self.log_api_response(f"MSH datetime parsed: {obr_sample_time}")
                        elif len(msg_datetime) >= 8:
                            year = msg_datetime[:4]
                            month = msg_datetime[4:6]
                            day = msg_datetime[6:8]
                            obr_sample_time = f"{year}-{month}-{day}"
                            self.log_api_response(f"MSH date parsed: {obr_sample_time}")
                except Exception as e:
                    self.log_api_response(f"Warning: Error parsing MSH segment: {str(e)}")

            # ===== PID Segment (Patient Identification) =====
            elif segment_type == 'PID':
                try:
                    # Try multiple fields for Patient ID with validation
                    
                    # Field 2: Patient ID (index 1)
                    if not obr_patient_id and len(segments) > 1 and segments[1]:
                        field_value = segments[1].strip()
                        if self.is_valid_patient_id(field_value):
                            obr_patient_id = field_value
                            self.log_api_response(f"Patient ID from PID[2]: {obr_patient_id}")
                    
                    # Field 3: Patient Identifier List (index 2)
                    if not obr_patient_id and len(segments) > 2 and segments[2]:
                        field_value = segments[2].strip()
                        if self.is_valid_patient_id(field_value):
                            obr_patient_id = field_value
                            self.log_api_response(f"Patient ID from PID[3]: {obr_patient_id}")
                    
                    # Field 4: Alternate Patient ID (index 3)
                    if not obr_patient_id and len(segments) > 3 and segments[3]:
                        field_value = segments[3].strip()
                        if self.is_valid_patient_id(field_value):
                            obr_patient_id = field_value
                            self.log_api_response(f"Patient ID from PID[4]: {obr_patient_id}")
                    
                    # Field 5: Patient Name (index 4) - Save for fallback
                    if len(segments) > 4 and segments[4]:
                        pid_patient_name = segments[4].strip()
                        if pid_patient_name and pid_patient_name not in ['^', '', 'NOERS', '0']:
                            patient['patient_name'] = pid_patient_name
                            self.log_api_response(f"Patient Name from PID[5]: {pid_patient_name}")
                    
                except Exception as e:
                    self.log_api_response(f"Warning: Error parsing PID segment: {str(e)}")

            # ===== OBR Segment (Observation Request) =====
            elif segment_type == 'OBR':
                try:
                    # Field 3: Filler Order Number
                    # Use as Patient ID fallback if PID fields are empty/invalid
                    if not obr_patient_id and len(segments) > 2 and segments[2]:
                        order_number = segments[2].strip()
                        if self.is_valid_patient_id(order_number):
                            obr_patient_id = order_number
                            self.log_api_response(f"Patient ID from OBR[3] (Order Number): {obr_patient_id}")

                    # Field 7: Observation Date/Time
                    if len(segments) > 6 and segments[6]:
                        sample_time_raw = segments[6].strip()
                        
                        # Try YYYYMMDDHHMMSS format
                        if len(sample_time_raw) >= 14 and sample_time_raw.isdigit():
                            year = sample_time_raw[:4]
                            month = sample_time_raw[4:6]
                            day = sample_time_raw[6:8]
                            hour = sample_time_raw[8:10]
                            minute = sample_time_raw[10:12]
                            second = sample_time_raw[12:14]
                            if not obr_sample_time:  # Only use if MSH didn't provide
                                obr_sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                self.log_api_response(f"OBR datetime parsed: {obr_sample_time}")
                        
                        # Try YYYYMMDD format
                        elif len(sample_time_raw) >= 8 and sample_time_raw.isdigit():
                            year = sample_time_raw[:4]
                            month = sample_time_raw[4:6]
                            day = sample_time_raw[6:8]
                            if not obr_sample_time:
                                obr_sample_time = f"{year}-{month}-{day}"
                                self.log_api_response(f"OBR date parsed: {obr_sample_time}")
                        
                        # Try YYYY-MM-DD format
                        elif '-' in sample_time_raw:
                            if not obr_sample_time:
                                obr_sample_time = sample_time_raw
                                self.log_api_response(f"OBR date parsed: {obr_sample_time}")
                            
                except Exception as e:
                    self.log_api_response(f"Warning: Error parsing OBR segment: {str(e)}")

            # ===== OBX Segment (Observation Result) =====
            elif segment_type == 'OBX':
                try:
                    if len(segments) > 5:
                        # Handle different OBX formats:
                        # Format 1 (Standard): OBX|1|NM|TEST^TestName|1|Value|Units|Range|Flag
                        # Format 2 (URIT):     OBX|1|NM|1|TestName|Value|Units|Range|Flag
                        # Format 3 (BS-200):   OBX|1|NM|CHOL|CHOL|Value|Units|Range|Flag
                        
                        # Field 3: Observation Identifier (index 3)
                        obs_id = segments[3].split('^') if len(segments) > 3 else []
                        
                        # Determine test name and value positions
                        if len(obs_id) > 1:
                            # Format 1: Standard HL7 with ^ separator
                            # Field 3 = "TEST^TestName"
                            test_name = obs_id[1] if obs_id[1] else obs_id[0]
                            value = segments[5] if len(segments) > 5 else ''
                            units = segments[6] if len(segments) > 6 else ''
                            ref_range = segments[7] if len(segments) > 7 else ''
                            abnormal_flag = segments[8] if len(segments) > 8 else ''
                        elif obs_id and obs_id[0].isdigit():
                            # Format 2: URIT format
                            # Field 3 = "1" (sequence), Field 4 = "TestName"
                            test_name = segments[4] if len(segments) > 4 else 'Unknown Test'
                            value = segments[5] if len(segments) > 5 else ''
                            units = segments[6] if len(segments) > 6 else ''
                            ref_range = segments[7] if len(segments) > 7 else ''
                            abnormal_flag = segments[8] if len(segments) > 8 else ''
                        else:
                            # Format 3: BS-200 or other
                            # Field 3 = "CHOL", Field 4 might also be "CHOL" or empty
                            test_name = obs_id[0] if obs_id else 'Unknown Test'
                            
                            # If Field 4 is not the same as Field 3, it might be a sub-identifier
                            if len(segments) > 4 and segments[4] and segments[4] != test_name:
                                # Value is in Field 5
                                value = segments[5] if len(segments) > 5 else ''
                            else:
                                # Value is in Field 5
                                value = segments[5] if len(segments) > 5 else ''
                            
                            units = segments[6] if len(segments) > 6 else ''
                            ref_range = segments[7] if len(segments) > 7 else ''
                            abnormal_flag = segments[8] if len(segments) > 8 else ''

                        # Field 14: Date/Time of Observation (index 13)
                        obs_time = ''
                        if len(segments) > 14 and segments[14]:
                            obs_time_raw = segments[14].strip()
                            if len(obs_time_raw) >= 14 and obs_time_raw.isdigit():
                                year = obs_time_raw[:4]
                                month = obs_time_raw[4:6]
                                day = obs_time_raw[6:8]
                                hour = obs_time_raw[8:10]
                                minute = obs_time_raw[10:12]
                                obs_time = f"{year}-{month}-{day} {hour}:{minute}"
                            elif '-' in obs_time_raw:
                                obs_time = obs_time_raw

                        # Only add if test name and value exist
                        if test_name and value:
                            results.append({
                                'test_name': test_name,
                                'value': value,
                                'units': units,
                                'reference_range': ref_range,
                                'abnormal_flag': abnormal_flag,
                                'observation_time': obs_time
                            })
                            self.log_api_response(f"OBX parsed: {test_name} = {value} {units}")
                            
                except Exception as e:
                    self.log_api_response(f"Warning: Error parsing OBX segment: {str(e)}")

        # ===== Final Patient ID Assignment =====
        # Priority: PID fields > OBR Order Number > Patient Name
        if not obr_patient_id and pid_patient_name:
            obr_patient_id = pid_patient_name
            self.log_api_response(f"Using Patient Name as ID (fallback): {obr_patient_id}")

        patient['patient_id'] = obr_patient_id if obr_patient_id else 'Unknown'
        patient['sample_time'] = obr_sample_time if obr_sample_time else ''

        self.log_api_response(f"HL7 parsed: Patient ID={patient['patient_id']}, Sample Time={patient['sample_time']}, Results={len(results)}")
        
        return patient, results

    def parse_custom_hl7(self, raw_data):
        """
        Parse Custom HL7 format with special markers (#VTM, #CR, #FS)
        """
        try:
            # STEP 1: Clean markers and normalize
            clean_data = raw_data
            
            # Normalize line endings
            clean_data = clean_data.replace('\r\n', '\n')
            clean_data = clean_data.replace('\r', '\n')
            
            # Remove control markers
            clean_data = clean_data.replace('#VTM', '')
            clean_data = clean_data.replace('#FS', '')
            
            # Replace #CR with newline
            clean_data = clean_data.replace('#CR', '\n')
            
            # Clean up extra whitespace
            clean_data = '\n'.join([line.strip() for line in clean_data.split('\n') if line.strip()])
            
            self.log_api_response(f"Custom HL7 cleaned. Original: {len(raw_data)} bytes → Clean: {len(clean_data)} bytes")
            
            # STEP 2: Parse segments
            lines = clean_data.strip().split('\n')
            
            patient = {}
            results = []
            obr_patient_id = None
            obr_sample_time = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                segments = line.split('|')
                if not segments:
                    continue
                
                segment_type = segments[0]
                
                # ===== MSH Segment =====
                if segment_type == 'MSH':
                    try:
                        # FIX: MSH field 7 (bukan field 6!)
                        # Format: MSH|^~\&|SAGES||||20251017071234||...
                        # Index:  0   1     2     3  4  5  6           7
                        if len(segments) > 6 and segments[6]:
                            msg_datetime = segments[6].strip()
                            if len(msg_datetime) >= 14:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                hour = msg_datetime[8:10]
                                minute = msg_datetime[10:12]
                                second = msg_datetime[12:14]
                                obr_sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                self.log_api_response(f"MSH datetime parsed: {obr_sample_time}")
                            elif len(msg_datetime) >= 8:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                obr_sample_time = f"{year}-{month}-{day}"
                                self.log_api_response(f"MSH date parsed: {obr_sample_time}")
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing MSH datetime: {str(e)}")
                
                # ===== PID Segment =====
                elif segment_type == 'PID':
                    try:
                        # FIX: PID field 1 atau 3 (cek keduanya)
                        # Format: PID|1||1||NOERS|...
                        # Index:  0   1  2 3  4  5
                        
                        # Coba field 1 dulu (index 1)
                        if len(segments) > 1 and segments[1] and segments[1].strip():
                            obr_patient_id = segments[1].strip()
                            self.log_api_response(f"Patient ID parsed from PID[1]: {obr_patient_id}")
                        # Fallback ke field 3 (index 3)
                        elif len(segments) > 3 and segments[3] and segments[3].strip():
                            obr_patient_id = segments[3].strip()
                            self.log_api_response(f"Patient ID parsed from PID[3]: {obr_patient_id}")
                        
                        # PID field 5: Patient Name (optional)
                        if len(segments) > 5 and segments[5]:
                            patient_name = segments[5].strip()
                            if patient_name and patient_name not in ['^', '', 'NOERS']:
                                patient['patient_name'] = patient_name
                        
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing PID segment: {str(e)}")
                
                # ===== OBX Segment =====
                elif segment_type == 'OBX':
                    try:
                        # Format: OBX|NM|1|URIC ACID^1|6|mg/dL|3-6|N||F|||20251017070323|1|
                        # Index:  0   1  2  3            4  5     6   7  8 9 10 11            12
                        
                        if len(segments) > 4:
                            # Field 3: Test name
                            obs_id = segments[3].split('^') if len(segments) > 3 else []
                            test_name = obs_id[0] if obs_id else 'Unknown Test'
                            
                            # Field 4: Value (PENTING!)
                            value = segments[4] if len(segments) > 4 else ''
                            
                            # Field 5: Units
                            units = segments[5] if len(segments) > 5 else ''
                            
                            # Field 6: Reference Range
                            ref_range = segments[6] if len(segments) > 6 else ''
                            
                            # Field 7: Abnormal Flag
                            abnormal_flag = segments[7] if len(segments) > 7 else ''
                            
                            # FIX: Field 12 (bukan field 11!) untuk Observation time
                            obs_time = ''
                            if len(segments) > 12 and segments[12]:
                                obs_time_raw = segments[12].strip()
                                if len(obs_time_raw) >= 14:
                                    year = obs_time_raw[:4]
                                    month = obs_time_raw[4:6]
                                    day = obs_time_raw[6:8]
                                    hour = obs_time_raw[8:10]
                                    minute = obs_time_raw[10:12]
                                    second = obs_time_raw[12:14]
                                    obs_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                    self.log_api_response(f"OBX time parsed: {obs_time}")
                            
                            if test_name and value:
                                results.append({
                                    'test_name': test_name,
                                    'value': value,
                                    'units': units,
                                    'reference_range': ref_range,
                                    'abnormal_flag': abnormal_flag,
                                    'observation_time': obs_time
                                })
                                
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing OBX segment: {str(e)}")
            
            # STEP 3: Assign patient data
            patient['patient_id'] = obr_patient_id if obr_patient_id else 'Unknown'

            # 1. Gunakan waktu dari MSH (message header time)
            # 2. Fallback ke OBX pertama jika MSH kosong
            if obr_sample_time:
                patient['sample_time'] = obr_sample_time
                self.log_api_response(f"Using MSH sample time: {obr_sample_time}")
            elif results and results[0].get('observation_time'):
                patient['sample_time'] = results[0]['observation_time']
                self.log_api_response(f"Using first OBX observation time: {results[0]['observation_time']}")
            else:
                patient['sample_time'] = ''
                self.log_api_response("No sample time found")
            
            # Validation log
            self.log_api_response(f"Custom HL7 parsed: Patient ID={patient['patient_id']}, Sample Time={patient['sample_time']}, Results={len(results)}")
            return patient, results
            
        except Exception as e:
            raise ValueError(f"Error parsing Custom HL7 data: {str(e)}")

    def detect_data_format(self, data):
        """
        Universal data format detection with priority system
        Supports: BC-1800, URIT-8030 Custom, BC-5300, Custom HL7, Standard HL7, ASTM
        """
        data_stripped = data.strip()
        data_upper = data_stripped.upper()
        
        # ===== PRIORITY 1: BC-1800 Format (Very Specific) =====
        if "#STXAAAI" in data_stripped or "STXAAAI" in data_stripped:
            return "BC1800"
        
        # ===== PRIORITY 2: Generic ASTM Format =====
        if "STXA" in data_stripped and "#STXAAAI" not in data_stripped:
            return "ASTM"
        
        # ===== PRIORITY 3: Custom HL7 with Control Markers =====
        # FIX: ONLY detect as Custom HL7 if it HAS control markers (#VTM, #CR, #FS)
        
        # URIT-8030 Custom HL7: Must have markers + urit/8030 identifier
        has_urit_custom = any([
            "#VTM" in data_stripped and ("urit" in data_stripped.lower() or "8030" in data_stripped),
            "#VTMSH" in data_stripped and ("urit" in data_stripped.lower() or "8030" in data_stripped),
        ])
        if has_urit_custom:
            return "URIT_8030"
        
        # BC-5300 Custom HL7: Must have markers + BC-5300/Mindray identifier
        has_bc5300_custom = any([
            "#VTM" in data_stripped and ("BC-5300" in data_upper or "BC5300" in data_upper),
            "#VTMSH" in data_stripped and ("BC-5300" in data_upper or "BC5300" in data_upper),
            "#VTM" in data_stripped and "MINDRAY" in data_upper,
            "#VTMSH" in data_stripped and "MINDRAY" in data_upper,
        ])
        if has_bc5300_custom:
            return "BC5300_HL7"
        
        # Generic Custom HL7: Has control markers but no specific device identifier
        has_control_markers = any([
            "#VTM" in data_stripped,
            "#VTMSH" in data_stripped,
            "#CR" in data_stripped and ("MSH" in data_stripped or "OBX" in data_stripped),
            "#FS" in data_stripped and ("MSH" in data_stripped or "OBX" in data_stripped)
        ])
        if has_control_markers:
            return "CUSTOM_HL7"
        
        # ===== PRIORITY 4: Standard HL7 (Most Common) =====
        # This will catch: URIT Standard HL7, BS-200, and other standard HL7 devices
        has_hl7_segments = any([
            data_stripped.startswith('MSH'),
            'MSH|' in data_stripped and ('OBX|' in data_stripped or 'OBR|' in data_stripped),
            'PID|' in data_stripped and 'OBX|' in data_stripped
        ])
        if has_hl7_segments:
            return "HL7"
        
        # ===== FALLBACK: Default to HL7 =====
        if '|' in data_stripped and len(data_stripped) > 20:
            return "HL7"
        
        return "UNKNOWN"
    
    def parse_bc5300_hl7(self, raw_data):
        """
        Parse BC-5300 Custom HL7 format
        Extract Patient ID dari OBR field 4, Sample Time dari OBR field 7
        """
        try:
            # STEP 1: Clean markers dan normalize
            clean_data = raw_data
            
            # Normalize line endings
            clean_data = clean_data.replace('\r\n', '\n')
            clean_data = clean_data.replace('\r', '\n')
            
            # Remove control markers
            clean_data = clean_data.replace('#VTM', '')
            clean_data = clean_data.replace('#FS', '')
            
            # Replace #CR with newline
            clean_data = clean_data.replace('#CR', '\n')
            
            # Clean up extra whitespace
            clean_data = '\n'.join([line.strip() for line in clean_data.split('\n') if line.strip()])
            
            self.log_api_response(f"BC-5300 HL7 cleaned. Original: {len(raw_data)} bytes → Clean: {len(clean_data)} bytes")
            
            # STEP 2: Parse segments
            lines = clean_data.strip().split('\n')
            
            patient = {}
            patient_id = None
            sample_time = None
            patient_name = None  # Simpan nama untuk informasi
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                segments = line.split('|')
                if not segments:
                    continue
                
                segment_type = segments[0]
                
                # ===== MSH Segment (untuk fallback timestamp jika OBR tidak ada) =====
                if segment_type == 'MSH':
                    try:
                        # Format: MSH|^~\&|BC-5300|Mindray|||20251021164450||...
                        # Index:  0   1         2       3       4 5 6
                        if len(segments) > 6 and segments[6]:
                            msg_datetime = segments[6].strip()
                            if len(msg_datetime) >= 14:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                hour = msg_datetime[8:10]
                                minute = msg_datetime[10:12]
                                second = msg_datetime[12:14]
                                msh_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                # Simpan untuk fallback
                                if not sample_time:
                                    sample_time = msh_time
                                    self.log_api_response(f"BC-5300 MSH time (fallback): {sample_time}")
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing MSH segment: {str(e)}")
                
                # ===== PID Segment (biasanya kosong di BC-5300) =====
                elif segment_type == 'PID':
                    try:
                        # Format: PID|1||||
                        # Field 1 atau field lain biasanya kosong
                        pass
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing PID segment: {str(e)}")
                
                # ===== OBR Segment (PATIENT ID DAN SAMPLE TIME ADA DI SINI) =====
                elif segment_type == 'OBR':
                    try:
                        # Format: OBR|1||NY. IDA|00001^Automated Count^99MRC|||20251021162236|...
                        # Index:  0   1  2 3        4                           5 6 7
                        
                        # FIX 1: Field 3 adalah Patient Name (simpan untuk informasi)
                        if len(segments) > 3 and segments[3] and segments[3].strip():
                            patient_name = segments[3].strip()
                            self.log_api_response(f"BC-5300 Patient Name from OBR[3]: {patient_name}")
                        
                        # FIX 2: Field 4 sub-component pertama adalah Patient ID
                        if len(segments) > 4 and segments[4]:
                            # Split by ^ untuk mendapatkan sub-components
                            field_4_parts = segments[4].split('^')
                            if field_4_parts and field_4_parts[0].strip():
                                patient_id = field_4_parts[0].strip()
                                self.log_api_response(f"BC-5300 Patient ID from OBR[4]: {patient_id}")
                        
                        # FIX 3: Field 7 adalah Sample/Observation datetime (PRIORITAS UTAMA)
                        # Format: 20251021162236 (YYYYMMDDHHmmss)
                        if len(segments) > 7 and segments[7]:
                            sample_time_raw = segments[7].strip()
                            if len(sample_time_raw) >= 14:
                                year = sample_time_raw[:4]
                                month = sample_time_raw[4:6]
                                day = sample_time_raw[6:8]
                                hour = sample_time_raw[8:10]
                                minute = sample_time_raw[10:12]
                                second = sample_time_raw[12:14]
                                sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                self.log_api_response(f"BC-5300 Sample time from OBR[7]: {sample_time}")
                            elif len(sample_time_raw) >= 8:
                                year = sample_time_raw[:4]
                                month = sample_time_raw[4:6]
                                day = sample_time_raw[6:8]
                                sample_time = f"{year}-{month}-{day}"
                                self.log_api_response(f"BC-5300 Sample date from OBR[7]: {sample_time}")
                        
                        # Once we have Patient ID and Sample Time, we can break
                        if patient_id and sample_time:
                            break
                        
                    except Exception as e:
                        self.log_api_response(f"⚠️ Warning: Error parsing OBR segment: {str(e)}")
            
            # STEP 3: Build patient dict
            # Patient ID dari OBR field 4 (PENTING!)
            patient['patient_id'] = patient_id if patient_id else 'Unknown'
            
            # Sample Time dari OBR field 7 (prioritas) atau MSH field 6 (fallback)
            patient['sample_time'] = sample_time if sample_time else ''
            
            # Tambahkan patient name untuk informasi (opsional)
            if patient_name:
                patient['patient_name'] = patient_name
            
            # Create minimal results (BC-5300 tidak parse detail hasil seperti ASTM)
            results = [
                {
                    'test_name': 'Patient ID',
                    'value': patient_id if patient_id else 'Unknown',
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                },
                {
                    'test_name': 'Sample Time',
                    'value': sample_time if sample_time else 'N/A',
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                }
            ]
            
            # Tambahkan patient name jika ada
            if patient_name:
                results.append({
                    'test_name': 'Patient Name',
                    'value': patient_name,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                })
            
            # Validation log
            log_msg = f"BC-5300 parsed: Patient ID={patient['patient_id']}, Sample Time={patient['sample_time']}"
            if patient_name:
                log_msg += f", Patient Name={patient_name}"
            self.log_api_response(log_msg)
            
            return patient, results
            
        except Exception as e:
            raise ValueError(f"Error parsing BC-5300 HL7 data: {str(e)}")

    def parse_urit_8030(self, raw_data):
        """
        Parse URIT-8030 Custom HL7 format (single line dengan #VTMSH, #CR, #FS)
        Extract Patient ID dari OBR, Sample Time lengkap dari MSH (preferred), dan Results
        """
        try:
            # STEP 1: Clean markers dan normalize
            clean_data = raw_data

            # Normalize line endings
            clean_data = clean_data.replace('\r\n', '\n').replace('\r', '\n')

            # Replace the VTMSH marker with proper MSH so we can parse it
            # Important: replace '#VTMSH' first (don't remove '#VTM' alone)
            clean_data = clean_data.replace('#VTMSH', 'MSH')

            # In case some variants exist, also handle '#VTM' -> keep safe (optional)
            clean_data = clean_data.replace('#VTM', '')

            # Remove end-of-transmission marker but keep segments separated
            clean_data = clean_data.replace('#FS', '')

            # Replace #CR with newline untuk memisahkan segmen (kehilangan '#CR' prefix)
            clean_data = clean_data.replace('#CR', '\n')

            # Clean up extra whitespace and empty lines
            clean_data = '\n'.join([line.strip() for line in clean_data.split('\n') if line.strip()])

            self.log_api_response(f"URIT-8030 cleaned. Original: {len(raw_data)} bytes → Clean: {len(clean_data)} bytes")

            # STEP 2: Parse segments
            lines = clean_data.strip().split('\n')

            patient = {}
            results = []
            patient_id = None
            sample_time = None
            patient_name = None  # Simpan nama untuk informasi tambahan

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                segments = line.split('|')
                if not segments:
                    continue

                segment_type = segments[0].upper()

                # ===== MSH Segment (Message Header - Sample Time LENGKAP) =====
                if segment_type == 'MSH':
                    try:
                        # Field index 6 (0-based) holds message datetime in HL7 (YYYYMMDDHHMM[SS])
                        # Example: MSH|^~\&|urit|8030|||20251022095617||...
                        if len(segments) > 6 and segments[6].strip():
                            msg_datetime = segments[6].strip()
                            # Accept at least YYYYMMDDHHMM (12) or full YYYYMMDDHHMMSS (14)
                            if len(msg_datetime) >= 14:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                hour = msg_datetime[8:10]
                                minute = msg_datetime[10:12]
                                second = msg_datetime[12:14]
                                sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                self.log_api_response(f"URIT MSH datetime parsed: {sample_time}")
                            elif len(msg_datetime) >= 12:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                hour = msg_datetime[8:10]
                                minute = msg_datetime[10:12]
                                sample_time = f"{year}-{month}-{day} {hour}:{minute}:00"
                                self.log_api_response(f"URIT MSH datetime (no seconds) parsed: {sample_time}")
                            elif len(msg_datetime) >= 8:
                                year = msg_datetime[:4]
                                month = msg_datetime[4:6]
                                day = msg_datetime[6:8]
                                sample_time = f"{year}-{month}-{day}"
                                self.log_api_response(f"URIT MSH date parsed: {sample_time}")
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing MSH segment: {str(e)}")

                # ===== PID Segment (Patient Name - untuk informasi saja) =====
                elif segment_type == 'PID':
                    try:
                        # Field 5: Patient Name (simpan untuk referensi)
                        if len(segments) > 5 and segments[5] and segments[5].strip():
                            patient_name = segments[5].strip()
                            self.log_api_response(f"URIT Patient Name from PID[5]: {patient_name}")

                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing PID segment: {str(e)}")

                # ===== OBR Segment (Order Information - PATIENT ID ADA DI SINI) =====
                elif segment_type == 'OBR':
                    try:
                        # Field 3 adalah Patient ID / Order Number (index 3)
                        if len(segments) > 3 and segments[3].strip():
                            patient_id = segments[3].strip()
                            self.log_api_response(f"URIT Patient ID from OBR[3]: {patient_id}")

                        # Field 7: Observation Date (fallback saja jika MSH tidak memberikan datetime)
                        if len(segments) > 7 and segments[7].strip():
                            obr_date = segments[7].strip()
                            if not sample_time:
                                if len(obr_date) >= 14:
                                    year = obr_date[:4]
                                    month = obr_date[4:6]
                                    day = obr_date[6:8]
                                    hour = obr_date[8:10]
                                    minute = obr_date[10:12]
                                    second = obr_date[12:14]
                                    sample_time = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                                    self.log_api_response(f"URIT Sample time from OBR[7] (fallback): {sample_time}")
                                elif len(obr_date) >= 8:
                                    year = obr_date[:4]
                                    month = obr_date[4:6]
                                    day = obr_date[6:8]
                                    sample_time = f"{year}-{month}-{day}"
                                    self.log_api_response(f"URIT Sample date from OBR[7] (fallback): {sample_time}")

                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing OBR segment: {str(e)}")

                # ===== OBX Segment (Observation Results) =====
                elif segment_type == 'OBX' or segment_type == 'CROBX':
                    # Note: some inputs may still have CROBX if #CR replacement not perfect;
                    # so accept both 'OBX' and 'CROBX'
                    try:
                        # Field positions (HL7-like)
                        if len(segments) > 5:
                            test_name = segments[4] if len(segments) > 4 else 'Unknown Test'
                            value = segments[5] if len(segments) > 5 else ''
                            units = segments[6] if len(segments) > 6 else ''
                            ref_range = segments[7] if len(segments) > 7 else ''
                            abnormal_flag = segments[8] if len(segments) > 8 else ''

                            obs_time = ''
                            if len(segments) > 13 and segments[13].strip():
                                obs_time_raw = segments[13].strip()
                                if len(obs_time_raw) >= 14:
                                    y = obs_time_raw[:4]; mo = obs_time_raw[4:6]; d = obs_time_raw[6:8]
                                    hh = obs_time_raw[8:10]; mi = obs_time_raw[10:12]; ss = obs_time_raw[12:14]
                                    obs_time = f"{y}-{mo}-{d} {hh}:{mi}:{ss}"
                                elif len(obs_time_raw) >= 12:
                                    y = obs_time_raw[:4]; mo = obs_time_raw[4:6]; d = obs_time_raw[6:8]
                                    hh = obs_time_raw[8:10]; mi = obs_time_raw[10:12]
                                    obs_time = f"{y}-{mo}-{d} {hh}:{mi}:00"
                                else:
                                    obs_time = obs_time_raw
                                self.log_api_response(f"URIT OBX time parsed: {obs_time}")

                            if test_name and value != '':
                                results.append({
                                    'test_name': test_name,
                                    'value': value,
                                    'units': units,
                                    'reference_range': ref_range,
                                    'abnormal_flag': abnormal_flag,
                                    'observation_time': obs_time
                                })
                    except Exception as e:
                        self.log_api_response(f"Warning: Error parsing OBX segment: {str(e)}")
                else:
                    # ignore unknown segment types, but optionally log
                    pass

            # STEP 3: Assign patient data
            patient['patient_id'] = patient_id if patient_id else 'Unknown'
            patient['sample_time'] = sample_time if sample_time else ''

            if patient_name:
                patient['patient_name'] = patient_name

            # Validation log
            log_msg = f"URIT-8030 parsed: Patient ID={patient['patient_id']}, Sample Time={patient['sample_time']}, Results={len(results)}"
            if patient_name:
                log_msg += f", Patient Name={patient_name}"
            self.log_api_response(log_msg)

            return patient, results

        except Exception as e:
            raise ValueError(f"Error parsing URIT-8030 data: {str(e)}")

    def parse_astm_1394(self, raw_data):
        """Parse ASTM 1394 format data - Flexible detection"""
        try:
            # FIND position of "STXA" in data
            stxa_pos = raw_data.find("STXA")
            
            if stxa_pos == -1:
                raise ValueError("STXA marker not found in data")
            
            # Extract data starting from STXA
            # Skip "STXA" itself (4 characters)
            data_start = stxa_pos + 4
            
            # Find end position (optional - jika ada #SUB)
            sub_pos = raw_data.find("#SUB", data_start)
            if sub_pos == -1:
                sub_pos = raw_data.find("SUB", data_start)
            
            # Extract clean data
            if sub_pos != -1:
                # Ada marker SUB - ambil sampai sebelum SUB
                clean_data = raw_data[data_start:sub_pos]
            else:
                # Tidak ada SUB - ambil semua data setelah STXA
                clean_data = raw_data[data_start:]
            
            # Validate minimum length
            if len(clean_data) < 50:
                raise ValueError(f"ASTM data too short (only {len(clean_data)} chars after STXA)")
            
            # Extract patient info from ASTM fixed positions
            # Position counting starts from AFTER "STXA"
            try:
                patient_id_raw = clean_data[1:8] if len(clean_data) >= 8 else "0000000"
                patient_id = patient_id_raw.lstrip("0") or "0"  # Remove leading zeros
                
                # Extract date/time fields
                month = clean_data[9:11] if len(clean_data) >= 11 else "01"
                day = clean_data[11:13] if len(clean_data) >= 13 else "01"
                year = clean_data[13:17] if len(clean_data) >= 17 else "2025"
                hour = clean_data[17:19] if len(clean_data) >= 19 else "00"
                minute = clean_data[19:21] if len(clean_data) >= 21 else "00"
                
                test_date = f"{year}-{month}-{day}"
                test_time = f"{hour}:{minute}"
                
            except Exception as e:
                # Fallback jika extraction gagal
                patient_id = "Unknown"
                test_date = datetime.now().strftime("%Y-%m-%d")
                test_time = datetime.now().strftime("%H:%M")
                self.log_api_response(f"Warning: ASTM field extraction error: {str(e)}")
            
            # Build patient dict
            patient = {
                'first_name': 'ASTM',
                'last_name': 'Patient',
                'patient_id': patient_id,
                'dob': '',
                'sex': 'U',
                'test_date': test_date,
                'test_time': test_time
            }
            
            # Create minimal results (ASTM tidak parse histogram detail)
            results = [
                {
                    'test_name': 'Patient ID',
                    'value': patient_id,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                },
                {
                    'test_name': 'Test Date',
                    'value': test_date,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                },
                {
                    'test_name': 'Test Time',
                    'value': test_time,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                }
            ]
            
            return patient, results
                    
        except Exception as e:
            raise ValueError(f"Error parsing ASTM data: {str(e)}")

    def parse_bc1800(self, raw_data):
        """
        Parse BC-1800 ASTM format data
        Extract Patient ID dan Sample Time dari posisi fixed
        """
        try:
            # STEP 1: Find STXA marker
            stxa_pos = raw_data.find("#STXA")
            
            if stxa_pos == -1:
                stxa_pos = raw_data.find("STXA")
                if stxa_pos == -1:
                    raise ValueError("STXA marker not found in BC-1800 data")
            
            # Extract data starting after #STXA
            if raw_data[stxa_pos:stxa_pos+5] == "#STXA":
                data_start = stxa_pos + 5  # Skip "#STXA" (5 chars)
            else:
                data_start = stxa_pos + 4  # Skip "STXA" (4 chars)
            
            clean_data = raw_data[data_start:]
            
            # STEP 2: Validate minimum length
            if len(clean_data) < 33:
                raise ValueError(f"BC-1800 data too short (only {len(clean_data)} chars after STXA)")
            
            self.log_api_response(f"BC-1800 raw data after STXA (first 35 chars): [{clean_data[:35]}]")
            
            # STEP 3: Extract Patient ID - EXACT POSITIONS
            try:
                patient_id = clean_data[12:20]  # Position 12-19 (8 chars)
                
                # Validation
                if not patient_id.isdigit():
                    raise ValueError(f"Patient ID contains non-digit: {patient_id}")
                
                self.log_api_response(f"BC-1800 Patient ID: {patient_id}")
                self.log_api_response(f"   └─ Full ID block (7-19): [{clean_data[7:20]}]")
            
            except Exception as e:
                patient_id = "Unknown"
                self.log_api_response(f"BC-1800 Patient ID extraction error: {str(e)}")
            
            # STEP 4: Extract Sample Time - EXACT POSITIONS
            
            try:
                # Extract datetime components from exact positions
                mmdd = clean_data[21:25]  # Position 21-24 → "1023"
                yyyy = clean_data[25:29]  # Position 25-28 → "2025"
                hhmm = clean_data[29:33]  # Position 29-32 → "0712"
                
                # Break down components
                month = mmdd[0:2]   # "10"
                day = mmdd[2:4]     # "23"
                year = yyyy         # "2025"
                hour = hhmm[0:2]    # "07"
                minute = hhmm[2:4]  # "12"
                
                # Validate all components are digits
                if not all([month.isdigit(), day.isdigit(), year.isdigit(), 
                        hour.isdigit(), minute.isdigit()]):
                    raise ValueError("Invalid date/time components (non-digit found)")
                
                # Validate ranges
                if not (1 <= int(month) <= 12):
                    raise ValueError(f"Invalid month: {month}")
                if not (1 <= int(day) <= 31):
                    raise ValueError(f"Invalid day: {day}")
                if not (0 <= int(hour) <= 23):
                    raise ValueError(f"Invalid hour: {hour}")
                if not (0 <= int(minute) <= 59):
                    raise ValueError(f"Invalid minute: {minute}")
                
                # Build sample_time
                sample_time = f"{year}-{month}-{day} {hour}:{minute}:00"
                
                self.log_api_response(f"BC-1800 Sample Time: {sample_time}")
                self.log_api_response(f"   └─ DateTime block (20-32): [{clean_data[20:33]}]")
                self.log_api_response(f"   └─ MMDD: {mmdd}, YYYY: {yyyy}, HHMM: {hhmm}")
                self.log_api_response(f"   └─ Components: Month={month}, Day={day}, Year={year}, Hour={hour}, Minute={minute}")
            
            except Exception as e:
                sample_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_api_response(f"BC-1800 Sample Time extraction error: {str(e)}, using current time")
            
            # STEP 5: Build patient dict
            patient = {
                'patient_id': patient_id,
                'sample_time': sample_time,
                'first_name': 'BC1800',
                'last_name': 'Patient',
                'dob': '',
                'sex': 'U'
            }
            
            # STEP 6: Create minimal results
            results = [
                {
                    'test_name': 'Patient ID',
                    'value': patient_id,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                },
                {
                    'test_name': 'Sample Time',
                    'value': sample_time,
                    'units': '',
                    'reference_range': '',
                    'abnormal_flag': ''
                }
            ]
            
            self.log_api_response(f"BC-1800 FINAL RESULT: Patient ID={patient_id}, Sample Time={sample_time}")
            
            return patient, results
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            raise ValueError(f"Error parsing BC-1800 data: {str(e)}\n{error_detail}")

    def parse_data_auto(self, data):
        """Auto-detect format and parse accordingly"""
        try:
            # Detect format
            data_format = self.detect_data_format(data)
            
            if data_format == "BC1800":
                self.log_api_response("Detected: BC-1800 Hematology Analyzer format")
                return self.parse_bc1800(data)
            
            elif data_format == "URIT_8030":
                self.log_api_response("Detected: URIT-8030 Chemistry Analyzer format")
                return self.parse_urit_8030(data)
            
            elif data_format == "BC5300_HL7":
                self.log_api_response("Detected: BC-5300 Custom HL7 format")
                return self.parse_bc5300_hl7(data)
            
            elif data_format == "CUSTOM_HL7":
                self.log_api_response("Detected: Generic Custom HL7 format (with markers)")
                return self.parse_custom_hl7(data)
            
            elif data_format == "ASTM":
                self.log_api_response("Detected: ASTM 1394 format")
                return self.parse_astm_1394(data)
            
            else:
                self.log_api_response("Detected: Standard HL7 format")
                return self.parse_hl7(data)
                
        except Exception as e:
            # Fallback chain
            try:
                self.log_api_response("Trying BC-1800 format as fallback")
                return self.parse_bc1800(data)
            except:
                try:
                    self.log_api_response("Trying URIT-8030 format as fallback")
                    return self.parse_urit_8030(data)
                except:
                    try:
                        self.log_api_response("Trying generic Custom HL7 format as fallback")
                        return self.parse_custom_hl7(data)
                    except:
                        try:
                            self.log_api_response("Trying standard HL7 format as final fallback")
                            return self.parse_hl7(data)
                        except:
                            raise ValueError(f"Failed to parse data: {str(e)}")

    def parse_data(self):
        """Parse HL7/Custom HL7/BC-5300/URIT-8030/BC-1800/ASTM data and display results"""
        try:
            if not self.current_file_path:
                messagebox.showwarning("Warning", "Please select a file first")
                return
                
            hl7_data = self.hl7_text.get(1.0, tk.END)
            if not hl7_data.strip():
                messagebox.showwarning("Warning", "No data found in the selected file")
                return
            
            # Auto-detect and parse
            data_format = self.detect_data_format(hl7_data)
            self.patient, self.results = self.parse_data_auto(hl7_data)
            
            # Map format for display
            format_display = {
                "BC1800": "BC-1800",
                "URIT_8030": "URIT-8030",
                "BC5300_HL7": "BC-5300 HL7",
                "CUSTOM_HL7": "Custom HL7",
                "HL7": "HL7",
                "ASTM": "ASTM"
            }.get(data_format, data_format)
            
            # Save format
            self.current_data_format = data_format
            
            # Device source for file import
            device_source = "Manual File Import"
            
            # Display patient info with context
            self.update_results_display_with_context(
                patient=self.patient,
                results=self.results,
                data_format=format_display,
                device_source=device_source
            )
            
            self.update_status(f"Parsed successfully ({format_display}) - Patient data ready")

            # Auto-save using existing save_to_database()
            try:
                threading.Thread(target=self.save_to_database, daemon=True).start()
                self.update_status("Auto-save started for file data")
            except Exception as e:
                self.update_status(f"Auto-save error (file): {e}")
            
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse data: {str(e)}")
            self.update_status("Parse failed")

    def is_complete_message(self, data):
        """
        Universal message completeness detection - IMPROVED VERSION
        Returns: (is_complete: bool, format_type: str)
        """
        data = data.strip()
        data_upper = data.upper()
        
        # ===== CHECK 1: BC-1800 Format =====
        if "#STXAAAI" in data or "STXAAAI" in data:
            # BC-1800 complete if has end marker or large enough
            if "#SUB" in data or "SUB" in data:
                return True, "BC1800"
            if len(data) > 1500:  # BC-1800 data biasanya panjang
                return True, "BC1800"
            return False, "BC1800"
        
        # ===== CHECK 2: Generic ASTM Format =====
        if "STXA" in data and "#STXAAAI" not in data:
            stxa_pos = data.find("STXA")
            data_after_stxa = data[stxa_pos + 4:]
            
            if "#SUB" in data_after_stxa or "SUB" in data_after_stxa:
                return True, "ASTM"
            if len(data_after_stxa) > 100:
                return True, "ASTM"
            
            return False, "ASTM"
        
        # ===== CHECK 3: URIT-8030 Format =====
        has_urit = any([
            "#VTM" in data and ("urit" in data.lower() or "8030" in data),
            "#VTMSH" in data and ("urit" in data.lower() or "8030" in data),
            "MSH" in data and "urit" in data.lower() and "8030" in data
        ])
        
        if has_urit:
            # FIX: Check for OBX segments as completion indicator
            if data.endswith("#FS#CR") or data.endswith("#CR#FS") or "#FS#CR" in data:
                return True, "URIT_8030"
        
            # NEW: Check if has multiple OBX segments (likely complete)
            obx_count = data.count("OBX|")
            if obx_count >= 2:  # At least 2 OBX segments = complete
                return True, "URIT_8030"
            
            # Check end patterns without markers
            if data.endswith("||") and "OBX|" in data:
                return True, "URIT_8030"
            
            if len(data) > 2000:
                self.log_multi_serial(f"URIT-8030 data unusually large ({len(data)} bytes) - forcing process")
                return True, "URIT_8030"
            
            return False, "URIT_8030"
        
        # ===== CHECK 4: BC-5300 Format =====
        has_bc5300 = any([
            "#VTM" in data and ("BC-5300" in data_upper or "BC5300" in data_upper),
            "#VTMSH" in data and ("BC-5300" in data_upper or "BC5300" in data_upper),
            "#VTM" in data and "MINDRAY" in data_upper,
            "#VTMSH" in data and "MINDRAY" in data_upper
        ])
        
        if has_bc5300:
            # FIX: More flexible end detection
            if data.endswith("#FS#CR") or data.endswith("#CR#FS") or "#FS#CR" in data:
                return True, "BC5300_HL7"
            
            # NEW: Check if has multiple OBX segments
            obx_count = data.count("OBX|") + data.count("CROBX|")
            if obx_count >= 5:  # BC-5300 usually has many results
                return True, "BC5300_HL7"
            
            # Check patterns
            if data.endswith("#CR") and "CROBX|" in data:
                return True, "BC5300_HL7"
            
            if len(data) > 3000:
                self.log_multi_serial(f"BC-5300 data unusually large ({len(data)} bytes) - forcing process")
                return True, "BC5300_HL7"
            
            return False, "BC5300_HL7"
        
        # ===== CHECK 5: Generic Custom HL7 (with control markers) =====
        has_custom_markers = any([
            "#VTM" in data,
            "#VTMSH" in data,
            "#CR" in data and ("MSH" in data or "OBX" in data)
        ])
        
        if has_custom_markers:
            if "#FS" in data or "#FS#CR" in data:
                return True, "CUSTOM_HL7"
            
            # NEW: Check OBX count
            obx_count = data.count("OBX|")
            if obx_count >= 3:
                return True, "CUSTOM_HL7"
            
            if len(data) > 500:
                return True, "CUSTOM_HL7"
            
            return False, "CUSTOM_HL7"
        
        # ===== CHECK 6: Standard HL7 =====
        if "MSH" in data:
            # FIX: More robust completion detection
            has_obr = "OBR|" in data
            has_obx = "OBX|" in data
            
            if has_obr and has_obx:
                # Count OBX segments
                obx_count = data.count("OBX|")
                
                # If has multiple OBX, likely complete
                if obx_count >= 2:
                    return True, "HL7"
                
                # If ends with || pattern, likely complete
                if data.endswith("||"):
                    return True, "HL7"
                
                # If large enough with content
                if len(data) > 300:
                    return True, "HL7"
            
            # Fallback for short messages
            if len(data) > 200:
                return True, "HL7"
            
            return False, "HL7"
        
        # ===== FALLBACK: Force process if too large =====
        if len(data) > 2000:
            self.log_multi_serial(f"Unknown format, data too large ({len(data)} bytes) - forcing process")
            return True, "UNKNOWN"
        
        return False, "UNKNOWN"
    
    def parse_data_universal(self, raw_data):
        """
        Universal parser that automatically selects the right parser
        """
        data_format = self.detect_data_format(raw_data)
        
        # Map format to parser method
        parser_map = {
            "URIT_8030": self.parse_urit_8030,
            "BC5300_HL7": self.parse_bc5300_hl7,
            "CUSTOM_HL7": self.parse_custom_hl7,
            "ASTM": self.parse_astm_1394,
            "HL7": self.parse_hl7
        }
        
        # Get parser
        parser_func = parser_map.get(data_format)
        
        if parser_func:
            try:
                return parser_func(raw_data)
            except Exception as e:
                self.log_multi_serial(f"Primary parser failed for {data_format}: {str(e)}")
                # Try fallback
                return self.parse_with_fallback(raw_data)
        else:
            return self.parse_with_fallback(raw_data)

    def parse_with_fallback(self, raw_data):
        """
        Fallback parser chain when primary detection fails
        """
        parsers = [
            ("URIT-8030", self.parse_urit_8030),
            ("BC-5300", self.parse_bc5300_hl7),
            ("Custom HL7", self.parse_custom_hl7),
            ("Standard HL7", self.parse_hl7),
            ("ASTM", self.parse_astm_1394)
        ]
        
        for name, parser in parsers:
            try:
                self.log_multi_serial(f"Trying {name} parser...")
                patient, results = parser(raw_data)
                if patient.get('patient_id') and patient['patient_id'] != 'Unknown':
                    self.log_multi_serial(f"Success with {name} parser")
                    return patient, results
            except Exception as e:
                continue
        
        raise ValueError("All parsers failed to parse data")
    
# 6. ===SETTING MENU KONEKSI DATABASE===
    def update_config(self):
        """Update database configuration"""
        self.db_config = {
            'host': self.host_entry.get(),
            'database': self.db_entry.get(),
            'user': self.user_entry.get(),
            'password': self.pass_entry.get(),
        }
        self.update_status("Database configuration updated")

        # Auto-save if enabled
        if self.auto_startup_enabled:
            self.save_app_configuration()
        
    def test_connection(self):
        """Test database connection"""
        def test_conn():
            try:
                self.update_config()
                conn = psycopg2.connect(**self.db_config)
                conn.close()
                self.conn_status.configure(text="✓ Connection successful", fg='#27ae60')
                self.update_status("Database connection test successful")
            except Exception as e:
                self.conn_status.configure(text=f"✗ Connection failed: {str(e)}", fg='#e74c3c')
                self.update_status("Database connection test failed")
        
        # Run in thread to prevent GUI freezing
        threading.Thread(target=test_conn, daemon=True).start()
        self.conn_status.configure(text="Testing connection...", fg='#f39c12')

    def save_to_database_with_context(self, patient, results, data_format, 
                                        device_type, device_identifier, device_label):
            """
            Save data to database with explicit device context
            This ensures correct device assignment even with concurrent operations
            """
            def save_data():
                try:
                    self.update_config()
                    conn = psycopg2.connect(**self.db_config)
                    cur = conn.cursor()
                    
                    # Get or create device with explicit parameters
                    cur.execute("""
                        SELECT get_or_create_device(
                            %s::VARCHAR, 
                            %s::VARCHAR, 
                            %s::VARCHAR
                        )
                    """, (device_label, device_type, device_identifier))
                    
                    device_id = cur.fetchone()[0]
                    
                    # Parse sample time
                    sample_time = patient.get('sample_time', '').strip()
                    if sample_time:
                        try:
                            sample_time_dt = datetime.strptime(sample_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            try:
                                sample_time_dt = datetime.strptime(sample_time, "%Y-%m-%d")
                            except ValueError:
                                sample_time_dt = datetime.now()
                    else:
                        sample_time_dt = datetime.now()
                    
                    # Insert test record
                    patient_id = patient.get('patient_id', 'Unknown')
                    total_results = len(results) if data_format in ["HL7", "CUSTOM_HL7", "URIT_8030"] else 0
                    
                    cur.execute("""
                        INSERT INTO test_records 
                        (device_id, patient_id, sample_time, data_format, total_results)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING record_id
                    """, (device_id, patient_id, sample_time_dt, data_format, total_results))
                    
                    record_id = cur.fetchone()[0]
                    
                    # Insert test results
                    if data_format in ["HL7", "CUSTOM_HL7", "URIT_8030"] and len(results) > 0:
                        for r in results:
                            abnormal_flag = r.get('abnormal_flag', '').strip()
                            cur.execute("""
                                INSERT INTO test_results
                                (record_id, test_name, test_value, test_units, 
                                reference_range, abnormal_flag)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                record_id,
                                r.get('test_name', ''),
                                r.get('value', ''),
                                r.get('units', ''),
                                r.get('reference_range', ''),
                                abnormal_flag if abnormal_flag else None
                            ))
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    # Success message
                    success_msg = f"[{device_identifier}] Saved to DB | Record #{record_id} | Device: {device_label}"
                    if data_format in ["HL7", "CUSTOM_HL7", "URIT_8030"]:
                        success_msg += f" | Tests: {len(results)}"
                    
                    self.root.after(0, lambda msg=success_msg: self.log_multi_serial(msg))
                    self.root.after(0, lambda msg=success_msg: self.log_socket_message(msg))
                    
                except Exception as e:
                    import traceback
                    error_msg = f"❌ Database save failed: {str(e)}"
                    self.root.after(0, lambda msg=error_msg: self.log_multi_serial(msg))
                    print(traceback.format_exc())
            
            # Run in background thread
            threading.Thread(target=save_data, daemon=True).start()

    def save_to_database(self):
        """
        Save parsed data to database - MODIFIED with auto device detection fallback
        This version is for manual file input and backward compatibility
        """
        if not hasattr(self, 'patient') or not hasattr(self, 'results'):
            messagebox.showwarning("Warning", "Please parse data first")
            return
        
        data_format = getattr(self, 'current_data_format', 'HL7')
        
        # ===== AUTO-DETECT DEVICE SOURCE =====
        device_type = None
        device_identifier = None
        device_label = None
        
        # Priority 1: Socket
        if hasattr(self, 'current_socket_ip') and self.current_socket_ip:
            device_type = 'socket'
            device_identifier = self.current_socket_ip
            device_label = self.device_labels["socket"].get(
                device_identifier, 
                f"Unlabeled Socket ({device_identifier})"
            )
        
        # Priority 2: Serial
        elif hasattr(self, 'current_serial_port') and self.current_serial_port:
            device_type = 'serial'
            device_identifier = self.current_serial_port
            device_label = self.device_labels["serial"].get(
                device_identifier, 
                f"Unlabeled Serial ({device_identifier})"
            )
        
        # Priority 3: File import
        else:
            device_type = 'file'
            device_identifier = 'manual_import'
            device_label = 'Manual File Import'
        
        # Use the context-aware version
        self.save_to_database_with_context(
            patient=self.patient,
            results=self.results,
            data_format=data_format,
            device_type=device_type,
            device_identifier=device_identifier,
            device_label=device_label
        )

# 7. ===SETTING SOCKET SERVER METHODS===
    def update_socket_config(self):
        """Update socket configuration"""
        try:
            self.socket_config = {
                'host': self.socket_host_entry.get(),
                'port': int(self.socket_port_entry.get()),
                'buffer_size': int(self.socket_buffer_entry.get())
            }
            self.log_socket_message("Socket configuration updated")
            messagebox.showinfo("Success", "Socket configuration updated successfully!")

            # Auto-save if enabled
            if self.auto_startup_enabled:
                self.save_app_configuration()
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid configuration values: {str(e)}")
    
    def start_socket_server(self):
        """Start socket server to listen for HL7 data"""
        if self.socket_running:
            messagebox.showwarning("Warning", "Socket server is already running!")
            return
            
        def run_server():
            try:
                self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket_server.bind((self.socket_config['host'], self.socket_config['port']))
                self.socket_server.listen(5)
                
                self.socket_running = True
                
                # Update UI in main thread
                self.root.after(0, lambda: self.socket_status_label.configure(
                    text=f"Server Status: Running on {self.socket_config['host']}:{self.socket_config['port']}", 
                    fg='#27ae60'
                ))
                self.root.after(0, lambda: self.start_socket_btn.configure(state=tk.DISABLED))
                self.root.after(0, lambda: self.stop_socket_btn.configure(state=tk.NORMAL))
                
                self.root.after(0, lambda: self.log_socket_message(
                    f"Socket server started on {self.socket_config['host']}:{self.socket_config['port']}"
                ))
                
                while self.socket_running:
                    try:
                        client_socket, address = self.socket_server.accept()
                        self.root.after(0, lambda addr=address: self.log_socket_message(
                            f"Connection established from {addr[0]}:{addr[1]}"
                        ))
                        
                        # Handle client in separate thread
                        client_thread = threading.Thread(
                            target=self.handle_client, 
                            args=(client_socket, address),
                            daemon=True
                        )
                        client_thread.start()
                        
                    except socket.error as e:
                        if self.socket_running:
                            self.root.after(0, lambda: self.log_socket_message(f"Socket error: {str(e)}"))
                        break
                        
            except Exception as e:
                self.socket_running = False
                self.root.after(0, lambda: messagebox.showerror("Socket Error", f"Failed to start server: {str(e)}"))
                self.root.after(0, lambda: self.socket_status_label.configure(
                    text="Server Status: Error", 
                    fg='#e74c3c'
                ))
        
        # Run server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

    def handle_client(self, client_socket, address):
        """Handle individual client connections - WITH TIMEOUT FALLBACK"""
        client_ip = address[0]
        self.auto_register_socket_device(client_ip)
        
        device_label = self.device_labels["socket"].get(client_ip, "Unlabeled Device")
        self.log_socket_message(f"Connection from {client_ip} ({device_label})")
        
        try:
            with client_socket:
                # Send initial ACK
                try:
                    initial_ack = "<ACK>\n"
                    client_socket.send(initial_ack.encode('utf-8'))
                    self.root.after(0, lambda: self.log_socket_message(
                        f"Initial ACK sent to {client_ip}"
                    ))
                except Exception as e:
                    self.root.after(0, lambda: self.log_socket_message(
                        f"Failed to send initial ACK to {client_ip}: {str(e)}"
                    ))
                
                data_buffer = ""
                last_data_time = time.time()  # NEW: Track last data received
                
                while self.socket_running:
                    data = client_socket.recv(self.socket_config['buffer_size'])
                    if not data:
                        break
                    
                    received_data = data.decode('utf-8', errors='ignore')
                    data_buffer += received_data
                    last_data_time = time.time()  # Update timestamp
                    
                    self.root.after(0, lambda size=len(received_data): self.log_socket_message(
                        f"Chunk received from {client_ip} ({size} bytes)"
                    ))
                    
                    # Check if message complete
                    is_complete, detected_format = self.is_complete_message(data_buffer)
                    
                    # NEW: Timeout fallback - process if no data for 2 seconds
                    time_since_last_data = time.time() - last_data_time
                    force_process = (
                        len(data_buffer) > 100 and 
                        time_since_last_data > 2.0 and
                        ("MSH" in data_buffer or "OBX" in data_buffer or "STXA" in data_buffer)
                    )
                    
                    if is_complete or force_process:
                        complete_data = data_buffer.strip()
                        data_buffer = ""
                        
                        if force_process:
                            self.root.after(0, lambda size=len(complete_data): 
                                self.log_socket_message(
                                    f"Timeout-based completion from {client_ip} ({size} bytes)"
                                )
                            )
                        else:
                            self.root.after(0, lambda size=len(complete_data): 
                                self.log_socket_message(
                                    f"Complete message from {client_ip} ({size} bytes)"
                                )
                            )
                        
                        # Display received data
                        self.root.after(0, lambda data=complete_data: 
                            self.display_received_data(data))
                        
                        # Process with device context (thread-safe)
                        threading.Thread(
                            target=self.process_and_save_with_context,
                            args=(complete_data, 'socket', client_ip),
                            daemon=True
                        ).start()
                        
                        # Send ACK
                        try:
                            ack = "<ACK>\n"
                            client_socket.send(ack.encode('utf-8'))
                            self.root.after(0, lambda: self.log_socket_message(
                                f"ACK sent to {client_ip}"
                            ))
                        except Exception as e:
                            self.root.after(0, lambda: self.log_socket_message(
                                f"Failed to send ACK: {str(e)}"
                            ))
                        
                        # Reset timer after processing
                        last_data_time = time.time()
        
        except Exception as e:
            self.root.after(0, lambda: self.log_socket_message(
                f"Client handling error for {client_ip}: {str(e)}"
            ))
        finally:
            self.root.after(0, lambda: self.log_socket_message(
                f"Connection closed for {client_ip}"
            ))

    def stop_socket_server(self):
        """Stop socket server"""
        if not self.socket_running:
            messagebox.showinfo("Info", "Socket server is not running!")
            return
        
        self.socket_running = False
        
        if self.socket_server:
            try:
                self.socket_server.close()
            except:
                pass
        
        # Update UI
        self.socket_status_label.configure(text="Server Status: Stopped", fg='#e74c3c')
        self.start_socket_btn.configure(state=tk.NORMAL)
        self.stop_socket_btn.configure(state=tk.DISABLED)
        self.log_socket_message("Socket server stopped")
    
    def log_socket_message(self, message):
        """Add message to socket log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.socket_log.configure(state=tk.NORMAL)
        self.socket_log.insert(tk.END, log_entry)
        self.socket_log.see(tk.END)
        self.socket_log.configure(state=tk.DISABLED)
    
    def display_received_data(self, data):
        """Display received HL7 data"""
        self.received_data_text.configure(state=tk.NORMAL)
        self.received_data_text.delete(1.0, tk.END)
        self.received_data_text.insert(1.0, data)
        self.received_data_text.configure(state=tk.DISABLED)
        
        # Enable parse button
        # self.parse_socket_btn.configure(state=tk.NORMAL)

    def parse_socket_data(self):
        """Parse received socket HL7/ASTM data - MODIFIED to use context"""
        try:
            socket_data = self.received_data_text.get(1.0, tk.END)
            if not socket_data.strip():
                messagebox.showwarning("Warning", "No socket data to parse")
                return
            
            # Detect device
            device_ip = getattr(self, 'current_socket_ip', 'Unknown IP')
            device_label = self.device_labels["socket"].get(device_ip, f"Unlabeled Socket ({device_ip})")
            
            self.log_socket_message(f"Processing socket data from {device_label}...")
            
            # Process with context
            threading.Thread(
                target=self.process_and_save_with_context,
                args=(socket_data, 'socket', device_ip),
                daemon=True
            ).start()
            
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse socket data: {str(e)}")
            self.log_socket_message(f"Parse error: {str(e)}")

    def process_and_save_with_context(self, raw_data, device_type, device_identifier):
            """
            Process and save data with explicit device context
            This prevents race conditions when multiple devices send data simultaneously
            
            Args:
                raw_data: Raw HL7/ASTM data string
                device_type: 'socket' or 'serial'
                device_identifier: IP address for socket, port name for serial
            """
            try:
                # Get device label
                device_label = self.device_labels[device_type].get(
                    device_identifier, 
                    f"Unlabeled {device_type.capitalize()} ({device_identifier})"
                )
                
                self.log_multi_serial(f"[{device_identifier}] Starting processing...")
                
                # STEP 1: Parse data
                data_format = self.detect_data_format(raw_data)
                patient, results = self.parse_data_auto(raw_data)
                
                # Map format for display
                format_display = {
                    "BC1800": "BC-1800",
                    "URIT_8030": "URIT-8030",
                    "BC5300_HL7": "BC-5300 HL7",
                    "CUSTOM_HL7": "Custom HL7",
                    "HL7": "HL7",
                    "ASTM": "ASTM"
                }.get(data_format, data_format)
                
                self.log_multi_serial(
                    f"[{device_identifier}] Parsed as {format_display} | "
                    f"Patient: {patient.get('patient_id', 'Unknown')}"
                )
                
                # STEP 2: Save to database with explicit device context
                self.save_to_database_with_context(
                    patient=patient,
                    results=results,
                    data_format=data_format,
                    device_type=device_type,
                    device_identifier=device_identifier,
                    device_label=device_label
                )
                
                # STEP 3: Update UI display (thread-safe)
                device_source = f"{device_label} ({device_identifier})"
                self.root.after(0, lambda: self.update_results_display_with_context(
                    patient=patient,
                    results=results,
                    data_format=format_display,
                    device_source=device_source
                ))
                
                self.log_multi_serial(
                    f"[{device_identifier}] Processing complete | "
                    f"Device: {device_label} | Format: {format_display}"
                )
                
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                self.log_multi_serial(
                    f"[{device_identifier}] Processing error:\n{error_detail}"
                )
    
    # BARU
    def auto_parse_and_save(self, raw_data):
        """Automatically detect, parse, and save HL7 or ASTM data"""
        try:
            raw_data = raw_data.strip()
            if not raw_data:
                return
            
            # Deteksi format data (gunakan method yang sudah diupdate)
            data_format = self.detect_data_format(raw_data)
            
            if data_format == "HL7":
                self.log_serial_message("Detected HL7 format - parsing...")
                self.patient, self.results = self.parse_hl7(raw_data)
                self.current_data_format = "HL7"
                
            elif data_format == "ASTM":
                self.log_serial_message("Detected ASTM format - parsing...")
                self.patient, self.results = self.parse_astm_1394(raw_data)
                self.current_data_format = "ASTM"
                
            else:
                self.log_serial_message("Unknown data format, skipping parse.")
                return
            
            # Update Results display
            self.root.after(0, lambda: self.update_results_display())
            
            # Auto-save ke database
            self.save_to_database()
            self.log_serial_message(f"✓ {data_format} data saved to database successfully")
            
        except Exception as e:
            self.log_serial_message(f"✗ Auto parse/save error: {str(e)}")

    
    def save_socket_to_database(self):
        """Save parsed socket data to database"""
        if not hasattr(self, 'patient') or not hasattr(self, 'results'):
            messagebox.showwarning("Warning", "Please parse socket data first")
            return
        
        # Use the same save logic as file input
        self.save_to_database()
        self.log_socket_message("Socket data saved to database")
    
    def clear_socket_log(self):
        """Clear socket connection log"""
        self.socket_log.configure(state=tk.NORMAL)
        self.socket_log.delete(1.0, tk.END)
        self.socket_log.configure(state=tk.DISABLED)
        self.log_socket_message("Log cleared")
    
    def clear_received_data(self):
        """Clear received HL7 data and results"""
        # Clear received data display
        self.received_data_text.configure(state=tk.NORMAL)
        self.received_data_text.delete(1.0, tk.END)
        self.received_data_text.configure(state=tk.DISABLED)
        
        # Clear results in Results tab
        self.clear_results_tab()
        
        # Disable parse and save buttons
        self.parse_socket_btn.configure(state=tk.DISABLED)
        self.save_socket_btn.configure(state=tk.DISABLED)
        
        # Clear stored data
        if hasattr(self, 'patient'):
            delattr(self, 'patient')
        if hasattr(self, 'results'):
            delattr(self, 'results')
        
        self.log_socket_message("Received data cleared")
        
        self.update_status("File content cleared - Please select an HL7 file")
    
# 8. ===SETTING RESULTS TAB MENU
    def clear_results_tab(self):
        """Clear all content in Results tab"""
        # Clear patient info
        self.patient_info.delete(1.0, tk.END)
        
        # Clear results tree
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

    def update_results_display_with_context(self, patient, results, data_format, device_source):
            """
            Update Results tab display with explicit context
            Thread-safe update to prevent UI corruption
            """
            try:
                # Clear patient info
                self.patient_info.delete(1.0, tk.END)
                
                # Build patient info text
                patient_text = f"Device Source: {device_source}\n"
                patient_text += f"Patient ID: {patient.get('patient_id', 'N/A')}\n"
                
                # Sample time
                sample_time = patient.get('sample_time', '').strip()
                if sample_time:
                    patient_text += f"Sample Time: {sample_time}\n"
                
                # Total results (only for specific formats)
                if data_format in ["HL7", "Custom HL7", "URIT-8030"]:
                    patient_text += f"Total Results: {len(results)}"
                
                self.patient_info.insert(1.0, patient_text)
                
                # Clear and populate results tree
                for item in self.results_tree.get_children():
                    self.results_tree.delete(item)
                
                # Only show results for HL7-based formats
                if data_format in ["HL7", "Custom HL7", "URIT-8030"]:
                    for result in results:
                        flag = result.get('abnormal_flag', '').strip()
                        display_flag = 'Normal' if flag.upper() in ['NORMAL', 'N', ''] else flag
                        
                        self.results_tree.insert('', tk.END, values=(
                            result['test_name'],
                            result['value'],
                            result['units'],
                            result['reference_range'],
                            display_flag
                        ))
                    
                    # Color code abnormal results
                    for child in self.results_tree.get_children():
                        item = self.results_tree.item(child)
                        if item['values'][4] not in ['Normal', '']:
                            self.results_tree.item(child, tags=('abnormal',))
                    
                    self.results_tree.tag_configure('abnormal', background='#ffebee')
                
                self.update_status(f"Results updated: {device_source} - {data_format}")
                
            except Exception as e:
                self.log_multi_serial(f"UI update error: {str(e)}")

    def update_results_display(self):
        """Update results display in Results tab - DEPRECATED, use display_patient_info_with_device instead"""
        # Untuk backward compatibility, gunakan fungsi baru
        device_source = "Unknown Device"
        data_format = getattr(self, 'current_data_format', 'HL7')
        
        format_display = {
            "BC1800": "BC-1800",
            "URIT_8030": "URIT-8030",
            "BC5300_HL7": "BC-5300 HL7",
            "CUSTOM_HL7": "Custom HL7",
            "HL7": "HL7",
            "ASTM": "ASTM"
        }.get(data_format, data_format)
        
        self.display_patient_info_with_device(device_source, format_display)
        self.update_results_tree()

    def update_results_tree(self):
        """Update results tree view"""
        # Clear results tree
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Populate results (only for specific formats)
        data_format = getattr(self, 'current_data_format', 'HL7')
        if data_format in ["HL7", "CUSTOM_HL7", "URIT_8030"]:
            for result in self.results:
                abnormal_flag = result.get('abnormal_flag', '').strip()
                
                if abnormal_flag.upper() in ['NORMAL', 'N', '']:
                    display_flag = 'Normal'
                else:
                    display_flag = abnormal_flag
                
                self.results_tree.insert('', tk.END, values=(
                    result['test_name'],
                    result['value'],
                    result['units'],
                    result['reference_range'],
                    display_flag
                ))
            
            # Color code abnormal results
            for child in self.results_tree.get_children():
                item = self.results_tree.item(child)
                flag_value = item['values'][4]
                if flag_value.upper() not in ['NORMAL', 'N', '']:
                    self.results_tree.item(child, tags=('abnormal',))
            
            self.results_tree.tag_configure('abnormal', background='#ffebee')

    # SETTING MENU UP 
    def show_socket_settings(self):
        """Show socket settings dialog"""
        self.notebook.select(1)  # Switch to socket tab
    
    def show_api_settings(self):
        """Show API settings dialog"""
        self.notebook.select(4)  # Switch to API tab
    
    def show_about(self):
        """Show about dialog"""
        about_text = """Data Parser & LIMS Simulation
Version 2.0

Features:
• File-based HL7 parsing
• Real-time socket connection for laboratory instruments
• PostgreSQL database integration
• API integration for external systems
• Results visualization and management

Developed for Laboratory Information Management System (LIMS)
        """
        messagebox.showinfo("About", about_text)

# 9. ===SETTING KONEKSI DAN LOGIKA PORT===
    def refresh_all_ports(self):
        """Refresh list of available serial ports"""
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        self.log_multi_serial(f"Found {len(available_ports)} available ports: {', '.join(available_ports) if available_ports else 'None'}")
        messagebox.showinfo("Refresh Ports", f"Found {len(available_ports)} available serial ports:\n\n" + "\n".join(available_ports) if available_ports else "No ports found")

    def add_port_connection(self):
            """Add new port connection dialog"""
            dialog = tk.Toplevel(self.root)
            dialog.title("Add Serial Port Connection")
            dialog.geometry("500x400")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Center dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
            y = (dialog.winfo_screenheight() // 2) - (400 // 2)
            dialog.geometry(f"500x400+{x}+{y}")
            
            # Configuration frame
            config_frame = ttk.LabelFrame(dialog, text="Port Configuration", padding=15)
            config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Port selection
            ttk.Label(config_frame, text="Select Port:").grid(row=0, column=0, sticky='w', pady=5, padx=5)
            
            available_ports = [port.device for port in serial.tools.list_ports.comports()]
            port_var = tk.StringVar()
            port_combo = ttk.Combobox(config_frame, textvariable=port_var, values=available_ports, width=20)
            port_combo.grid(row=0, column=1, pady=5, padx=5, sticky='ew')
            if available_ports:
                port_combo.current(0)
            
            # Baudrate
            ttk.Label(config_frame, text="Baudrate:").grid(row=1, column=0, sticky='w', pady=5, padx=5)
            baudrate_var = tk.StringVar(value='9600')
            ttk.Combobox(config_frame, textvariable=baudrate_var, 
                        values=['9600', '19200', '38400', '57600', '115200'], 
                        width=20, state='readonly').grid(row=1, column=1, pady=5, padx=5, sticky='ew')
            
            # Data bits
            ttk.Label(config_frame, text="Data Bits:").grid(row=2, column=0, sticky='w', pady=5, padx=5)
            databits_var = tk.StringVar(value='8')
            ttk.Combobox(config_frame, textvariable=databits_var,
                        values=['5', '6', '7', '8'], width=20, state='readonly').grid(row=2, column=1, pady=5, padx=5, sticky='ew')
            
            # Parity
            ttk.Label(config_frame, text="Parity:").grid(row=3, column=0, sticky='w', pady=5, padx=5)
            parity_var = tk.StringVar(value='N')
            ttk.Combobox(config_frame, textvariable=parity_var,
                        values=['N', 'E', 'O', 'M', 'S'], width=20, state='readonly').grid(row=3, column=1, pady=5, padx=5, sticky='ew')
            
            # Stop bits
            ttk.Label(config_frame, text="Stop Bits:").grid(row=4, column=0, sticky='w', pady=5, padx=5)
            stopbits_var = tk.StringVar(value='1')
            ttk.Combobox(config_frame, textvariable=stopbits_var,
                        values=['1', '1.5', '2'], width=20, state='readonly').grid(row=4, column=1, pady=5, padx=5, sticky='ew')
            
            # Timeout
            ttk.Label(config_frame, text="Timeout (seconds):").grid(row=5, column=0, sticky='w', pady=5, padx=5)
            timeout_var = tk.StringVar(value='3')
            ttk.Entry(config_frame, textvariable=timeout_var, width=22).grid(row=5, column=1, pady=5, padx=5, sticky='ew')
            
            config_frame.grid_columnconfigure(1, weight=1)
            
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
                        'bytesize': int(databits_var.get()),
                        'parity': parity_var.get(),
                        'stopbits': float(stopbits_var.get()),
                        'timeout': float(timeout_var.get())
                    }
                    
                    self.serial_running[port_name] = False
                    self.update_ports_display()
                    self.log_multi_serial(f"Port {port_name} configured successfully")

                     # ✅ Auto-save if enabled
                    if self.auto_startup_enabled:
                        self.save_app_configuration()
                    dialog.destroy()
                    
                except ValueError as e:
                    messagebox.showerror("Error", f"Invalid configuration: {str(e)}")
            
            ttk.Button(btn_frame, text="Save & Add", command=save_and_close, 
                    style="Accent.TButton").pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def update_ports_display(self):
        """Update ports treeview display"""
        # Clear existing items
        for item in self.ports_tree.get_children():
            self.ports_tree.delete(item)
        
        # Add configured ports
        for port_name, config in self.serial_configs.items():
            status = "Connected" if self.serial_running.get(port_name, False) else "Disconnected"
            last_activity = "N/A"
            
            self.ports_tree.insert('', tk.END, values=(
                port_name,
                config['baudrate'],
                status,
                last_activity
            ))
        
        # Update status label
        total_ports = len(self.serial_configs)
        connected_ports = sum(1 for running in self.serial_running.values() if running)
        self.multi_serial_status.configure(
            text=f"Connected Ports: {connected_ports} | Total Configured: {total_ports}",
            fg='#27ae60' if connected_ports > 0 else '#7f8c8d'
        )

    def configure_selected_port(self):
        """Configure selected port - RESPONSIVE & CLEAN UI"""
        selected = self.ports_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a port first")
            return
        
        item = self.ports_tree.item(selected[0])
        port_name = item['values'][0]
        
        if port_name not in self.serial_configs:
            messagebox.showerror("Error", f"Configuration for {port_name} not found")
            return
        
        # CHECK: Port harus DISCONNECT dulu sebelum dikonfigurasi
        if self.serial_running.get(port_name, False):
            if not messagebox.askyesno("Confirm", 
                f"Port {port_name} is currently connected.\n\n"
                "Do you want to disconnect and reconfigure it?"):
                return
            
            # Disconnect port dulu
            self.disconnect_single_port(port_name)
            time.sleep(0.5)  # Wait for disconnect
        
        # Get current configuration
        current_config = self.serial_configs[port_name]
        
        # ===== CREATE CONFIGURATION DIALOG =====
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Configure Port: {port_name}")
        
        # FIX: Set minimum size dan proper geometry
        dialog.minsize(520, 480)  # Minimum width x height
        
        # Calculate position for center screen
        dialog.update_idletasks()
        
        # Get screen dimensions
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        
        # Calculate window size (responsive based on screen)
        if screen_width <= 1366:  # Small screen
            window_width = 500
            window_height = 460
        else:  # Normal/Large screen
            window_width = 550
            window_height = 500
        
        # Calculate center position
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        dialog.geometry(f"{window_width}x{window_height}+{x}+{y}")
        dialog.resizable(False, False)  # Fixed size untuk konsistensi
        dialog.transient(self.root)
        dialog.grab_set()
        
        # ===== MAIN CONTAINER WITH PROPER LAYOUT =====
        # Use grid with weight configuration for responsive layout
        dialog.grid_rowconfigure(0, weight=0)  # Config frame (fixed)
        dialog.grid_rowconfigure(1, weight=0)  # Status frame (fixed)
        dialog.grid_rowconfigure(2, weight=1)  # Spacer (expandable)
        dialog.grid_rowconfigure(3, weight=0)  # Button frame (fixed at bottom)
        dialog.grid_columnconfigure(0, weight=1)
        
        # ===== CONFIGURATION FRAME =====
        config_frame = ttk.LabelFrame(dialog, text=f"Port Configuration", padding=15)
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky='ew')
        
        # Configure internal grid
        config_frame.grid_columnconfigure(1, weight=1)
        
        # ===== PORT NAME (READ-ONLY) =====
        ttk.Label(config_frame, text="Port Name:", font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky='w', pady=8, padx=5
        )
        port_label = ttk.Label(
            config_frame, 
            text=port_name, 
            font=("Arial", 10, "bold"), 
            foreground="#2980b9"
        )
        port_label.grid(row=0, column=1, pady=8, padx=5, sticky='w')
        
        # ===== SEPARATOR =====
        ttk.Separator(config_frame, orient='horizontal').grid(
            row=1, column=0, columnspan=2, sticky='ew', pady=5
        )
        
        # ===== BAUDRATE =====
        ttk.Label(config_frame, text="Baudrate:").grid(
            row=2, column=0, sticky='w', pady=5, padx=5
        )
        baudrate_var = tk.StringVar(value=str(current_config['baudrate']))
        baudrate_combo = ttk.Combobox(
            config_frame, 
            textvariable=baudrate_var, 
            values=['9600', '19200', '38400', '57600', '115200'], 
            width=25,
            state='readonly'
        )
        baudrate_combo.grid(row=2, column=1, pady=5, padx=5, sticky='ew')
        
        # ===== DATA BITS =====
        ttk.Label(config_frame, text="Data Bits:").grid(
            row=3, column=0, sticky='w', pady=5, padx=5
        )
        databits_var = tk.StringVar(value=str(current_config['bytesize']))
        databits_combo = ttk.Combobox(
            config_frame, 
            textvariable=databits_var,
            values=['5', '6', '7', '8'], 
            width=25,
            state='readonly'
        )
        databits_combo.grid(row=3, column=1, pady=5, padx=5, sticky='ew')
        
        # ===== PARITY =====
        ttk.Label(config_frame, text="Parity:").grid(
            row=4, column=0, sticky='w', pady=5, padx=5
        )
        parity_var = tk.StringVar(value=current_config['parity'])
        parity_combo = ttk.Combobox(
            config_frame, 
            textvariable=parity_var,
            values=['N', 'E', 'O', 'M', 'S'], 
            width=25,
            state='readonly'
        )
        parity_combo.grid(row=4, column=1, pady=5, padx=5, sticky='ew')
        
        # ===== STOP BITS =====
        ttk.Label(config_frame, text="Stop Bits:").grid(
            row=5, column=0, sticky='w', pady=5, padx=5
        )
        stopbits_var = tk.StringVar(value=str(current_config['stopbits']))
        stopbits_combo = ttk.Combobox(
            config_frame, 
            textvariable=stopbits_var,
            values=['1', '1.5', '2'], 
            width=25,
            state='readonly'
        )
        stopbits_combo.grid(row=5, column=1, pady=5, padx=5, sticky='ew')
        
        # ===== TIMEOUT =====
        ttk.Label(config_frame, text="Timeout (seconds):").grid(
            row=6, column=0, sticky='w', pady=5, padx=5
        )
        timeout_var = tk.StringVar(value=str(current_config['timeout']))
        timeout_entry = ttk.Entry(config_frame, textvariable=timeout_var, width=27)
        timeout_entry.grid(row=6, column=1, pady=5, padx=5, sticky='ew')
        
        # ===== CURRENT STATUS FRAME =====
        status_frame = ttk.LabelFrame(dialog, text="Current Status", padding=12)
        status_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky='ew')
        
        # Status info
        is_connected = self.serial_running.get(port_name, False)
        status_text = f"Status: {'🟢 Connected' if is_connected else '🔴 Disconnected'}\n"
        status_text += f"Original Baudrate: {current_config['baudrate']} bps\n"
        status_text += f"Original Data Bits: {current_config['bytesize']}"
        
        status_label = ttk.Label(
            status_frame, 
            text=status_text, 
            font=("Consolas", 9),
            justify=tk.LEFT
        )
        status_label.pack(anchor='w')

        # ===== BUTTON FRAME (ALWAYS AT BOTTOM) =====
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, padx=10, pady=10, sticky='ew')
        
        # Configure button columns for equal spacing
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        btn_frame.grid_columnconfigure(2, weight=1)
        
        # ===== BUTTON FUNCTIONS =====
        def save_and_close():
            """Save new configuration"""
            try:
                # Validate inputs
                new_config = {
                    'port': port_name,
                    'baudrate': int(baudrate_var.get()),
                    'bytesize': int(databits_var.get()),
                    'parity': parity_var.get(),
                    'stopbits': float(stopbits_var.get()),
                    'timeout': float(timeout_var.get())
                }
                
                # Validate timeout range
                if new_config['timeout'] <= 0 or new_config['timeout'] > 60:
                    messagebox.showerror("Validation Error", 
                        "Timeout must be between 0 and 60 seconds")
                    return
                
                # Update configuration
                self.serial_configs[port_name] = new_config
                
                # Update display
                self.update_ports_display()
                
                # Log changes
                changes = []
                if current_config['baudrate'] != new_config['baudrate']:
                    changes.append(f"Baudrate: {current_config['baudrate']} → {new_config['baudrate']}")
                if current_config['bytesize'] != new_config['bytesize']:
                    changes.append(f"Data Bits: {current_config['bytesize']} → {new_config['bytesize']}")
                if current_config['parity'] != new_config['parity']:
                    changes.append(f"Parity: {current_config['parity']} → {new_config['parity']}")
                if current_config['stopbits'] != new_config['stopbits']:
                    changes.append(f"Stop Bits: {current_config['stopbits']} → {new_config['stopbits']}")
                if current_config['timeout'] != new_config['timeout']:
                    changes.append(f"Timeout: {current_config['timeout']}s → {new_config['timeout']}s")
                
                if changes:
                    self.log_multi_serial(f"{port_name} configuration updated:")
                    for change in changes:
                        self.log_multi_serial(f"   • {change}")
                    
                    messagebox.showinfo("Success", 
                        f"Configuration for {port_name} has been updated!\n\n"
                        f"Changes made:\n" + "\n".join(f"• {c}" for c in changes) + 
                        "\n\nNote: Reconnect the port to apply new settings.")
                else:
                    self.log_multi_serial(f"{port_name} configuration unchanged")
                    messagebox.showinfo("No Changes", 
                        "No configuration changes were made.")
                
                dialog.destroy()
                
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid configuration values:\n{str(e)}")
        
        def cancel_and_close():
            """Cancel without saving"""
            dialog.destroy()
        
        def save_and_reconnect():
            """Save and immediately reconnect"""
            try:
                # Save configuration
                new_config = {
                    'port': port_name,
                    'baudrate': int(baudrate_var.get()),
                    'bytesize': int(databits_var.get()),
                    'parity': parity_var.get(),
                    'stopbits': float(stopbits_var.get()),
                    'timeout': float(timeout_var.get())
                }
                
                # Validate timeout range
                if new_config['timeout'] <= 0 or new_config['timeout'] > 60:
                    messagebox.showerror("Validation Error", 
                        "Timeout must be between 0 and 60 seconds")
                    return
                
                self.serial_configs[port_name] = new_config
                self.update_ports_display()
                
                self.log_multi_serial(f"{port_name} configuration saved, reconnecting...")
                
                dialog.destroy()
                
                # Reconnect with new settings
                self.connect_single_port(port_name)
                
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid configuration values:\n{str(e)}")
        
        # ===== CREATE BUTTONS WITH PROPER STYLING =====
        save_btn = ttk.Button(
            btn_frame, 
            text="💾 Save Only", 
            command=save_and_close,
            style="Accent.TButton"
        )
        save_btn.grid(row=0, column=0, padx=5, sticky='ew')
        
        save_reconnect_btn = ttk.Button(
            btn_frame, 
            text="💾 Save & Reconnect", 
            command=save_and_reconnect,
            style="Accent.TButton"
        )
        save_reconnect_btn.grid(row=0, column=1, padx=5, sticky='ew')
        
        cancel_btn = ttk.Button(
            btn_frame, 
            text="❌ Cancel", 
            command=cancel_and_close
        )
        cancel_btn.grid(row=0, column=2, padx=5, sticky='ew')
        
        # ===== KEYBOARD SHORTCUTS =====
        dialog.bind('<Escape>', lambda e: cancel_and_close())
        dialog.bind('<Return>', lambda e: save_and_close())
        
        # Focus on first editable field
        baudrate_combo.focus_set()

    def connect_selected_port(self):
            """Connect to selected port"""
            selected = self.ports_tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select a port first")
                return
            
            item = self.ports_tree.item(selected[0])
            port_name = item['values'][0]
            
            if self.serial_running.get(port_name, False):
                messagebox.showinfo("Info", f"Port {port_name} is already connected")
                return
            
            self.connect_single_port(port_name)

    def connect_single_port(self, port_name):
        """Connect to a single serial port - WITH TIMEOUT FALLBACK"""
        if port_name not in self.serial_configs:
            self.log_multi_serial(f"❌ Port {port_name} not configured")
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
                
                self.auto_register_serial_device(port_name)
                device_label = self.device_labels["serial"].get(port_name, "Unlabeled Device")
                
                self.serial_connections[port_name] = ser
                self.serial_running[port_name] = True
                
                self.root.after(0, lambda: self.log_multi_serial(
                    f"{port_name} connected at {config['baudrate']} baud | Label: {device_label}"
                ))
                self.root.after(0, self.update_ports_display)
                
                # Send initial ACK
                try:
                    time.sleep(0.5)
                    initial_ack = "<ACK>\n".encode('utf-8')
                    ser.write(initial_ack)
                    ser.flush()
                    self.root.after(0, lambda: self.log_multi_serial(
                        f"Initial ACK sent to {port_name}"
                    ))
                except Exception as e:
                    self.root.after(0, lambda: self.log_multi_serial(
                        f"Failed to send initial ACK to {port_name}: {str(e)}"
                    ))
                
                data_buffer = ""
                last_data_time = time.time()  # NEW: Track last data received
                
                while self.serial_running.get(port_name, False):
                    try:
                        if ser.in_waiting > 0:
                            chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                            data_buffer += chunk
                            last_data_time = time.time()  # Update timestamp
                            time.sleep(0.05)
                            
                            # Check if message complete
                            is_complete, data_format = self.is_complete_message(data_buffer)
                            
                            # NEW: Timeout fallback
                            time_since_last_data = time.time() - last_data_time
                            force_process = (
                                len(data_buffer) > 100 and 
                                time_since_last_data > 2.0 and
                                ("MSH" in data_buffer or "OBX" in data_buffer or "STXA" in data_buffer)
                            )
                            
                            if is_complete or force_process:
                                received_data = data_buffer.strip()
                                data_buffer = ""
                                
                                format_name = {
                                    "URIT_8030": "URIT-8030",
                                    "BC5300_HL7": "BC-5300",
                                    "CUSTOM_HL7": "Custom HL7",
                                    "BC1800": "BC-1800",
                                    "ASTM": "ASTM",
                                    "HL7": "Standard HL7",
                                    "UNKNOWN": "Unknown"
                                }.get(data_format, "Unknown")
                                
                                if force_process:
                                    self.root.after(0, lambda fmt=format_name, size=len(received_data): 
                                        self.log_multi_serial(
                                            f"[{port_name}] Timeout-based completion {fmt} ({size} bytes)"
                                        )
                                    )
                                else:
                                    self.root.after(0, lambda fmt=format_name, size=len(received_data): 
                                        self.log_multi_serial(
                                            f"[{port_name}] Received {fmt} data ({size} bytes)"
                                        )
                                    )
                                
                                # Display received data
                                self.root.after(0, lambda data=received_data, pn=port_name: 
                                    self.display_serial_received_data(data, pn))
                                
                                # Process with device context (thread-safe)
                                threading.Thread(
                                    target=self.process_and_save_with_context,
                                    args=(received_data, 'serial', port_name),
                                    daemon=True
                                ).start()
                                
                                # Send ACK
                                try:
                                    ack = "<ACK>\n".encode('utf-8')
                                    ser.write(ack)
                                    ser.flush()
                                    self.root.after(0, lambda fmt=format_name: 
                                        self.log_multi_serial(f"ACK sent to {port_name} ({fmt})")
                                    )
                                except Exception as e:
                                    self.root.after(0, lambda: 
                                        self.log_multi_serial(f"[{port_name}] Failed to send ACK: {str(e)}")
                                    )
                                
                                # Reset timer
                                last_data_time = time.time()
                        
                        else:
                            # NEW: Check timeout when no data waiting
                            time_since_last_data = time.time() - last_data_time
                            if (len(data_buffer) > 100 and 
                                time_since_last_data > 2.0 and
                                ("MSH" in data_buffer or "OBX" in data_buffer or "STXA" in data_buffer)):
                                
                                # Force process buffered data
                                received_data = data_buffer.strip()
                                data_buffer = ""
                                
                                self.root.after(0, lambda size=len(received_data): 
                                    self.log_multi_serial(
                                        f"[{port_name}] Timeout - processing buffered data ({size} bytes)"
                                    )
                                )
                                
                                # Display and process
                                self.root.after(0, lambda data=received_data, pn=port_name: 
                                    self.display_serial_received_data(data, pn))
                                
                                threading.Thread(
                                    target=self.process_and_save_with_context,
                                    args=(received_data, 'serial', port_name),
                                    daemon=True
                                ).start()
                                
                                last_data_time = time.time()
                            
                            time.sleep(0.1)  # Small delay when no data
                    
                    except serial.SerialException as e:
                        self.root.after(0, lambda: self.log_multi_serial(f"❌ [{port_name}] Serial error: {str(e)}"))
                        break
                    except Exception as e:
                        self.root.after(0, lambda: self.log_multi_serial(f"❌ [{port_name}] Error: {str(e)}"))
            
            except serial.SerialException as e:
                self.serial_running[port_name] = False
                self.root.after(0, lambda: self.log_multi_serial(f"❌ [{port_name}] Cannot open port: {str(e)}"))
                self.root.after(0, self.update_ports_display)
            except Exception as e:
                self.serial_running[port_name] = False
                self.root.after(0, lambda: self.log_multi_serial(f"❌ [{port_name}] Connection failed: {str(e)}"))
                self.root.after(0, self.update_ports_display)
        
        thread = threading.Thread(target=run_serial, daemon=True)
        self.serial_threads[port_name] = thread
        thread.start()

    def disconnect_selected_port(self):
            """Disconnect selected port"""
            selected = self.ports_tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select a port first")
                return
            
            item = self.ports_tree.item(selected[0])
            port_name = item['values'][0]
            
            self.disconnect_single_port(port_name)

    def disconnect_single_port(self, port_name):
        """Disconnect single port"""
        if not self.serial_running.get(port_name, False):
            self.log_multi_serial(f"[{port_name}] Already disconnected")
            return
        
        self.serial_running[port_name] = False
        
        if port_name in self.serial_connections:
            try:
                self.serial_connections[port_name].close()
                del self.serial_connections[port_name]
            except:
                pass
        
        self.log_multi_serial(f"[{port_name}] Disconnected")
        self.update_ports_display()

    def remove_selected_port(self):
        """Remove selected port from configuration"""
        selected = self.ports_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a port first")
            return
        
        item = self.ports_tree.item(selected[0])
        port_name = item['values'][0]
        
        if self.serial_running.get(port_name, False):
            messagebox.showwarning("Warning", f"Please disconnect {port_name} first")
            return
        
        if messagebox.askyesno("Confirm", f"Remove port {port_name} from configuration?"):
            if port_name in self.serial_configs:
                del self.serial_configs[port_name]
            if port_name in self.serial_running:
                del self.serial_running[port_name]
            
            self.update_ports_display()
            self.log_multi_serial(f"Port {port_name} removed from configuration")

    def connect_all_ports(self):
        """Connect to all configured ports"""
        if not self.serial_configs:
            messagebox.showinfo("Info", "No ports configured")
            return
        
        for port_name in self.serial_configs.keys():
            if not self.serial_running.get(port_name, False):
                self.connect_single_port(port_name)
                time.sleep(0.1)  # Small delay between connections
        
        self.log_multi_serial("Connecting to all configured ports...")

    def disconnect_all_ports(self):
        """Disconnect all connected ports"""
        for port_name in list(self.serial_running.keys()):
            if self.serial_running.get(port_name, False):
                self.disconnect_single_port(port_name)
        
        self.log_multi_serial("All ports disconnected")

    def clear_all_serial_data(self):
        """Clear all serial data"""
        self.clear_results_tab()
        self.log_multi_serial("All serial data cleared")

    def log_multi_serial(self, message):
        """Log message to multi serial log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.multi_serial_log.configure(state=tk.NORMAL)
        self.multi_serial_log.insert(tk.END, log_entry)
        self.multi_serial_log.see(tk.END)
        self.multi_serial_log.configure(state=tk.DISABLED)

    def clear_multi_serial_log(self):
        """Clear multi serial log"""
        self.multi_serial_log.configure(state=tk.NORMAL)
        self.multi_serial_log.delete(1.0, tk.END)
        self.multi_serial_log.configure(state=tk.DISABLED)
        self.log_multi_serial("Log cleared")

    def display_serial_received_data(self, data, port_name):
        """Display received serial data with port identifier"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"{'='*70}\n[{timestamp}] Data from {port_name} ({len(data)} bytes)\n{'='*70}\n\n"
        
        self.serial_received_data_text.configure(state=tk.NORMAL)
        self.serial_received_data_text.insert(tk.END, header)
        self.serial_received_data_text.insert(tk.END, data)
        self.serial_received_data_text.insert(tk.END, f"\n\n{'='*70}\n\n")
        self.serial_received_data_text.see(tk.END)
        self.serial_received_data_text.configure(state=tk.DISABLED)

    def clear_serial_received_data(self):
        """Clear serial received data display"""
        self.serial_received_data_text.configure(state=tk.NORMAL)
        self.serial_received_data_text.delete(1.0, tk.END)
        self.serial_received_data_text.configure(state=tk.DISABLED)
        self.log_multi_serial("Received data display cleared")
    
# 10. ===SETTING TAB MENU LABEL DEVICE===
    def create_socket_label_tab(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        frame = ttk.LabelFrame(parent, text="Manage Socket Device Labels", padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        columns = ("IP Address", "Device Label")
        self.socket_label_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            self.socket_label_tree.heading(col, text=col)
            self.socket_label_tree.column(col, width=200, minwidth=100)
        self.socket_label_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.socket_label_tree.yview)
        self.socket_label_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, pady=10, sticky="ew")
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)

        ttk.Button(btn_frame, text="Add / Update", command=self.add_socket_label).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_socket_label).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="Save Labels", command=self.save_device_labels).grid(row=0, column=2, padx=5)

        self.refresh_socket_label_tree()

    def create_serial_label_tab(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        frame = ttk.LabelFrame(parent, text="Manage Serial Device Labels", padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        columns = ("Port", "Device Label")
        self.serial_label_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            self.serial_label_tree.heading(col, text=col)
            self.serial_label_tree.column(col, width=200, minwidth=100)
        self.serial_label_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.serial_label_tree.yview)
        self.serial_label_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, pady=10, sticky="ew")
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)

        ttk.Button(btn_frame, text="Add / Update", command=self.add_serial_label).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_serial_label).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="Save Labels", command=self.save_device_labels).grid(row=0, column=2, padx=5)

        self.refresh_serial_label_tree()

    def add_socket_label(self):
        selected = self.socket_label_tree.selection()
        if selected:
            item = self.socket_label_tree.item(selected[0])
            ip = item["values"][0]  # Ambil IP yang dipilih
            label = simpledialog.askstring("Add Socket Label", f"Enter label for {ip}:")
            if label:
                self.device_labels["socket"][ip] = label
                self.save_device_labels()
                self.refresh_socket_label_tree()

    def delete_socket_label(self):
        selected = self.socket_label_tree.selection()
        if selected:
            item = self.socket_label_tree.item(selected[0])
            ip = item["values"][0]
            if ip in self.device_labels["socket"]:
                del self.device_labels["socket"][ip]
                self.save_device_labels()
                self.refresh_socket_label_tree()

    def refresh_socket_label_tree(self):
        for i in self.socket_label_tree.get_children():
            self.socket_label_tree.delete(i)
        for ip, label in self.device_labels["socket"].items():
            self.socket_label_tree.insert("", tk.END, values=(ip, label))

    def add_serial_label(self):
        selected = self.serial_label_tree.selection()
        if selected:
            item = self.serial_label_tree.item(selected[0])
            port = item["values"][0]  # Ambil port yang dipilih
            label = simpledialog.askstring("Add Serial Label", f"Enter label for {port}:")
            if label:
                self.device_labels["serial"][port] = label
                self.save_device_labels()
                self.refresh_serial_label_tree()

    def delete_serial_label(self):
        selected = self.serial_label_tree.selection()
        if selected:
            item = self.serial_label_tree.item(selected[0])
            port = item["values"][0]
            if port in self.device_labels["serial"]:
                del self.device_labels["serial"][port]
                self.save_device_labels()
                self.refresh_serial_label_tree()

    def refresh_serial_label_tree(self):
        for i in self.serial_label_tree.get_children():
            self.serial_label_tree.delete(i)
        for port, label in self.device_labels["serial"].items():
            self.serial_label_tree.insert("", tk.END, values=(port, label))

    def auto_register_socket_device(self, ip):
        """Automatically add a new IP to the socket device list if not present"""
        if ip not in self.device_labels["socket"]:
            self.device_labels["socket"][ip] = ""  # Kolom label kosong
            self.refresh_socket_label_tree()
            self.save_device_labels()
            self.update_status(f"New socket device detected: {ip}")

    def auto_register_serial_device(self, port):
        """Automatically add a new serial port to the serial device list if not present"""
        if port not in self.device_labels["serial"]:
            self.device_labels["serial"][port] = ""  # Kolom label kosong
            self.refresh_serial_label_tree()
            self.save_device_labels()
            self.update_status(f"New serial device detected: {port}")

# 11. ===SETTING API INTEGRATION METHODS===
    def save_api_config(self):
        """Save API configuration"""
        try:
            self.api_config = {
                'endpoint': self.api_endpoint_entry.get(),
                'method': self.api_method_var.get(),
                'api_key': self.api_key_entry.get(),
                'timeout': int(self.api_timeout_entry.get()),
                'enabled': self.api_enabled_var.get()
            }
            
            status = "enabled" if self.api_config['enabled'] else "disabled"
            self.api_status_label.configure(
                text=f"API Status: Configuration saved ({status})",
                fg='#27ae60' if self.api_config['enabled'] else '#f39c12'
            )
            self.log_api_response("API configuration saved successfully")
            messagebox.showinfo("Success", "API configuration saved!")

            # Auto-save if enabled
            if self.auto_startup_enabled:
                self.save_app_configuration()
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid timeout value: {str(e)}")
    
    def test_api_connection(self):
        """Test API connection"""
        if not self.api_endpoint_entry.get():
            messagebox.showwarning("Warning", "Please enter an API endpoint first")
            return
        
        def test_connection():
            try:
                headers = {
                    'Content-Type': 'application/json',
                }
                
                if self.api_key_entry.get():
                    headers['Authorization'] = f'Bearer {self.api_key_entry.get()}'
                
                # Check if endpoint is for health check or main results endpoint
                endpoint = self.api_endpoint_entry.get()
                
                # If endpoint ends with /results, send proper lab data format
                if endpoint.endswith('/results'):
                    # Send a minimal valid test payload
                    test_payload = {
                        "timestamp": datetime.now().isoformat(),
                        "source": "HL7_Parser_ConnectionTest",
                        "patient": {
                            "first_name": "Test",
                            "last_name": "Connection",
                            "date_of_birth": "19900101",
                            "sex": "M"
                        },
                        "laboratory_results": [
                            {
                                "test_name": "Connection Test",
                                "value": "0",
                                "units": "test",
                                "reference_range": "0-0",
                                "abnormal_flag": None,
                                "status": "normal"
                            }
                        ]
                    }
                    
                    response = requests.post(
                        endpoint,
                        json=test_payload,
                        headers=headers,
                        timeout=int(self.api_timeout_entry.get())
                    )
                else:
                    # For other endpoints (like /health), just do a GET or simple POST
                    # Try GET first for health check endpoints
                    try:
                        response = requests.get(
                            endpoint,
                            headers=headers,
                            timeout=int(self.api_timeout_entry.get())
                        )
                    except:
                        # If GET fails, try POST with minimal payload
                        test_payload = {
                            "test": True,
                            "timestamp": datetime.now().isoformat(),
                            "message": "API connection test from HL7 Parser"
                        }
                        response = requests.post(
                            endpoint,
                            json=test_payload,
                            headers=headers,
                            timeout=int(self.api_timeout_entry.get())
                        )
                
                if response.status_code in [200, 201, 202]:
                    self.root.after(0, lambda: self.api_status_label.configure(
                        text=f"API Status: Connected (Status: {response.status_code})",
                        fg='#27ae60'
                    ))
                    self.root.after(0, lambda: self.log_api_response(
                        f"✓ Connection test successful - Status: {response.status_code}\nResponse: {response.text[:500]}"
                    ))
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Success", 
                        f"API connection successful!\nStatus Code: {response.status_code}\n\n"
                        f"Tip: Connection test data was sent to verify API is working."
                    ))
                elif response.status_code == 400:
                    self.root.after(0, lambda: self.api_status_label.configure(
                        text=f"API Status: Bad Request (400)",
                        fg='#e67e22'
                    ))
                    self.root.after(0, lambda: self.log_api_response(
                        f"⚠ Bad Request (400) - Endpoint may require different data format\n"
                        f"Response: {response.text[:500]}\n\n"
                        f"Tip: Use /api/health endpoint for connection testing, or ensure endpoint expects lab results format."
                    ))
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Connection Issue",
                        f"API returned 400 (Bad Request)\n\n"
                        f"This usually means:\n"
                        f"1. Endpoint requires specific data format\n"
                        f"2. Missing required fields\n"
                        f"3. Try using health check endpoint: /api/health\n\n"
                        f"Response: {response.text[:200]}"
                    ))
                elif response.status_code == 401:
                    self.root.after(0, lambda: self.api_status_label.configure(
                        text=f"API Status: Unauthorized (401)",
                        fg='#e74c3c'
                    ))
                    self.root.after(0, lambda: self.log_api_response(
                        f"✗ Unauthorized (401) - Invalid or missing API key\nResponse: {response.text[:500]}"
                    ))
                    self.root.after(0, lambda: messagebox.showerror(
                        "Authentication Error",
                        f"API Key is invalid or missing!\n\n"
                        f"Please check:\n"
                        f"1. API Key is correct\n"
                        f"2. API Key matches server configuration\n"
                        f"3. Format is correct (no extra spaces)"
                    ))
                else:
                    self.root.after(0, lambda: self.api_status_label.configure(
                        text=f"API Status: Error (Status: {response.status_code})",
                        fg='#e74c3c'
                    ))
                    self.root.after(0, lambda: self.log_api_response(
                        f"✗ Connection test failed - Status: {response.status_code}\nResponse: {response.text[:500]}"
                    ))
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"API returned error status: {response.status_code}\n\n{response.text[:200]}"
                    ))
                    
            except requests.exceptions.Timeout:
                self.root.after(0, lambda: self.log_api_response("✗ Connection timeout"))
                self.root.after(0, lambda: messagebox.showerror("Error", "Connection timeout - Server took too long to respond"))
            except requests.exceptions.ConnectionError:
                self.root.after(0, lambda: self.log_api_response("✗ Connection error - Cannot reach endpoint"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Connection Error", 
                    "Cannot connect to API endpoint\n\n"
                    "Please check:\n"
                    "1. API server is running\n"
                    "2. URL is correct\n"
                    "3. Network/firewall is not blocking"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.log_api_response(f"✗ Error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", f"Connection test failed:\n\n{str(e)}"))
        
        threading.Thread(target=test_connection, daemon=True).start()
        self.log_api_response("Testing API connection...")

    def generate_json_payload(self):
        """Generate JSON payload - Support Custom HL7, BC-5300, ASTM"""
        if not hasattr(self, 'patient'):
            messagebox.showwarning("Warning", "Please parse data first")
            return

        try:
            # Check data format
            data_format = getattr(self, 'current_data_format', 'HL7')
            
            # Base payload
            payload = {
                "timestamp": datetime.now().isoformat(),
                "source": "HL7_Parser_LIMS",
                "data_format": data_format,
                "patient": {
                    "patient_id": self.patient.get("patient_id", ""),
                    "sample_time": self.patient.get("sample_time", "")
                }
            }
            
            # FIX: Laboratory results ONLY for HL7 and Custom HL7
            if data_format in ["HL7", "CUSTOM_HL7", "URIT_8030"] and hasattr(self, 'results') and len(self.results) > 0:
                payload["patient"]["total_results"] = len(self.results)
                payload["laboratory_results"] = []
                
                for result in self.results:
                    abnormal_flag = result.get('abnormal_flag', '').strip()

                    # Determine status
                    if abnormal_flag.upper() in ['NORMAL', 'N', 'normal', 'n', '']:
                        status = 'normal'
                    else:
                        status = 'abnormal'

                    test_data = {
                        "test_name": result.get('test_name', ''),
                        "value": result.get('value', ''),
                        "units": result.get('units', ''),
                        "reference_range": result.get('reference_range', ''),
                        "abnormal_flag": abnormal_flag if abnormal_flag else None,
                        "status": status
                    }
                    payload["laboratory_results"].append(test_data)
            
            # Display JSON
            json_formatted = json.dumps(payload, indent=2, ensure_ascii=False)
            self.json_preview.delete(1.0, tk.END)
            self.json_preview.insert(1.0, json_formatted)

            # Enable send button
            self.send_api_btn.configure(state=tk.NORMAL)
            self.current_payload = payload

            # FIX: Log message
            if data_format in ["ASTM", "BC5300_HL7"]:
                self.log_api_response(f"JSON payload generated - {data_format} patient data only (no detailed results)")
            elif data_format == ["CUSTOM_HL7", "URIT_8030"]:
                self.log_api_response(f"JSON payload generated - Custom HL7 with {len(self.results)} test results")
            else:
                self.log_api_response(f"JSON payload generated - HL7 with {len(self.results)} test results")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate JSON: {str(e)}")
            self.log_api_response(f"Error generating JSON: {str(e)}")

    def send_to_api(self):
        """Send data to API endpoint"""
        if not self.api_config['enabled']:
            messagebox.showwarning("Warning", "API integration is not enabled. Please enable it in API settings.")
            return
        
        if not hasattr(self, 'current_payload'):
            messagebox.showwarning("Warning", "Please generate JSON payload first")
            return
        
        def send_request():
            try:
                headers = {
                    'Content-Type': 'application/json',
                }
                
                if self.api_config['api_key']:
                    headers['Authorization'] = f"Bearer {self.api_config['api_key']}"
                
                self.root.after(0, lambda: self.log_api_response(
                    f"Sending data to {self.api_config['endpoint']}..."
                ))
                
                # Send request based on method
                if self.api_config['method'] == 'POST':
                    response = requests.post(
                        self.api_config['endpoint'],
                        json=self.current_payload,
                        headers=headers,
                        timeout=self.api_config['timeout']
                    )
                elif self.api_config['method'] == 'PUT':
                    response = requests.put(
                        self.api_config['endpoint'],
                        json=self.current_payload,
                        headers=headers,
                        timeout=self.api_config['timeout']
                    )
                else:  # PATCH
                    response = requests.patch(
                        self.api_config['endpoint'],
                        json=self.current_payload,
                        headers=headers,
                        timeout=self.api_config['timeout']
                    )
                
                # Handle response
                if response.status_code in [200, 201, 202]:
                    self.root.after(0, lambda: self.log_api_response(
                        f"✓ SUCCESS - Status: {response.status_code}\n"
                        f"Response: {response.text[:500]}\n"
                        f"Sent {len(self.results)} test results"
                    ))
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Success",
                        f"Data sent successfully to API!\n"
                        f"Status Code: {response.status_code}\n"
                        f"Results sent: {len(self.results)}"
                    ))
                else:
                    self.root.after(0, lambda: self.log_api_response(
                        f"✗ FAILED - Status: {response.status_code}\n"
                        f"Response: {response.text[:500]}"
                    ))
                    self.root.after(0, lambda: messagebox.showerror(
                        "Error",
                        f"API returned error status: {response.status_code}\n{response.text[:200]}"
                    ))
                    
            except requests.exceptions.Timeout:
                self.root.after(0, lambda: self.log_api_response("✗ Request timeout"))
                self.root.after(0, lambda: messagebox.showerror("Error", "Request timeout"))
            except requests.exceptions.ConnectionError:
                self.root.after(0, lambda: self.log_api_response("✗ Connection error"))
                self.root.after(0, lambda: messagebox.showerror("Error", "Cannot connect to API"))
            except Exception as e:
                self.root.after(0, lambda: self.log_api_response(f"✗ Error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send data: {str(e)}"))
        
        threading.Thread(target=send_request, daemon=True).start()
    
    def copy_json_to_clipboard(self):
        """Copy JSON payload to clipboard"""
        json_text = self.json_preview.get(1.0, tk.END).strip()
        if json_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(json_text)
            self.log_api_response("JSON payload copied to clipboard")
            messagebox.showinfo("Success", "JSON copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "No JSON to copy. Generate payload first.")
    
    def log_api_response(self, message):
        """Log API response message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n{'-'*60}\n"
        
        self.api_response_log.configure(state=tk.NORMAL)
        self.api_response_log.insert(tk.END, log_entry)
        self.api_response_log.see(tk.END)
        self.api_response_log.configure(state=tk.DISABLED)

    def exit_application(self):
        """Exit application - MODIFIED with auto-save"""
        # ✅ Save configuration before exit
        if self.auto_startup_enabled:
            self.log_multi_serial("Saving configuration for next startup...")
            self.save_app_configuration()
        
        # Disconnect all serial ports
        if any(self.serial_running.values()):
            self.disconnect_all_ports()
        
        # Stop socket server
        if self.socket_running:
            self.stop_socket_server()
        
        if messagebox.askyesno("Exit Confirmation", 
                            "Are you sure you want to exit the application?", 
                            icon='question'):
            self.root.quit()
            self.root.destroy()
    
    def update_status(self, message):
        """Update status label"""
        # self.status_label.configure(text=message)
        auto_startup_indicator = "🔄" if self.auto_startup_enabled else ""
        self.status_label.configure(text=f"{auto_startup_indicator} {message}")
        self.root.update_idletasks()

def main():
    root = tk.Tk()
    
    # Configure ttk styles
    style = ttk.Style()
    style.theme_use('clam')
    
    style.configure('Accent.TButton', 
                   foreground='white', 
                   background='#3498db',
                   font=('Arial', 10, 'bold'),
                   padding=6)
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
                   padding=[15, 5],
                   font=('Arial', 10))
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
    
    app = HL7ParserGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()