import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import sys
import queue
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import yt_dlp


# --- Base Directory Setup for PyInstaller ---
# This logic ensures that whether running as a script or a frozen .exe,
# all file paths are relative to the application's location.
if getattr(sys, 'frozen', False):
    # We are running in a bundle (e.g., PyInstaller executable)
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    # We are running in a normal Python environment (as a .py script)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- File and Folder Constants ---
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
LINKS_FILE = os.path.join(BASE_DIR, 'links.txt')
# Note: DOWNLOAD_DIR is built dynamically from the GUI input + BASE_DIR

# --- Constants ---
APP_TITLE = "Instagram Collections Downloader Pro"
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 550

# --- COLOR PALETTE ---
COLOR_BG = "#000000"
COLOR_BG_LIGHT = "#4A5A70"
COLOR_FG = "#FFFFFF"
COLOR_PRIMARY = "#4CAF50"
COLOR_PRIMARY_HOVER = "#45a049"
COLOR_SECONDARY = "#008CBA"
COLOR_SECONDARY_HOVER = "#007B9E"
COLOR_DANGER = "#f44336"
COLOR_DANGER_HOVER = "#e53935"


# --- Scraping Logic ---
SCROLL_PAUSE = 1.5
MAX_NO_NEW_ROUNDS = 5 # How many scrolls with no new links before stopping

def start_driver():
    """
    Starts and returns a new Chrome WebDriver instance.
    """
    options = webdriver.ChromeOptions()
    
    print("Initializing WebDriver...")
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Failed to use webdriver-manager: {e}. Trying default Service.")
        try:
            service = ChromeService() 
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e2:
            print(f"Fatal error initializing Chrome: {e2}")
            print("Please ensure ChromeDriver is installed and in your system's PATH, or that webdriver-manager can run.")
            raise
            
    driver.maximize_window()
    driver.get("https://www.instagram.com/")
    print("Browser opened to Instagram. Please log in.")
    return driver

def collect_reel_links(driver):
    """
    Collects all unique post/reel links from the currently open page.
    Assumes the user is already logged in and on a collection/profile page.
    
    Args:
        driver: The Selenium WebDriver instance.
        
    Returns:
        A list of unique, sorted links.
    """
    # --- MODIFICATION: Truncate links.txt before starting ---
    print(f"Clearing old links from {LINKS_FILE}...")
    try:
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            pass # Opening in "w" mode automatically truncates the file
    except Exception as e:
        print(f"Warning: Could not clear {LINKS_FILE}. {e}")
    # --- End Modification ---

    print("Starting link collection... Scrolling down.")
    seen = set()
    no_new_rounds = 0
    last_count = 0

    while no_new_rounds < MAX_NO_NEW_ROUNDS:
        anchors = driver.find_elements(By.XPATH, '//a[starts-with(@href, "/p/") or starts-with(@href, "/reel/")]')
        
        if not anchors:
            print("No links found on this scroll. Retrying...")

        for a in anchors:
            try:
                href = a.get_attribute("href")
                if href:
                    clean_link = href.split("?")[0].rstrip("/")
                    if clean_link not in seen:
                        seen.add(clean_link)
            except Exception:
                pass # Ignore stale elements

        current_count = len(seen)
        
        if current_count == last_count:
            no_new_rounds += 1
            print(f"No new links found on this scroll. (Round {no_new_rounds}/{MAX_NO_NEW_ROUNDS})")
        else:
            no_new_rounds = 0
            last_count = current_count
            print(f"Collected {current_count} unique links so far...")

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE)

    print(f"\n✅ Finished scrolling. Total unique links: {len(seen)}")
    return sorted(list(seen))

def save_links(links):
    """
    Saves the collected links to the global LINKS_FILE.
    """
    # --- MODIFICATION: Use global LINKS_FILE constant ---
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in links:
            f.write(link + "\n")
    print(f"Saved {len(links)} links to {LINKS_FILE}")
    # --- End Modification ---


# --- Download Logic ---
def start_download(download_dir, links_file=LINKS_FILE, cookies_file=COOKIES_FILE):
    """
    Starts the yt-dlp download process with specified parameters.
    
    Args:
        download_dir (str): The *absolute* folder path to save videos to.
        links_file (str): The *absolute* path to the file containing URLs.
        cookies_file (str): The *absolute* path to the Netscape cookies file.
    """
    
    # Create the download directory if it doesn't exist
    if not os.path.exists(download_dir):
        print(f"Creating download directory: {download_dir}")
        os.makedirs(download_dir)

    # Read URLs from the links file
    print(f"Reading links from {links_file}...")
    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(f"No URLs found in {links_file}. Nothing to download.")
        return

    print(f"Found {len(urls)} links to download.")

    # Configure yt-dlp options
    ydl_opts = {
        'outtmpl': os.path.join(download_dir, '%(upload_date)s_%(title)s.%(ext)s'),
        'cookies': cookies_file,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'ignoreerrors': True,
        'continuedl': True,
        'logtostderr': True,
        'progress_hooks': [print_progress], 
    }

    print(f"Starting download with yt-dlp...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download(urls)
        except Exception as e:
            print(f"yt-dlp download error: {e}")

    print("Download process finished.")

def print_progress(d):
    """
    Custom progress hook for yt-dlp to print status to stdout.
    """
    if d['status'] == 'downloading':
        filename = "unknown_file"
        if 'filename' in d:
            filename = os.path.basename(d['filename'])
        
        percent = d.get('_percent_str', '---%')
        speed = d.get('_speed_str', '---B/s')
        eta = d.get('_eta_str', '--:--')
        
        print(f"  Downloading: {filename} | {percent.strip()} | {speed.strip()} | ETA: {eta.strip()}", end="\r")

    if d['status'] == 'finished':
        filename = os.path.basename(d.get('filename', 'unknown_file'))
        print(f"\n  ✅ Finished: {filename}")


# --- Main GUI Application Class ---
class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.driver = None  
        self.log_queue = queue.Queue()

        self.setup_ui()
        self.configure_styles()
        self.redirect_stdout()
        self.check_log_queue()

    def setup_ui(self):
        """Initializes and lays out all UI components."""
        self.title(APP_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        folder_frame = ttk.Labelframe(main_frame, text=" 1. Download Folder ", padding=10)
        folder_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(folder_frame, text="Folder Name:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.folder_name_var = tk.StringVar(value="videos")
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_name_var, width=60)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        scraping_frame = ttk.Labelframe(main_frame, text=" 2. Scrape Video Links ", padding=15)
        scraping_frame.pack(fill=tk.X, pady=15)

        self.browser_button = ttk.Button(scraping_frame, text="Open Browser for Login", 
                                         command=self.start_browser_thread, style="Secondary.TButton")
        self.browser_button.pack(fill=tk.X, ipady=5)

        self.scrape_button = ttk.Button(scraping_frame, text="Start Scraping Links", 
                                        command=self.start_scraping_thread, state=tk.DISABLED)
        self.scrape_button.pack(fill=tk.X, ipady=5, pady=(10, 0))

        download_frame = ttk.Labelframe(main_frame, text=" 3. Download Videos ", padding=15)
        download_frame.pack(fill=tk.X, pady=15)

        self.download_button = ttk.Button(download_frame, text="Download All Videos", 
                                          command=self.start_download_thread, style="Primary.TButton")
        self.download_button.pack(fill=tk.X, ipady=10)

        log_frame = ttk.Labelframe(main_frame, text=" Status Log ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(15, 0))

        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, width=70, state=tk.DISABLED,
                                                  bg=COLOR_BG_LIGHT, fg=COLOR_FG,
                                                  font=("Inter", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
    def configure_styles(self):
        """Configures all ttk styles for the professional look."""
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure(".", background=COLOR_BG, foreground=COLOR_FG, fieldbackground=COLOR_BG_LIGHT)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_FG, font=("Inter", 10))
        style.configure("TEntry", fieldbackground=COLOR_BG_LIGHT, foreground=COLOR_FG, insertcolor=COLOR_FG)
        style.configure("TLabelframe", background=COLOR_BG, foreground=COLOR_FG, font=("Inter", 11, "bold"))
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_FG)

        style.map("TButton",
                  foreground=[('!active', COLOR_FG), ('active', COLOR_FG)],
                  background=[('!active', COLOR_SECONDARY), ('active', COLOR_SECONDARY_HOVER)])
        
        style.configure("TButton", font=("Inter", 10, "bold"), borderwidth=0, padding=10)
        
        style.configure("Primary.TButton", background=COLOR_PRIMARY)
        style.map("Primary.TButton",
                  background=[('!active', COLOR_PRIMARY), ('active', COLOR_PRIMARY_HOVER)])

        style.configure("Secondary.TButton", background=COLOR_SECONDARY)
        style.map("Secondary.TButton",
                  background=[('!active', COLOR_SECONDARY), ('active', COLOR_SECONDARY_HOVER)])
        
        style.map("TButton",
                  background=[('disabled', '#555')],
                  foreground=[('disabled', '#999')])

    # --- Threading and Logic ---

    def start_thread(self, target_function):
        thread = threading.Thread(target=target_function, daemon=True)
        thread.start()

    def start_browser_thread(self):
        print("Starting browser thread...")
        self.browser_button.config(text="Opening Browser...", state=tk.DISABLED)
        self.start_thread(self.open_browser)

    def open_browser(self):
        """
        Runs in a thread. Opens the browser and stores the driver instance.
        """
        try:
            print("Attempting to launch Chrome...")
            self.driver = start_driver() 
            print("✅ Browser is open. Please log in to Instagram.")
            print("   Once logged in, you can click 'Start Scraping Links'.")
            
            self.browser_button.config(text="Browser is Open", state=tk.DISABLED)
            self.scrape_button.config(state=tk.NORMAL)
            
        except Exception as e:
            print(f"Error opening browser: {e}")
            messagebox.showerror("Browser Error", f"Could not start Chrome. Is it installed?\nError: {e}")
            self.browser_button.config(text="Open Browser for Login", state=tk.NORMAL)

    def start_scraping_thread(self):
        if not self.driver:
            messagebox.showwarning("No Browser", "Please open the browser first.")
            return
            
        print("Starting link scraping...")
        self.scrape_button.config(text="Scraping... This may take a while.", state=tk.DISABLED)
        self.start_thread(self.scrape_links)

    def scrape_links(self):
        """
        Runs in a thread. Uses the existing driver to scrape links.
        """
        try:
            links = collect_reel_links(self.driver) 
            save_links(links) # MODIFIED: No argument needed
            print(f"✅ Scraping complete. {len(links)} links saved to {LINKS_FILE}")
            
            self.scrape_button.config(text="Scraping Complete", state=tk.DISABLED)
            messagebox.showinfo("Scraping Complete", f"Successfully saved {len(links)} links to {LINKS_FILE}.")
            
        except Exception as e:
            print(f"Error during scraping: {e}")
            messagebox.showerror("Scraping Error", f"An error occurred while scraping:\n{e}")
            self.scrape_button.config(text="Start Scraping Links", state=tk.NORMAL)

    def start_download_thread(self):
        print("Starting download process...")
        
        # --- MODIFICATIONS: Use global constants and update paths/messages ---
        
        # 1. Check for cookies.txt
        if not os.path.exists(COOKIES_FILE):
            print(f"Error: {COOKIES_FILE} not found.")
            messagebox.showerror("Cookies Not Found",
                                 f"Error: '{os.path.basename(COOKIES_FILE)}' not found.\n\n"
                                 "Please export your cookies from the browser "
                                 f"and save the file as '{os.path.basename(COOKIES_FILE)}' next to the application.")
            return

        # 2. Check for links.txt
        if not os.path.exists(LINKS_FILE) or os.path.getsize(LINKS_FILE) == 0:
            print(f"Error: {LINKS_FILE} is empty or missing.")
            messagebox.showerror("Links Not Found",
                                 f"Error: '{os.path.basename(LINKS_FILE)}' is empty or missing.\n\n"
                                 "Please use the scraping tool first to collect links.")
            return
            
        # 3. Get folder name and create absolute path
        download_dir_name = self.folder_name_var.get().strip()
        if not download_dir_name:
            messagebox.showwarning("Invalid Folder", "Please enter a valid folder name.")
            return
        
        # Create absolute path relative to BASE_DIR
        download_dir_path = os.path.join(BASE_DIR, download_dir_name)

        print(f"Download folder set to: {download_dir_path}")
        self.download_button.config(text="Downloading... See log for progress.", state=tk.DISABLED)
        
        # 4. Start download in a thread
        # Pass the absolute path, and the file constants
        self.start_thread(lambda: start_download(download_dir_path, LINKS_FILE, COOKIES_FILE))
        # --- End Modifications ---

    # --- Log and stdout Redirection ---

    def redirect_stdout(self):
        sys.stdout = self.QueueStream(self.log_queue)
        sys.stderr = self.QueueStream(self.log_queue)

    def write_to_log(self, message):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message)
        self.log_area.see(tk.END) # Auto-scroll
        self.log_area.config(state=tk.DISABLED)

    def check_log_queue(self):
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                self.write_to_log(message)
            except queue.Empty:
                pass
        
        self.after(100, self.check_log_queue)

    class QueueStream:
        def __init__(self, queue):
            self.queue = queue
        
        def write(self, text):
            self.queue.put(text)
        
        def flush(self):
            pass

    def on_closing(self):
        """Handle window close event."""
        if self.driver:
            print("Closing browser...")
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Error quitting driver: {e}")
        self.destroy()

# --- Run the Application ---
if __name__ == "__main__":
    app = DownloaderApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
