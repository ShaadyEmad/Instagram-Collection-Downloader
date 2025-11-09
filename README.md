# Instagram Collection Downloader

A simple GUI application for scraping and downloading all media from your private Instagram Saved Collections.

This tool provides a streamlined **3-step process**:
1. **Open Browser** - Launch a Selenium-controlled Chrome browser to log in
2. **Scrape Links** - Automatically collect all post URLs from your collection
3. **Download Videos** - Use yt-dlp to download all media to your computer

> **⚠️ Important Note:** This tool is designed specifically for downloading from your own private Instagram Saved Collections. A `cookies.txt` file is **mandatory** for the download feature to work with private posts.

---

## 📸 Application Screenshot

<div align="center">

![Application Interface](https://raw.githubusercontent.com/ShaadyEmad/Instagram-Collection-Downloader/main/screenshot.png)

</div>

---

## ✨ Features

- **Simple GUI** - Built with Tkinter for an intuitive, user-friendly interface
- **Collection-Focused Scraping** - Uses Selenium to automatically scroll and collect all post links from your saved collections
- **Powerful Downloading** - Leverages yt-dlp for reliable, high-quality media downloads
- **Cookie-Based Access** - Accesses your private collections using exported browser cookies
- **Portable** - Manages all files (links.txt, cookies.txt, downloads) in its own folder
- **Build-Ready** - Can be compiled into a standalone executable with PyInstaller

---

## 🔧 How It Works

### Scraping
The application uses Selenium to open a Chrome browser window where you log in to Instagram. After you manually navigate to your Saved collection page, the app takes control and automatically scrolls through the entire collection, extracting all post URLs. These links are saved to a local `links.txt` file for the download step.

### Downloading
Once links are collected, yt-dlp reads the URLs from `links.txt` and uses your `cookies.txt` file to authenticate and access your private saved posts. All media files are then downloaded to your specified folder with proper naming conventions.

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.7+** installed on your system
- **Google Chrome** browser installed

### Installation (Running from Source)

1. Clone the repository:
```bash
git clone https://github.com/ShaadyEmad/instagram-collection-downloader.git
cd instagram-collection-downloader
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

---

## 📖 How to Use

### ⚠️ Step 0: Get Your cookies.txt File (CRITICAL)

**This is the most important step!** Without this file, the downloader cannot access your private saved posts.

<div align="center">

![Cookie Export Process](https://via.placeholder.com/700x300/f44336/FFFFFF?text=Export+Cookies+from+Browser)

</div>

1. **Log in to Instagram** in your regular browser (Chrome, Firefox, etc.)
2. **Install a cookie export extension** such as:
   - [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome)
   - [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox)
3. **Export your cookies** in Netscape format
4. **Save the file as `cookies.txt`** in the same folder as the application

### Step 1: Run the Application

**From source:**
```bash
python main.py
```

**From executable:**
Simply double-click the `.exe` file (if you've built one following the instructions below)

### Step 2: Use the GUI

#### 1. Download Folder
- Enter a folder name where you want videos saved (optional)
- Defaults to `videos` if left blank
- The folder will be created automatically if it doesn't exist

#### 2. Scrape Video Links (from your Collection)
- Click **"Open Browser for Login"**
- A Chrome window will open - **log in to your Instagram account**
- Manually navigate to your **Saved collection** page (e.g., `instagram.com/your_username/saved/all-posts/`)

<div align="center">

![Instagram Saved Collection](https://via.placeholder.com/700x400/008CBA/FFFFFF?text=Navigate+to+Saved+Collections)

</div>

- Return to the app and click **"Start Scraping Links"**
- The app will automatically scroll through your collection and save all post URLs to `links.txt`
- This may take several minutes depending on the size of your collection

#### 3. Download Videos
- Ensure your `cookies.txt` file is in the application folder
- Click **"Download All Videos"**
- The download process will begin, and you can monitor progress in the Status Log
- All media will be saved to your specified download folder

---

## 🔨 How to Build Your Own Executable

You can compile this application into a standalone Windows executable that doesn't require Python to be installed.

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:
```bash
pyinstaller --onefile --windowed main.py
```

3. Your executable will be created in the `dist` folder

4. **Important:** Remember to place your `cookies.txt` file in the same folder as the `.exe` file before running it

---

## 📁 File Structure

```
instagram-collection-downloader/
├── main.py                 # Main application file
├── requirements.txt        # Python dependencies
├── cookies.txt            # Your exported cookies (you create this)
├── links.txt              # Scraped links (auto-generated)
└── videos/                # Downloaded media (auto-generated)
```

---

## ⚠️ Disclaimer

**This tool is for personal and educational use only.** Downloading content may be against Instagram's Terms of Service. The developers are not responsible for any misuse of this tool. Use at your own risk and ensure you have the right to download any content you access.

---

## 🛠️ Troubleshooting

**Browser won't open:**
- Ensure Google Chrome is installed
- Try updating Chrome to the latest version

**Download fails:**
- Verify your `cookies.txt` file is present and up-to-date
- Re-export your cookies if they're more than a few days old

**No links found:**
- Make sure you're on the correct collection page before clicking "Start Scraping"
- Ensure you're logged in to Instagram in the browser window

---

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/ShaadyEmad/instagram-collection-downloader/issues).

---

<div align="center">

**Created by [ShaadyEmad](https://github.com/ShaadyEmad)**

⭐ Star this repo if you find it helpful!

</div>
