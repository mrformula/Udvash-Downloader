# Try to import aria2p
try:
    import aria2p
    ARIA2_AVAILABLE = True
except ImportError:
    ARIA2_AVAILABLE = False

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
import json
from tqdm import tqdm
import concurrent.futures
import logging
from urllib.parse import urlparse, unquote
import re
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloader.log'),
        logging.StreamHandler()
    ]
)

class VideoDownloader:
    def __init__(self, config_file='config.json'):
        self.config = self.load_config(config_file)
        self.setup_chrome_options()
        self.console = Console()
        
        # Try to start aria2c daemon if not running
        try:
            import aria2p
            import subprocess
            
            # Check if aria2c is installed
            try:
                subprocess.run(['aria2c', '--version'], capture_output=True)
                
                # Start aria2c daemon if not running
                subprocess.Popen(
                    ['aria2c', '--enable-rpc', '--rpc-listen-all=false', '--rpc-listen-port=6800'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
            except FileNotFoundError:
                self.console.print("[yellow]aria2c not found. For faster downloads, install aria2c:[/yellow]")
                self.console.print("[yellow]Windows: choco install aria2[/yellow]")
                self.console.print("[yellow]Linux: sudo apt install aria2[/yellow]")
                self.console.print("[yellow]macOS: brew install aria2[/yellow]")
                
        except ImportError:
            pass

    def load_config(self, config_file):
        default_config = {
            'download_path': 'downloads',
            'max_retries': 3,
            'chunk_size': 8192,
            'max_parallel_downloads': 3,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return {**default_config, **json.load(f)}
        return default_config

    def setup_chrome_options(self):
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--log-level=3')
        self.chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Suppress TensorFlow and other messages
        import os
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        os.environ['PYTHONWARNINGS'] = 'ignore'
        
        # Additional message suppression
        import logging
        logging.getLogger('tensorflow').setLevel(logging.ERROR)
        logging.getLogger('selenium').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        
        # Suppress all warnings
        import warnings
        warnings.filterwarnings('ignore')

    def get_cookies_dict(self, cookies_string):
        cookies = {}
        for cookie in cookies_string.split(';'):
            if cookie.strip():
                try:
                    key, value = cookie.strip().split('=', 1)
                    cookies[key] = value
                except:
                    continue
        return cookies

    def get_video_url(self, cookies_string, class_url):
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            # Initial setup
            driver.get("https://online.utkorsho.tech")
            cookies_dict = self.get_cookies_dict(cookies_string)
            for name, value in cookies_dict.items():
                driver.add_cookie({'name': name, 'value': value})
            
            # Load class page
            driver.get(class_url)
            time.sleep(3)  # Increased wait time
            
            # Switch to video tab if needed
            if "video-section" not in driver.current_url:
                self.switch_to_tab(driver, "video")
                time.sleep(2)
            
            # Wait for video element
            try:
                video_element = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "video"))
                )
                video_url = video_element.get_attribute('src')
                
                if not video_url:
                    # Try to get from source element
                    source_elements = driver.find_elements(By.TAG_NAME, "source")
                    for source in source_elements:
                        video_url = source.get_attribute('src')
                        if video_url:
                            break
                
                if not video_url:
                    # Try to get from data attributes
                    video_container = driver.find_element(By.ID, "video-section")
                    video_url = video_container.get_attribute('data-video-source')
                    
                if not video_url:
                    # Try to get from video-js element
                    video_js = driver.find_element(By.CLASS_NAME, "video-js")
                    video_url = video_js.get_attribute('data-setup')
                    if video_url:
                        # Parse JSON to get URL
                        import json
                        try:
                            data = json.loads(video_url)
                            video_url = data.get('sources', [{}])[0].get('src', '')
                        except:
                            pass
                
                return video_url
                
            except Exception as e:
                self.console.print(f"[yellow]Warning: Could not find video element, trying alternative method...[/yellow]")
                
                # Try alternative method - get from network requests
                try:
                    video_requests = [log for log in driver.get_log('performance') 
                                    if 'mp4' in str(log) or 'm3u8' in str(log)]
                    
                    for request in video_requests:
                        if isinstance(request, dict) and 'message' in request:
                            message = json.loads(request['message'])
                            request_url = message.get('message', {}).get('params', {}).get('request', {}).get('url', '')
                            if '.mp4' in request_url or '.m3u8' in request_url:
                                return request_url
                except:
                    pass
                
                return None
                
        except Exception as e:
            self.console.print(f"[red]Error getting video URL: {str(e)}[/red]")
            return None
        finally:
            driver.quit()

    def download_chunk(self, url, start_byte, end_byte, cookies, headers, filename):
        headers['Range'] = f'bytes={start_byte}-{end_byte}'
        response = requests.get(url, headers=headers, cookies=cookies, stream=True)
        
        temp_filename = f"{filename}.part{start_byte}"
        with open(temp_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=self.config['chunk_size']):
                if chunk:
                    f.write(chunk)
        return temp_filename

    def download_video(self, url, cookies_string, filename, progress, task):
        """Download video with progress tracking"""
        try:
            headers = self.config['headers']
            cookies = self.get_cookies_dict(cookies_string)
            
            # Create download directory if not exists
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # Try aria2c first if available
            if ARIA2_AVAILABLE:
                try:
                    import aria2p
                    
                    # Initialize aria2
                    aria2 = aria2p.API(
                        aria2p.Client(
                            host="http://localhost",
                            port=6800,
                            secret=""
                        )
                    )
                    
                    # Add download
                    download = aria2.add_uris(
                        [url],
                        options={
                            "dir": os.path.dirname(filename),
                            "out": os.path.basename(filename),
                            "header": [f"{k}: {v}" for k, v in headers.items()],
                            "header": f"Cookie: {'; '.join([f'{k}={v}' for k,v in cookies.items()])}",
                            "max-connection-per-server": "16",
                            "split": "16",
                            "min-split-size": "1M",
                            "max-concurrent-downloads": "16",
                            "file-allocation": "none",
                            "continue": "true"
                        }
                    )
                    
                    # Track download progress
                    prev_completed = 0
                    start_time = time.time()
                    
                    while not download.is_complete:
                        download.update()
                        
                        # Calculate progress
                        total = download.total_length
                        completed = download.completed_length
                        if total > 0:
                            percentage = (completed * 100) / total
                            
                            # Calculate speed
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = (completed - prev_completed) / (1024 * 1024 * elapsed)  # MB/s
                                
                                # Update progress
                                progress.update(
                                    task,
                                    completed=percentage,
                                    speed=f"{speed:.1f} MB/s"
                                )
                                
                                # Reset for next update
                                prev_completed = completed
                                start_time = time.time()
                        
                        time.sleep(0.1)
                    
                    return True
                    
                except Exception as e:
                    self.console.print("[yellow]aria2c download failed, falling back to regular download...[/yellow]")
            
            # Fallback to regular download
            # Get total size first
            response = requests.head(url, headers=headers, cookies=cookies)
            total_size = int(response.headers.get('content-length', 0))
            
            if total_size == 0:
                # Try GET request to get size
                response = requests.get(url, headers=headers, cookies=cookies, stream=True)
                total_size = int(response.headers.get('content-length', 0))
                
            if total_size == 0:
                self.console.print("[red]Could not get file size[/red]")
                return False
            
            # Download with progress tracking
            downloaded = 0
            last_update_time = time.time()
            last_downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            
            with requests.get(url, stream=True, headers=headers, cookies=cookies) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            size = len(chunk)
                            downloaded += size
                            f.write(chunk)
                            
                            # Update progress every 0.5 seconds
                            current_time = time.time()
                            if current_time - last_update_time >= 0.5:
                                # Calculate speed
                                time_diff = current_time - last_update_time
                                bytes_diff = downloaded - last_downloaded
                                speed = bytes_diff / (1024 * 1024 * time_diff)  # MB/s
                                
                                # Calculate percentage
                                percentage = (downloaded * 100) / total_size
                                
                                # Update progress
                                progress.update(
                                    task,
                                    completed=percentage,
                                    speed=f"{speed:.1f} MB/s"
                                )
                                
                                # Update last values
                                last_update_time = current_time
                                last_downloaded = downloaded
            
            # Ensure 100% progress at the end
            progress.update(task, completed=100, speed="Done!")
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error downloading video: {str(e)}[/red]")
            if os.path.exists(filename):
                os.remove(filename)
            return False

    def _fallback_download(self, url, cookies_string, filename, progress, task):
        """Regular download method as fallback"""
        try:
            headers = self.config['headers']
            cookies = self.get_cookies_dict(cookies_string)
            
            # Get total size first
            response = requests.head(url, headers=headers, cookies=cookies)
            total_size = int(response.headers.get('content-length', 0))
            
            if total_size == 0:
                self.console.print("[red]Could not get file size[/red]")
                return False
            
            # Download with progress tracking
            downloaded = 0
            start_time = time.time()
            chunk_size = 8192 * 16  # Increased chunk size
            
            with requests.get(url, stream=True, headers=headers, cookies=cookies) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            size = len(chunk)
                            downloaded += size
                            f.write(chunk)
                            
                            # Calculate speed and update progress
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = downloaded / (1024 * 1024 * elapsed)  # MB/s
                                percentage = (downloaded * 100) / total_size
                                
                                progress.update(
                                    task,
                                    completed=percentage,
                                    speed=f"{speed:.1f} MB/s"
                                )
                            
                            # Update time every second for accurate speed
                            if elapsed > 1:
                                start_time = time.time()
                                downloaded = 0
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error downloading video: {str(e)}[/red]")
            if os.path.exists(filename):
                os.remove(filename)
            return False

    def get_video_sources(self, driver, cookies_dict):
        video_sources = []
        
        try:
            # Get all video sources from the data attributes
            video_tab = driver.find_element(By.CSS_SELECTOR, "li.nav-item.d-none")
            video_sources_str = video_tab.get_attribute('data-all-video-source')
            resolutions = video_tab.get_attribute('data-all-resolution').split(',')
            
            if video_sources_str:
                sources = video_sources_str.split(',')
                for i, source in enumerate(sources):
                    if source:
                        video_sources.append(('direct', source.strip(), resolutions[i]))
            
            # Get YouTube video ID
            youtube_id = video_tab.get_attribute('data-youtube-video')
            if youtube_id:
                video_sources.append(('youtube', youtube_id))
                
            logging.info(f"Found {len(video_sources)} video sources")
            
        except Exception as e:
            logging.error(f"Error parsing video sources: {str(e)}")
            
        return video_sources

    def get_video_title(self, driver):
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, ".card-title")
            return title_element.text.strip()
        except:
            return None

    def get_note_url(self, driver):
        try:
            note_link = driver.find_element(By.CSS_SELECTOR, "a[href*='RoutineClassNote']")
            return note_link.get_attribute('href')
        except:
            return None

    def download_with_progress(self, url, filename, cookies, headers):
        response = requests.get(url, stream=True, cookies=cookies, headers=headers)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 KB

        with open(filename, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                start_time = time.time()
                downloaded = 0
                for data in response.iter_content(block_size):
                    downloaded += len(data)
                    f.write(data)
                    
                    # Calculate speed
                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        speed = downloaded / (1024 * 1024 * elapsed_time)  # MB/s
                        pbar.set_postfix(speed=f"{speed:.2f} MB/s", refresh=True)
                    
                    pbar.update(len(data))

    def download_note(self, url, cookies_string, filename):
        try:
            cookies = self.get_cookies_dict(cookies_string)
            headers = {
                **self.config['headers'],
                'Referer': 'https://online.utkorsho.tech/',
                'Accept': 'application/pdf'
            }
            
            # Hide long URL
            self.console.print("[cyan]Downloading note...[/cyan]")
            
            response = requests.get(url, cookies=cookies, headers=headers, stream=True)
            response.raise_for_status()
            
            # Verify it's a PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type:
                self.console.print(f"[yellow]Warning: Response may not be a PDF (Content-Type: {content_type})[/yellow]")
            
            total_size = int(response.headers.get('content-length', 0))
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Downloading note...", total=100)
                
                with open(filename, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            downloaded += len(chunk)
                            f.write(chunk)
                            if total_size:
                                progress.update(task, completed=(downloaded * 100 / total_size))
                                
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self.console.print(f"[green]✓ Note downloaded successfully[/green]")
                return True
            else:
                self.console.print("[red]✗ Downloaded file is empty[/red]")
                if os.path.exists(filename):
                    os.remove(filename)
                return False
                
        except Exception as e:
            self.console.print(f"[red]Failed to download note: {str(e)}[/red]")
            if os.path.exists(filename):
                os.remove(filename)
            return False

    def sanitize_filename(self, filename):
        """Sanitize filename to be safe for all operating systems"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*\n\r]', '', filename)
        
        # Replace Bengali characters with English
        bengali_to_english = {
            '০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4',
            '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'
        }
        
        for ben, eng in bengali_to_english.items():
            filename = filename.replace(ben, eng)
        
        # Limit length and remove extra spaces
        filename = ' '.join(filename.split())  # Replace multiple spaces with single space
        filename = filename[:200]  # Limit length
        
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        
        return filename

    def get_note_url_from_embed(self, driver):
        try:
            embed_element = driver.find_element(By.TAG_NAME, "embed")
            return embed_element.get_attribute('src')
        except:
            return None

    def get_note_url_from_link(self, driver):
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "note-section"))
            )
            
            selectors = [
                "a.btn.btn-success[href*='ums-public-study-materials']",
                "a.btn.btn-success[href*='storage-r2']",
                "a.btn.btn-success[href*='amazonaws.com']",
                "embed[src*='amazonaws.com']",
                "a.btn.btn-success"
            ]
            
            for selector in selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    url = element.get_attribute('href') or element.get_attribute('src')
                    if url and ('pdf' in url.lower()):
                        return url
                except:
                    continue
                
            return None
            
        except Exception as e:
            return None

    def switch_to_tab(self, driver, tab_type="video"):
        try:
            if tab_type == "video":
                tab = driver.find_element(By.CSS_SELECTOR, "a#btn-video-tab")
            else:
                tab = driver.find_element(By.CSS_SELECTOR, "a#btn-note-tab")
                
            if "active" not in tab.get_attribute("class"):
                self.console.print(f"[cyan]Switching to {tab_type} tab...[/cyan]")
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
            return True
        except Exception as e:
            self.console.print(f"[red]Failed to switch to {tab_type} tab: {str(e)}[/red]")
            return False

    def ask_resolution_preference(self, available_resolutions):
        self.console.print("\n[yellow]Available video qualities:[/yellow]")
        for i, res in enumerate(available_resolutions, 1):
            self.console.print(f"[cyan]{i}.[/cyan] {res}p")
        
        while True:
            choice = self.console.input("\n[bold blue]Choose quality (number) or press Enter for all:[/bold blue] ").strip()
            if not choice:
                return available_resolutions
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(available_resolutions):
                    return [available_resolutions[idx]]
                else:
                    self.console.print("[red]Invalid choice. Try again.[/red]")
            except:
                self.console.print("[red]Please enter a valid number.[/red]")

    def get_full_title(self, driver):
        try:
            # Get main title
            title = driver.find_element(By.CSS_SELECTOR, ".card-title").text.strip()
            
            # Get topic/chapter info
            topic_element = driver.find_element(By.CSS_SELECTOR, ".card-body.bangla-version div div strong")
            if topic_element:
                topic = topic_element.text.strip()
                # Extract chapter and topic
                if '[' in topic:
                    chapter, details = topic.split('[', 1)
                    details = details.rstrip(']')
                    title = f"{title} - {chapter.strip()} [{details}"
                else:
                    title = f"{title} - {topic}"
                
            return title
        except:
            return None

    def ask_youtube_preference(self, video_id):
        if video_id:
            self.console.print("\n[yellow]YouTube version available![/yellow]")
            choice = self.console.input("[bold blue]Do you want to download YouTube version? (y/N):[/bold blue] ").strip().lower()
            return choice == 'y'
        return False

    def get_youtube_resolutions(self, video_id):
        try:
            from pytube import YouTube
            yt = YouTube(f'https://www.youtube.com/watch?v={video_id}')
            streams = yt.streams.filter(progressive=True, file_extension='mp4')
            resolutions = []
            for stream in streams:
                res = int(stream.resolution.replace('p', ''))
                resolutions.append(res)
            return sorted(resolutions, reverse=True), yt
        except Exception as e:
            self.console.print(f"[red]Error getting YouTube resolutions: {str(e)}[/red]")
            return [], None

    def download_youtube(self, video_id, filename):
        try:
            import yt_dlp
            
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': filename,
                'quiet': True,
                'no_warnings': True,
                # IDM-like settings
                'external_downloader': 'aria2c',
                'external_downloader_args': [
                    '--min-split-size=1M',
                    '--max-connection-per-server=16',
                    '--split=16',
                    '--max-concurrent-downloads=16',
                    '--file-allocation=none'
                ]
            }
            
            # Get video info first
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
                formats = info.get('formats', [])
                
                # Filter for MP4 formats with both video and audio
                available_formats = []
                for f in formats:
                    if (f.get('vcodec') != 'none' and f.get('acodec') != 'none' and 
                        f.get('ext') == 'mp4' and f.get('height')):
                        height = f.get('height', 0)
                        if height in [360, 480, 720, 1080]:  # Include all standard resolutions
                            filesize = f.get('filesize', 0)
                            if filesize == 0:  # If filesize not available, try to get from URL
                                try:
                                    response = requests.head(f['url'])
                                    filesize = int(response.headers.get('content-length', 0))
                                except:
                                    pass
                            available_formats.append((height, f['format_id'], filesize))
                
                # Sort by resolution (highest first)
                available_formats.sort(key=lambda x: (x[0], x[2]), reverse=True)
                
                if not available_formats:
                    self.console.print("[red]No suitable formats found[/red]")
                    return False
                
                # Show available qualities with file sizes in a clean UI
                self.console.print("\n[yellow]╭─── Available YouTube Qualities ───╮[/yellow]")
                for i, (height, _, size) in enumerate(available_formats, 1):
                    size_mb = size / (1024 * 1024) if size else 0
                    if size_mb > 0:
                        self.console.print(f"[cyan]│ {i}. {height}p[/cyan] ({size_mb:.1f} MB)")
                    else:
                        self.console.print(f"[cyan]│ {i}. {height}p[/cyan]")
                self.console.print("[yellow]╰────────────────────────────────╯[/yellow]\n")
                
                # Get user choice
                while True:
                    choice = self.console.input("[bold blue]Choose quality (number):[/bold blue] ").strip()
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(available_formats):
                            selected_format = available_formats[idx][1]
                            break
                        else:
                            self.console.print("[red]Invalid choice. Try again.[/red]")
                    except:
                        self.console.print("[red]Please enter a valid number.[/red]")
                
                # Update options with selected format
                ydl_opts['format'] = selected_format
                
                # Add progress hook with speed display
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("•"),
                    TextColumn("[cyan]{task.fields[speed]}[/cyan]"),
                    console=self.console
                ) as progress:
                    task = progress.add_task("Downloading...", total=100, speed="0 MB/s")
                    
                    def progress_hook(d):
                        if d['status'] == 'downloading':
                            # Calculate speed in MB/s
                            speed = d.get('speed', 0)
                            if speed:
                                speed_mb = speed / (1024 * 1024)
                                speed_text = f"{speed_mb:.1f} MB/s"
                            else:
                                speed_text = "-- MB/s"
                            
                            # Update progress
                            downloaded = d.get('downloaded_bytes', 0)
                            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                            if total:
                                percentage = (downloaded / total) * 100
                                progress.update(task, completed=percentage, speed=speed_text)
                
                    ydl_opts['progress_hooks'] = [progress_hook]
                    
                    # Download video
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
                
                self.console.print("[green]✓ Successfully downloaded YouTube version[/green]")
                return True
                
        except Exception as e:
            self.console.print(f"[red]Failed to download YouTube version: {str(e)}[/red]")
            if "aria2c" in str(e):
                self.console.print("[yellow]Please install aria2c for faster downloads:[/yellow]")
                self.console.print("[yellow]Windows: choco install aria2[/yellow]")
                self.console.print("[yellow]Linux: sudo apt install aria2[/yellow]")
                self.console.print("[yellow]macOS: brew install aria2[/yellow]")
            else:
                self.console.print("[yellow]Please install yt-dlp first: pip install yt-dlp[/yellow]")
            return False

    def process_class_page(self, cookies_string, class_url):
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            # Initial setup
            self.console.print("\n[bold]🔄 Initializing...[/bold]")
            driver.get("https://online.utkorsho.tech")
            cookies_dict = self.get_cookies_dict(cookies_string)
            for name, value in cookies_dict.items():
                driver.add_cookie({'name': name, 'value': value})
            
            # Load page
            self.console.print("[bold]📥 Loading class page...[/bold]")
            driver.get(class_url)
            time.sleep(2)
            
            # Get video title
            video_title = self.get_full_title(driver)
            if video_title:
                base_filename = self.sanitize_filename(video_title)
                self.console.print(f"\n[bold green]📝 Class Title:[/bold green] {video_title}")
            else:
                base_filename = "video"

            # Try to get video sources
            video_sources = []
            note_url = None
            youtube_id = None
            
            # Check current tab and get content
            current_tab = "video" if "video-section" in driver.current_url else "note"
            
            # Try video tab first
            if current_tab != "video":
                self.switch_to_tab(driver, "video")
            video_sources = self.get_video_sources(driver, cookies_dict)
            
            # Extract YouTube ID if available
            for source in video_sources:
                if source[0] == 'youtube':
                    youtube_id = source[1]
                    break

            # Ask for YouTube preference first
            if youtube_id and self.ask_youtube_preference(youtube_id):
                filename = os.path.join(
                    self.config['download_path'], 
                    f"{base_filename}_youtube.mp4"
                )
                if not self.download_youtube(youtube_id, filename):
                    self.console.print("[yellow]Falling back to direct download...[/yellow]")
                    # Process direct video sources
                    if video_sources:
                        self.process_direct_sources(video_sources, base_filename, cookies_string)
            else:
                # Process direct video sources
                if video_sources:
                    self.process_direct_sources(video_sources, base_filename, cookies_string)

            # Handle notes
            if not note_url:
                self.switch_to_tab(driver, "note")
                note_url = self.get_note_url_from_link(driver)

            if note_url:
                note_filename = os.path.join(
                    self.config['download_path'], 
                    f"{base_filename}_note.pdf"
                )
                self.console.print("[cyan]Downloading note...[/cyan]")
                
                try:
                    response = requests.get(note_url, cookies=cookies_dict, headers=self.config['headers'])
                    with open(note_filename, 'wb') as f:
                        f.write(response.content)
                    self.console.print("[green]✓ Note downloaded successfully[/green]")
                except Exception as e:
                    self.console.print(f"[red]✗ Failed to download note: {str(e)}[/red]")

            return True

        except Exception as e:
            self.console.print(f"[red]Error processing class page: {str(e)}[/red]")
            return False
            
        finally:
            driver.quit()

    def process_direct_sources(self, video_sources, base_filename, cookies_string):
        self.console.print(f"[green]Found {len(video_sources)} video sources[/green]")
        
        # Get available resolutions
        resolutions = []
        for source in video_sources:
            if source[0] == 'direct':
                resolutions.append(int(source[2]))
        
        if not resolutions:
            self.console.print("[red]No direct download sources found[/red]")
            return False
        
        # Ask user preference
        selected_resolutions = self.ask_resolution_preference(sorted(resolutions, reverse=True))
        
        # Download selected videos
        for source_info in video_sources:
            if source_info[0] == 'direct':
                source_type, url, resolution = source_info
                if int(resolution) not in selected_resolutions:
                    continue
                    
                filename = os.path.join(
                    self.config['download_path'], 
                    f"{base_filename}_{resolution}p.mp4"
                )
                
                if not os.path.exists(filename):
                    self.console.print(f"[cyan]Downloading {resolution}p video...[/cyan]")
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=self.console
                    ) as progress:
                        task = progress.add_task(f"Downloading...", total=100)
                        if self.download_video(url, cookies_string, filename, progress, task):
                            self.console.print(f"[green]✓ Successfully downloaded {resolution}p version[/green]")
                        else:
                            self.console.print(f"[red]✗ Failed to download {resolution}p version[/red]")
        return True

    def show_welcome(self):
        welcome_text = Text()
        welcome_text.append("\n╭───────────── Udvash Video Downloader ───────────────╮\n", style="bold green")
        welcome_text.append("\n   🎥 Download videos and notes from Udvash online classes", style="blue")
        welcome_text.append("\n\n   ✨ Features:", style="yellow")
        welcome_text.append("\n   ├─ 📹 Multiple video qualities", style="cyan")
        welcome_text.append("\n   ├─ 📄 PDF notes download", style="cyan")
        welcome_text.append("\n   ├─ 📊 Progress tracking", style="cyan")
        welcome_text.append("\n   └─ 🚀 Download speed display", style="cyan")
        welcome_text.append("\n\n╰──────────────────────────────────────────────────────╯", style="bold green")
        self.console.print(welcome_text)

    def save_cookies(self, cookies_string):
        try:
            with open('cookies.txt', 'w') as f:
                f.write(cookies_string)
            self.console.print("[green]✓ Cookies saved successfully![/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]Failed to save cookies: {str(e)}[/red]")
            return False

    def load_cookies(self):
        try:
            if os.path.exists('cookies.txt'):
                with open('cookies.txt', 'r') as f:
                    return f.read().strip()
        except:
            pass
        return None

    def get_youtube_quality_preference(self, video_id):
        """Get YouTube quality preference without downloading"""
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
                formats = info.get('formats', [])
                
                # Filter and sort formats
                available_formats = []
                for f in formats:
                    if (f.get('vcodec') != 'none' and f.get('acodec') != 'none' and 
                        f.get('ext') == 'mp4' and f.get('height')):
                        height = f.get('height', 0)
                        if height in [360, 480, 720, 1080]:
                            available_formats.append((height, f['format_id']))
                
                available_formats.sort(key=lambda x: x[0], reverse=True)
                
                if not available_formats:
                    return None
                
                # Show available qualities
                self.console.print("\n[yellow]╭─── Available YouTube Qualities ───╮[/yellow]")
                for i, (height, _) in enumerate(available_formats, 1):
                    self.console.print(f"[cyan]│ {i}. {height}p[/cyan]")
                self.console.print("[yellow]╰──────────────────────────────────────────╯[/yellow]\n")
                
                # Get user choice
                while True:
                    choice = self.console.input("[bold blue]Choose quality (number):[/bold blue] ").strip()
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(available_formats):
                            return available_formats[idx][1]
                        else:
                            self.console.print("[red]Invalid choice. Try again.[/red]")
                    except:
                        self.console.print("[red]Please enter a valid number.[/red]")
        except:
            return None

    def process_class_page_with_preferences(self, cookies_string, class_url, use_youtube=False, youtube_quality=None, direct_quality=None):
        driver = webdriver.Chrome(options=self.chrome_options)
        video_downloaded = False
        
        try:
            # Initial setup
            driver.get("https://online.utkorsho.tech")
            cookies_dict = self.get_cookies_dict(cookies_string)
            for name, value in cookies_dict.items():
                driver.add_cookie({'name': name, 'value': value})
            
            # Load page
            driver.get(class_url)
            time.sleep(2)
            
            # Get video title
            video_title = self.get_full_title(driver)
            if video_title:
                # Remove topic details from filename to keep it shorter
                title_parts = video_title.split('-', 1)
                base_filename = self.sanitize_filename(title_parts[0].strip())
            else:
                base_filename = "video"

            # Create filenames
            if use_youtube:
                filename = os.path.join(
                    self.config['download_path'],
                    f"{base_filename}_youtube.mp4"
                )
            else:
                filename = os.path.join(
                    self.config['download_path'],
                    f"{base_filename}_{direct_quality}p.mp4"
                )

            # For notes
            note_filename = os.path.join(
                self.config['download_path'],
                f"{base_filename}_note.pdf"
            )

            # Switch to video tab
            self.switch_to_tab(driver, "video")
            time.sleep(2)
            
            # Get video sources
            video_sources = self.get_video_sources(driver, cookies_dict)
            
            if not video_sources:
                # Try to get direct video URL
                video_url = self.get_video_url(cookies_string, class_url)
                if video_url:
                    video_sources = [('direct', video_url, '720')]
            
            if video_sources:
                # Handle YouTube download
                if use_youtube:
                    youtube_id = next((source[1] for source in video_sources if source[0] == 'youtube'), None)
                    if youtube_id:
                        video_downloaded = self.download_youtube_with_quality(youtube_id, filename, youtube_quality)
                
                # Handle direct download if YouTube failed or not chosen
                if not video_downloaded and direct_quality:
                    direct_source = next((source for source in video_sources 
                                        if source[0] == 'direct'), None)
                    if direct_source:
                        # Download video with progress
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                            TextColumn("•"),
                            TextColumn("[cyan]{task.fields[speed]}[/cyan]"),
                            console=self.console
                        ) as progress:
                            task = progress.add_task(
                                f"Downloading {direct_quality}p version...", 
                                total=100,
                                speed="0 MB/s"
                            )
                            
                            if self.download_video(direct_source[1], cookies_string, filename, progress, task):
                                self.console.print("[green]✓ Successfully downloaded video[/green]")
                                video_downloaded = True
                            else:
                                self.console.print("[red]✗ Failed to download video[/red]")
            
            # Handle notes
            if not video_downloaded:
                self.console.print("[red]Failed to download video[/red]")
                
            self.switch_to_tab(driver, "note")
            time.sleep(2)
            
            note_url = self.get_note_url_from_link(driver)
            if note_url:
                self.download_note(note_url, cookies_string, note_filename)
            
            return video_downloaded
                
        except Exception as e:
            self.console.print(f"[red]Error processing class: {str(e)}[/red]")
            return False
        finally:
            driver.quit()

    def download_youtube_with_quality(self, video_id, filename, format_id):
        """Download YouTube video with specified quality"""
        try:
            import yt_dlp
            ydl_opts = {
                'format': format_id,
                'outtmpl': filename,
                'quiet': True,
                'no_warnings': True,
                'external_downloader': 'aria2c',
                'external_downloader_args': [
                    '--min-split-size=1M',
                    '--max-connection-per-server=16',
                    '--split=16',
                    '--max-concurrent-downloads=16',
                    '--file-allocation=none'
                ]
            }
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("•"),
                TextColumn("[cyan]{task.fields[speed]}[/cyan]"),
                console=self.console
            ) as progress:
                task = progress.add_task("Downloading...", total=100, speed="0 MB/s")
                
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        speed = d.get('speed', 0)
                        if speed:
                            speed_mb = speed / (1024 * 1024)
                            speed_text = f"{speed_mb:.1f} MB/s"
                        else:
                            speed_text = "-- MB/s"
                        
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                        if total:
                            percentage = (downloaded / total) * 100
                            progress.update(task, completed=percentage, speed=speed_text)
                
                ydl_opts['progress_hooks'] = [progress_hook]
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
                
                return True
                
        except Exception as e:
            self.console.print(f"[red]Failed to download YouTube version: {str(e)}[/red]")
            return False

def main():
    # Suppress all logs
    import os
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    os.environ['PYTHONWARNINGS'] = 'ignore'
    
    import logging
    for logger in [
        'tensorflow', 'selenium', 'urllib3', 
        'selenium.webdriver.remote.remote_connection'
    ]:
        logging.getLogger(logger).setLevel(logging.ERROR)
    
    # Disable all warnings
    import warnings
    warnings.filterwarnings('ignore', category=Warning)
    
    downloader = VideoDownloader()
    downloader.show_welcome()
    
    # Try to load saved cookies
    cookies = downloader.load_cookies()
    if not cookies:
        cookies = downloader.console.input("\n[bold blue]🔑 Enter your cookies string:[/bold blue] ").strip()
        if cookies:
            downloader.save_cookies(cookies)
    else:
        downloader.console.print("\n[bold green]✅ Using saved cookies[/bold green]")
        if downloader.console.input("[bold blue]🔄 Update cookies? (y/N):[/bold blue] ").strip().lower() == 'y':
            cookies = downloader.console.input("[bold blue]🔑 Enter new cookies:[/bold blue] ").strip()
            if cookies:
                downloader.save_cookies(cookies)
    
    while True:
        class_url = downloader.console.input("\n[bold blue]🔗 Enter class URL (or 'q' to quit):[/bold blue] ").strip()
        
        if class_url.lower() == 'q':
            break
            
        if downloader.process_class_page(cookies, class_url):
            downloader.console.print("\n[bold green] All downloads completed successfully![/bold green]")
        else:
            downloader.console.print("\n[bold red]❌ Some downloads failed![/bold red]")
        
        downloader.console.print("\n[bold cyan]📥 Ready for next download...[/bold cyan]")
    
    downloader.console.print("\n[bold yellow]👋 Thank you for using Udvash Video Downloader![/bold yellow]")

if __name__ == "__main__":
    main() 